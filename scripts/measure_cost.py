#!/usr/bin/env python3
"""Замер стоимости прогона анализа: реальные токены от провайдера.

Зачем: ядро не сохраняет usage из ответа модели, поэтому «сколько стоит прогон»
до сих пор было оценкой по длине текста. Скрипт прогоняет те же заказы тем же
кодом (AnalysisService + реальный провайдер), но перехватывает `response.usage`
у клиента OpenAI-совместимого провайдера и складывает точные числа.

Запуск (из каталога ядра, на КОПИИ базы, чтобы не портить рабочие данные):

    cp data/live.db data/probe.db
    DATABASE_URL=sqlite:///./data/probe.db LLM_PROVIDER=openai \
        ./.venv/Scripts/python.exe scripts/measure_cost.py \
        --price-in 39 --price-out 155 \
        --out artifacts/cost-run.json

Цены по умолчанию — proxyapi.ru для openai/gpt-4o-mini на 03.11.2026:
39 ₽ за 1М входных токенов, 155 ₽ за 1М выходных, с НДС.
Цены меняются: перед прогоном сверить на https://proxyapi.ru/models/openai/gpt-4o-mini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.domain.services.analysis_service import AnalysisService  # noqa: E402
from app.domain.services.audit_service import AuditService  # noqa: E402
from app.infrastructure.database.database import Database  # noqa: E402
from app.infrastructure.database.repositories import (  # noqa: E402
    AnalysisRepository,
    AuditRepository,
    OrderRepository,
    ProfileRepository,
)
from app.infrastructure.llm.factory import build_llm_provider  # noqa: E402


def sqlite_path_from_url(url: str) -> Path:
    """sqlite:///./data/probe.db -> Path('./data/probe.db')."""
    if not url.startswith("sqlite"):
        raise SystemExit("Скрипт рассчитан только на sqlite")
    raw = url.split("///", 1)[1] if "///" in url else url.split("//", 1)[1]
    return Path(raw.lstrip("/"))


def order_ids(db_file: Path) -> list[int]:
    con = sqlite3.connect(db_file)
    try:
        return [row[0] for row in con.execute("select id from orders order by id")]
    finally:
        con.close()


class UsageRecorder:
    """Оборачивает chat.completions.create и складывает usage по каждому вызову."""

    def __init__(self, create):
        self._create = create
        self.calls: list[dict] = []

    async def __call__(self, *args, **kwargs):
        response = await self._create(*args, **kwargs)
        usage = getattr(response, "usage", None)
        self.calls.append(
            {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
        )
        return response


async def run(price_in: float, price_out: float) -> dict:
    settings = get_settings()
    db_file = sqlite_path_from_url(settings.database_url)
    if not db_file.exists():
        raise SystemExit(f"Нет базы {db_file}: сначала создайте её (ingest) и скопируйте под прогон")

    database = Database(settings.database_url)
    database.create_all()
    with database.session() as session:
        ProfileRepository(session).ensure_default()

    provider = build_llm_provider(settings)
    if getattr(provider, "name", "mock") == "mock":
        raise SystemExit("Провайдер mock: задайте LLM_PROVIDER=openai, иначе мерить нечего")

    recorder = UsageRecorder(getattr(provider, "_client").chat.completions.create)
    getattr(provider, "_client").chat.completions.create = recorder

    ids = order_ids(db_file)
    rows = []
    started = time.perf_counter()
    for order_id in ids:
        before = len(recorder.calls)
        t0 = time.perf_counter()
        with database.session() as session:
            service = AnalysisService(
                order_repository=OrderRepository(session),
                profile_repository=ProfileRepository(session),
                analysis_repository=AnalysisRepository(session),
                audit_service=AuditService(AuditRepository(session)),
                llm_provider=provider,
                settings=settings,
            )
            outcome = await service.analyze_order(order_id)
        call = recorder.calls[before] if len(recorder.calls) > before else {}
        rows.append(
            {
                "order_id": order_id,
                "duration_ms": outcome.duration_ms,
                "wall_ms": int((time.perf_counter() - t0) * 1000),
                "recommendation": outcome.result.recommendation,
                "needs_review": bool(outcome.result.needs_review),
                "match_score": outcome.result.match_score,
                "prompt_tokens": call.get("prompt_tokens"),
                "completion_tokens": call.get("completion_tokens"),
                "audit_status": outcome.audit_status,
            }
        )
        print(
            f"#{order_id} {outcome.duration_ms} мс "
            f"{rows[-1]['prompt_tokens']}+{rows[-1]['completion_tokens']} ток "
            f"{outcome.result.recommendation}",
            flush=True,
        )

    prompt_tokens = sum(r["prompt_tokens"] or 0 for r in rows)
    completion_tokens = sum(r["completion_tokens"] or 0 for r in rows)
    cost_in = prompt_tokens / 1_000_000 * price_in
    cost_out = completion_tokens / 1_000_000 * price_out
    durations = sorted(r["duration_ms"] for r in rows)

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": getattr(provider, "name", None),
        "model": getattr(provider, "model", None),
        "database": str(db_file),
        "orders": len(rows),
        "wall_seconds": round(time.perf_counter() - started, 1),
        "prompt_tokens_total": prompt_tokens,
        "completion_tokens_total": completion_tokens,
        "tokens_per_order_avg": round((prompt_tokens + completion_tokens) / max(len(rows), 1)),
        "duration_ms_avg": int(sum(durations) / max(len(durations), 1)),
        "duration_ms_median": durations[len(durations) // 2] if durations else None,
        "duration_ms_max": durations[-1] if durations else None,
        "price_rub_per_1m_input": price_in,
        "price_rub_per_1m_output": price_out,
        "cost_rub_input": round(cost_in, 3),
        "cost_rub_output": round(cost_out, 3),
        "cost_rub_total": round(cost_in + cost_out, 3),
        "cost_rub_per_order": round((cost_in + cost_out) / max(len(rows), 1), 4),
        "calls": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Точный замер стоимости прогона (usage от провайдера)")
    parser.add_argument("--price-in", type=float, default=39.0, help="₽ за 1М входных токенов")
    parser.add_argument("--price-out", type=float, default=155.0, help="₽ за 1М выходных токенов")
    parser.add_argument("--out", default="artifacts/cost-run.json", help="куда записать отчёт")
    args = parser.parse_args()

    report = asyncio.run(run(args.price_in, args.price_out))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "calls"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
