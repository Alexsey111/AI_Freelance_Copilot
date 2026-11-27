"""Бенчмарк локальных моделей на живых заказах: качество против времени.

Берём заказы, по которым уже есть решение облачной модели (gpt-4o-mini), и прогоняем
те же заказы через локальные модели с тем же промптом и той же схемой JSON. Сравниваем:
валиден ли JSON, заполнены ли обязательные поля, совпала ли рекомендация, сколько
секунд и токенов стоил заказ.

Денег не тратит: всё локально. Пишет по строке на вызов в JSONL, поэтому прогон можно
прервать и продолжить — уже сделанные пары «модель + заказ» пропускаются.

Запуск:
    python scripts/bench_local_models.py --limit 20
    python scripts/bench_local_models.py --report   # только отчёт по готовому JSONL
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # noqa: E402

from app.domain.models.order import Order  # noqa: E402
from app.domain.models.profile import Profile  # noqa: E402
from app.infrastructure.llm.base import build_order_prompt  # noqa: E402

OLLAMA = "http://localhost:11434/api/chat"
MODELS = [
    "qwen2.5-coder:7b-instruct-q5_K_M",
    "deepseek-r1:8b",
    "hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M",
]
REQUIRED = ("match_score", "recommendation", "reason", "needs_review")
MIN_DRAFT = 80
RESULT_FILE = ROOT / "docs" / "bench-local-models.jsonl"
REPORT_FILE = ROOT / "docs" / "bench-local-models.md"


def load_orders(db: Path, limit: int) -> list[sqlite3.Row]:
    """Заказы с решением облачной модели и черновиком — чтобы сравнение было честным."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT o.*, a.recommendation AS ref_recommendation, a.draft_reply AS ref_draft,
               a.model AS ref_model, a.needs_review AS ref_needs_review
        FROM orders o
        JOIN analyses a ON a.order_id = o.id
        WHERE a.error IS NULL
          AND a.recommendation IS NOT NULL
          AND a.draft_reply IS NOT NULL AND length(a.draft_reply) >= 80
          AND a.id = (SELECT MAX(id) FROM analyses WHERE order_id = o.id)
        ORDER BY o.id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    con.close()
    return rows


def load_profile(db: Path) -> Profile:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM profiles WHERE is_active = 1 LIMIT 1").fetchone()
    con.close()
    return Profile(
        id=row["id"],
        name=row["name"],
        summary=row["summary"],
        skills=json.loads(row["skills"] or "[]"),
        experience=row["experience"],
        portfolio=row["portfolio"],
        preferences=json.loads(row["preferences"] or "{}"),
    )


def as_order(row: sqlite3.Row) -> Order:
    return Order(
        id=row["id"],
        source=row["source"],
        external_id=row["external_id"],
        title=row["title"],
        description=row["description"] or "",
        budget_min=row["budget_min"],
        budget_max=row["budget_max"],
        currency=row["currency"],
        url=row["url"],
        status=row["status"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def done_pairs() -> set[tuple[str, int]]:
    if not RESULT_FILE.exists():
        return set()
    pairs = set()
    for line in RESULT_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        pairs.add((item["model"], item["order_id"]))
    return pairs


def call_model(model: str, system: str, user: str, timeout: float = 1200) -> dict:
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 900, "num_ctx": 4096},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode()
    request = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def score_call(data: dict, elapsed: float, ref: sqlite3.Row) -> dict:
    content = data.get("message", {}).get("content", "")
    parsed: dict = {}
    valid = True
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        valid = False
    fields = [key for key in REQUIRED if key in parsed]
    draft = parsed.get("draft_reply")
    return {
        "json_valid": valid,
        "fields_present": len(fields),
        "missing_fields": [key for key in REQUIRED if key not in parsed],
        "recommendation": parsed.get("recommendation"),
        "ref_recommendation": ref["ref_recommendation"],
        "match": parsed.get("recommendation") == ref["ref_recommendation"],
        "match_score": parsed.get("match_score"),
        "draft_chars": len(draft) if isinstance(draft, str) else 0,
        "draft_ok": isinstance(draft, str) and len(draft) >= MIN_DRAFT,
        "needs_review": parsed.get("needs_review"),
        "elapsed_s": self_round(elapsed),
        "tokens_in": data.get("prompt_eval_count", 0),
        "tokens_out": data.get("eval_count", 0),
        "tok_per_s": round(data.get("eval_count", 0) / elapsed, 2) if elapsed > 0 else 0,
    }


def self_round(value: float) -> float:
    return float(round(value, 1))


def run(db: Path, limit: int) -> None:
    orders = load_orders(db, limit)
    profile = load_profile(db)
    print(f"заказов в выборке: {len(orders)}; моделей: {len(MODELS)}", flush=True)
    done = done_pairs()
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    total = len(orders) * len(MODELS)
    step = len(done)
    with RESULT_FILE.open("a", encoding="utf-8") as sink:
        for model in MODELS:
            for row in orders:
                if (model, row["id"]) in done:
                    continue
                prompt = build_order_prompt(as_order(row), profile)
                started = time.perf_counter()
                try:
                    data = call_model(model, prompt.system, prompt.user)
                    result = score_call(data, time.perf_counter() - started, row)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    result = {"json_valid": False, "error": f"{type(exc).__name__}: {exc}"}
                record = {
                    "model": model,
                    "order_id": row["id"],
                    "title": row["title"][:70],
                    **result,
                }
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                step += 1
                print(
                    f"[{step}/{total}] {model.split('/')[-1][:28]:28} #{row['id']:>3} "
                    f"{record.get('elapsed_s', '?')} с · json={record.get('json_valid')} "
                    f"· match={record.get('match')} · draft={record.get('draft_chars')}",
                    flush=True,
                )


def report() -> None:
    if not RESULT_FILE.exists():
        print("нет данных: сначала прогон")
        return
    rows = [
        json.loads(line)
        for line in RESULT_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_model: dict[str, list[dict]] = {}
    for item in rows:
        by_model.setdefault(item["model"], []).append(item)

    lines = [
        "# Локальные модели на живых заказах",
        "",
        "Один и тот же промпт и схема JSON, что и у ядра. Эталон — решение облачной модели,",
        "уже лежащее в базе (`analyses`). «Совпало» — локальная модель дала ту же",
        "рекомендацию (`apply` / `skip` / `review`).",
        "",
        "| Модель | Заказов | JSON валиден | Все поля | Черновик ок | Совпало с облачной | Секунд/заказ | Ток/с |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, items in by_model.items():
        n = len(items)
        valid = sum(1 for i in items if i.get("json_valid"))
        full = sum(1 for i in items if i.get("fields_present") == len(REQUIRED))
        draft = sum(1 for i in items if i.get("draft_ok"))
        match = sum(1 for i in items if i.get("match"))
        avg_s = sum(i.get("elapsed_s", 0) for i in items) / n if n else 0
        avg_tps = sum(i.get("tok_per_s", 0) for i in items) / n if n else 0
        lines.append(
            f"| {model.split('/')[-1][:40]} | {n} | {valid}/{n} | {full}/{n} | {draft}/{n} "
            f"| {match}/{n} | {avg_s:.0f} | {avg_tps:.1f} |"
        )
    lines += [
        "",
        "Как читать: «все поля» важнее «JSON валиден». Валидный JSON без черновика отклика",
        "ядро всё равно отправит на проверку человеку — то есть работа не сделана.",
        "",
    ]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"записано: {REPORT_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "live.db"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report()
        return
    run(Path(args.db), args.limit)
    report()


if __name__ == "__main__":
    main()
