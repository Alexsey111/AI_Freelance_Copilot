"""Демонстрация прогона целиком: начать прогон, разобрать пачку, закрыть, показать числа.

Работает на КОПИИ базы и на mock-провайдере: денег не тратит, данные демо-базы
(в том числе `data/live.db`) не меняет. Цель --- проверить, что связка
«прогон -> решения -> аудит -> итог» работает на живом приложении, а не только в тестах.

Запуск:
    ./.venv/Scripts/python.exe scripts/demo_run_tracking.py
    ./.venv/Scripts/python.exe scripts/demo_run_tracking.py --db data/live.db --orders 5
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

RUN_HEADERS = "X-Run-Id"


def main() -> int:
    parser = argparse.ArgumentParser(description="Демо: прогон на копии базы с mock-провайдером")
    parser.add_argument("--db", default="data/live.db", help="база-источник (копируется)")
    parser.add_argument("--orders", type=int, default=5, help="сколько заказов разобрать")
    parser.add_argument("--copy", default="data/run-demo.db", help="куда положить копию")
    args = parser.parse_args()

    source = ROOT / args.db
    target = ROOT / args.copy
    if not source.exists():
        print(f"Нет базы {source}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{target.as_posix()}",
        llm_provider="mock",
        min_description_chars=40,
    )
    client = TestClient(create_app(settings))
    client.__enter__()
    try:
        run_id = client.post(
            "/api/v1/runs",
            json={"kind": "analyze_batch", "model": "mock", "prompt_version": "v1"},
        ).json()["run_id"]
        print(f"Прогон #{run_id} на копии {target.name}")

        orders = client.get("/api/v1/orders", params={"page_size": args.orders}).json()["items"]
        for item in orders:
            response = client.post(
                f"/api/v1/orders/{item['id']}/analyze",
                json={},
                headers={RUN_HEADERS: str(run_id)},
            )
            if response.status_code != 200:
                print(f"  заказ #{item['id']}: {response.status_code} {response.text[:120]}")
                continue
            body = response.json()
            print(
                f"  заказ #{item['id']}: {body['result']['recommendation']} "
                f"(review={body['result']['needs_review']})"
            )

        finished = client.post(f"/api/v1/runs/{run_id}/finish").json()
        print(
            f"Итог прогона: решений {finished['orders_total']}, "
            f"к человеку {finished['orders_review']} "
            f"({finished['review_share']}), записей аудита {finished['audit_records']}"
        )
    finally:
        client.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
