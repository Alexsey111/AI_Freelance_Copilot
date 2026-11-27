"""Сбор заказов с площадок: один прогон — одна страница, без чудес.

    python scripts/parse_sources.py --source flru --pages 2
    python scripts/parse_sources.py --source all --limit 30 --dry-run

Что делает: скачивает ленту, разбирает карточки, кладёт новые заказы в базу и обновляет
счётчики у уже известных. Никакого ИИ здесь нет: прогон не тратит денег на модель.

Что не делает: не откликается. Отклик остаётся за человеком — на биржах он платный и
почти везде автоматически запрещён правилами.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.infrastructure.database.database import Database  # noqa: E402
from app.infrastructure.database.repositories.order_repository import (  # noqa: E402
    OrderRepository,
)
from app.infrastructure.sources.fetch import SourceUnavailable  # noqa: E402
from app.infrastructure.sources.ingest import IngestStats, ingest_orders  # noqa: E402
from app.infrastructure.sources.platform_sources import SOURCES, build_source  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сбор заказов с площадок")
    parser.add_argument(
        "--source",
        default="all",
        choices=[*SOURCES, "all"],
        help="какие площадки опрашивать (по умолчанию все доступные)",
    )
    parser.add_argument("--pages", type=int, default=1, help="сколько страниц ленты брать")
    parser.add_argument("--limit", type=int, default=None, help="остановиться на N заказах")
    parser.add_argument("--delay", type=float, default=1.5, help="пауза между страницами, с")
    parser.add_argument("--dry-run", action="store_true", help="разобрать, но не писать в базу")
    parser.add_argument("--json", action="store_true", help="вывести отчёт в JSON")
    return parser.parse_args()


def run_source(key: str, args: argparse.Namespace) -> tuple[list, SourceUnavailable | None]:
    source = build_source(key, pages=args.pages, limit=args.limit, delay=args.delay)
    try:
        return asyncio.run(source.fetch_orders()), None
    except SourceUnavailable as error:
        return [], error


def main() -> int:
    args = parse_args()
    keys = list(SOURCES) if args.source == "all" else [args.source]
    settings = get_settings()
    database = Database(settings.database_url)
    report: dict[str, dict] = {}

    try:
        for key in keys:
            orders, error = run_source(key, args)
            if error is not None:
                report[key] = {"available": False, "reason": str(error)}
                continue
            if args.dry_run:
                report[key] = {
                    "available": True,
                    "fetched": len(orders),
                    "written": False,
                    "sample": [
                        {
                            "id": item.external_id,
                            "title": item.title[:70],
                            "budget": item.budget_min,
                            "views": item.views,
                            "responses": item.responses,
                        }
                        for item in orders[:5]
                    ],
                }
                continue
            with database.session() as session:
                stats: IngestStats = ingest_orders(orders, OrderRepository(session))
                session.commit()
            report[key] = {"available": True, **stats.as_dict()}
    finally:
        database.dispose()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    for key, data in report.items():
        if not data.get("available", False):
            print(f"{key:14} недоступно: {data['reason']}")
            continue
        if data.get("written") is False:
            print(f"{key:14} разобрано {data['fetched']} заказов (dry-run, в базу не писали)")
            for item in data["sample"]:
                print(
                    f"   - #{item['id']} {item['title']} | бюджет {item['budget']} | "
                    f"просмотры {item['views']} | откликов {item['responses']}"
                )
            continue
        print(
            f"{key:14} скачано {data['fetched']:3} | новых {data['created']:3} | "
            f"обновлено {data['updated']:3} | пропущено {data['skipped']}"
        )
        for error in data.get("errors", [])[:5]:
            print(f"   ! {error}")
    print()
    print("Отклики не отправлялись: это работа человека, система только собирает ленту.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
