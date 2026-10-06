"""Сквозной прогон набора tests_data/ через живое API + экспорт результатов.

Что делает:
  1. читает tests_data/inputs.jsonl (15 сценариев) и заливает их через точку 1;
  2. запускает ИИ-анализ по каждому (точка 3);
  3. сверяет факт со tests_data/specs.jsonl и печатает таблицу;
  4. выполняет запросы витрины из tests_data/queries.jsonl (точка 2);
  5. выгружает артефакты для отчёта: результаты сценариев, витрину и аудит --- в JSON и CSV.

Запуск (backend уже поднят):
    ./.venv/Scripts/python.exe scripts/run_tests_data.py
    ./.venv/Scripts/python.exe scripts/run_tests_data.py --base-url http://127.0.0.1:8300
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.fixtures.tests_data_set import check_spec, events, inputs, queries, specs  # noqa: E402

SCENARIO_FIELDS = ["id", "order_id", "needs_review", "recommendation", "match_score",
                   "audit_status", "order_status", "has_draft_reply", "review_reason", "ok"]
SHOWCASE_FIELDS = ["id", "external_id", "source", "title", "status", "needs_review",
                   "budget_min", "budget_max", "currency", "match_score", "recommendation"]
AUDIT_FIELDS = ["id", "created_at", "action", "order_id", "status", "duration_ms", "error"]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description="Прогон набора тестовых данных с экспортом")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out-dir", default="artifacts")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        health = requests.get(f"{base}/api/v1/health", timeout=10).json()
    except requests.RequestException as exc:
        print(f"Backend недоступен по адресу {base}: {exc}")
        print("Сначала запустите: ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000")
        return 1
    print(f"Backend: {health['status']} · провайдер LLM: {health['provider']['name']}")
    if health["provider"]["is_live"]:
        print("ВНИМАНИЕ: активен реальный LLM-провайдер, прогон потратит деньги.")

    spec_by_id = {row["id"]: row for row in specs()}
    results: list[dict] = []
    problems: list[str] = []

    print(f"\nСценарии ({len(inputs())}):")
    for row in inputs():
        case_id, payload = row["id"], row["payload"]
        spec = spec_by_id[case_id]
        created = requests.post(f"{base}/api/v1/orders", json=payload, timeout=30)
        created.raise_for_status()
        order_id = created.json()["id"]
        analyzed = requests.post(f"{base}/api/v1/orders/{order_id}/analyze", json={}, timeout=180)
        analyzed.raise_for_status()
        body = analyzed.json()
        result = body["result"]

        outcome = type("Outcome", (), {
            "needs_review": result["needs_review"],
            "recommendation": result["recommendation"],
            "match_score": result["match_score"],
            "review_reason": result["review_reason"],
            "draft_reply": result["draft_reply"],
            "audit_status": body["audit_status"],
            "order_status": body["order_status"],
        })()
        mismatch = check_spec(outcome, spec)
        problems.extend(f"{case_id}: {text}" for text in mismatch)
        score = "—" if result["match_score"] is None else f"{result['match_score'] * 100:.0f}%"
        flag = "OK " if not mismatch else "!! "
        review = "РУЧНАЯ ПРОВЕРКА" if result["needs_review"] else ""
        print(f"  {flag}{case_id:26} {result['recommendation']:>6} · match {score:>4} · "
              f"{body['audit_status']:>7} · {body['duration_ms']:>5} мс {review}")
        if result["review_reason"]:
            print(f"      причина: {result['review_reason']}")
        results.append({
            "id": case_id, "order_id": order_id,
            "needs_review": result["needs_review"], "recommendation": result["recommendation"],
            "match_score": result["match_score"], "audit_status": body["audit_status"],
            "order_status": body["order_status"], "has_draft_reply": bool(result["draft_reply"]),
            "review_reason": result["review_reason"], "ok": not mismatch,
        })

    print("\nВитрина (точка 2):")
    query_results: list[dict] = []
    for query in queries():
        response = requests.get(f"{base}/api/v1/orders", params=query["params"], timeout=30)
        if query.get("expect_http"):
            ok = response.status_code == query["expect_http"]
            print(f"  {'OK ' if ok else '!! '}{query['id']:26} HTTP {response.status_code} "
                  f"(ожидался {query['expect_http']})")
            query_results.append({"id": query["id"], "http": response.status_code, "ok": ok})
            if not ok:
                problems.append(f"{query['id']}: HTTP {response.status_code}")
            continue
        body = response.json()
        ok = body["total"] == query["expect_total"]
        if query.get("expect_items"):
            ok = ok and len(body["items"]) == query["expect_items"]
        if query.get("expect_all_needs_review"):
            ok = ok and all(item["needs_review"] for item in body["items"])
        print(f"  {'OK ' if ok else '!! '}{query['id']:26} total={body['total']} "
              f"(ожидалось {query['expect_total']}), в странице {len(body['items'])}")
        query_results.append({"id": query["id"], "http": response.status_code,
                              "total": body["total"], "items": len(body["items"]), "ok": ok})
        if not ok:
            problems.append(f"{query['id']}: total={body['total']}, ожидалось {query['expect_total']}")

    print("\nАудит (событие на каждое действие):")
    audit = requests.get(f"{base}/api/v1/audit", params={"page_size": 500}, timeout=30).json()
    actions = requests.get(f"{base}/api/v1/audit/actions", timeout=30).json()
    for action, count in sorted(actions["actions"].items()):
        print(f"  {action:16} {count}")
    statuses = {row["status"] for row in audit["items"] if row["action"] == "analyze_order"}
    for event in events():
        if event["audit_status"] not in statuses:
            problems.append(f"{event['id']}: в аудите нет статуса {event['audit_status']}")

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    (out_dir / f"scenarios-{stamp}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(out_dir / f"scenarios-{stamp}.csv", results, SCENARIO_FIELDS)

    showcase = requests.get(f"{base}/api/v1/orders", params={"page_size": 200}, timeout=30).json()["items"]
    (out_dir / f"showcase-{stamp}.json").write_text(
        json.dumps(showcase, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(out_dir / f"showcase-{stamp}.csv", showcase, SHOWCASE_FIELDS)

    (out_dir / f"audit-{stamp}.json").write_text(
        json.dumps(audit["items"], ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(out_dir / f"audit-{stamp}.csv", audit["items"], AUDIT_FIELDS)

    metrics = requests.get(f"{base}/api/v1/metrics", timeout=30).json()
    (out_dir / f"metrics-{stamp}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nЭкспорт: {out_dir} (JSON + CSV, штамп {stamp})")
    print(f"  сценариев: {len(results)}, из них ручная проверка: "
          f"{sum(1 for row in results if row['needs_review'])}")
    print(f"  записей аудита: {len(audit['items'])}, метрики: "
          f"json_valid_rate={metrics['json_valid_rate']}")

    if problems:
        print(f"\nРАСХОЖДЕНИЙ: {len(problems)}")
        for problem in problems:
            print("  ", problem)
        return 2
    print("\nВсе сценарии совпали со спецификациями. Набор пройден.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
