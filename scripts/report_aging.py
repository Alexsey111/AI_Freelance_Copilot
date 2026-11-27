"""Актуальность заказов и долг в очереди: ответ на вопрос 5 урока 2.

Два разных счёта времени:
  * возраст заказа на площадке (`published_at`) — от него зависит, есть ли смысл
    откликаться: к суткам на заказе уже два десятка откликов;
  * возраст в очереди (`queued_at`) — сколько решение ждёт человека, то есть наш долг.

Если `published_at` нет (старые записи, ручной ввод), заказ попадает в «возраст
неизвестен» — а не в «свежий»: иначе отчёт врёт в удобную сторону.

Запуск:
    ./.venv/Scripts/python.exe scripts/report_aging.py --db data/live.db
    ./.venv/Scripts/python.exe scripts/report_aging.py --db data/live.db --write docs/урок2-актуальность.md
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.domain.aging import (  # noqa: E402
    DEAD,
    FRESH,
    LABELS,
    STALE,
    UNKNOWN,
    USABLE,
    age_hours,
    freshness,
)

ORDER_OF_BUCKETS = [FRESH, USABLE, STALE, DEAD, UNKNOWN]


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def build_report(db: Path, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    conn = sqlite3.connect(db)
    try:
        orders = conn.execute(
            "SELECT id, title, status, needs_review, published_at, queued_at, created_at "
            "FROM orders ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    buckets: dict[str, list[tuple]] = {key: [] for key in ORDER_OF_BUCKETS}
    queue: list[tuple] = []
    for order_id, title, status, needs_review, published_at, queued_at, created_at in orders:
        category = freshness(_parse(published_at), now=now)
        buckets[category].append((order_id, title, status, published_at, created_at))
        if needs_review and queued_at:
            queue.append((order_id, title, age_hours(_parse(queued_at), now)))

    lines = [
        "# Урок 2. Актуальность заказов и долг в очереди",
        "",
        f"База: `{db.name}`. Снято {now.strftime('%d.%m.%Y %H:%M')} UTC. Заказов: {len(orders)}.",
        "",
        "## Возраст на площадке (по `published_at`)",
        "",
        "| категория | заказов |",
        "|---|---|",
    ]
    for key in ORDER_OF_BUCKETS:
        lines.append(f"| {LABELS[key]} | {len(buckets[key])} |")

    dead = buckets[DEAD]
    lines += ["", "### Просроченные: смотреть не стоит", ""]
    if dead:
        lines += ["| id | заказ | статус | опубликован |", "|---|---|---|---|"]
        for order_id, title, status, published_at, _created in dead:
            lines.append(f"| {order_id} | {title[:60]} | {status} | {published_at} |")
    else:
        lines.append("Таких нет.")

    lines += ["", "### Возраст неизвестен", ""]
    unknown = buckets[UNKNOWN]
    if unknown:
        lines += [
            f"{len(unknown)} заказов без даты публикации — для них возраст считается от "
            "`created_at` (момента, когда запись завели у нас), и это не то же самое: "
            "заказ мог висеть на бирже сутки до того, как попал в систему.",
        ]
    else:
        lines.append("Все заказы с датой публикации.")

    lines += ["", "## Долг в очереди (по `queued_at`)", ""]
    if queue:
        queue.sort(key=lambda row: row[2] or 0, reverse=True)
        lines += ["| id | заказ | ждёт, ч |", "|---|---|---|"]
        for order_id, title, hours in queue:
            lines.append(f"| {order_id} | {title[:60]} | {hours} |")
    else:
        lines.append("Очередь пуста: ни одно решение не ждёт человека.")

    lines += [
        "",
        "## Правило",
        "",
        "Заказ, опубликованный больше 24 часов назад, в разбор не берём: к этому времени "
        "он либо закрыт, либо собрал отклики. Решение, которое ждёт человека больше "
        "12 часов, — просрочено по нашей вине, а не по вине заказа.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Актуальность заказов и очередь проверки")
    parser.add_argument("--db", required=True)
    parser.add_argument("--write", help="куда сохранить markdown")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"Нет базы {db}")
        return 1
    report = build_report(db)
    print(report)
    if args.write:
        target = Path(args.write)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report, encoding="utf-8")
        print(f"\nСохранено: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
