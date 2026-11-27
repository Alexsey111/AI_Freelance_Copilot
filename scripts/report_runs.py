"""Три вопроса к базе из урока 2 --- ответ числами, а не словами.

Запросы:
  1) доля решений, ушедших человеку, по прогонам;
  2) объём и длительность по прогонам (стоимость в базе пока не хранится ---
     она приходит из `scripts/measure_cost.py`; это открытый пункт в gaps.md);
  3) заказы, пришедшие повторно (один бизнес-ключ --- две строки).

Запуск:
    ./.venv/Scripts/python.exe scripts/report_runs.py --db data/live.db
    ./.venv/Scripts/python.exe scripts/report_runs.py --db data/live.db --write docs/урок2-отчёт.md
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

QUERY_REVIEW_SHARE = """
SELECT
    CASE WHEN a.run_id IS NULL THEN 'без прогона' ELSE 'прогон ' || a.run_id END AS run_group,
    COUNT(*)                                   AS decisions,
    SUM(CASE WHEN a.needs_review THEN 1 ELSE 0 END) AS to_human,
    ROUND(100.0 * SUM(CASE WHEN a.needs_review THEN 1 ELSE 0 END) / COUNT(*), 1) AS share_pct
FROM analyses a
GROUP BY a.run_id
ORDER BY a.run_id
"""

QUERY_RUN_COST = """
SELECT
    r.id                                        AS run_id,
    r.kind,
    r.model,
    r.prompt_version,
    r.status,
    r.orders_total,
    r.orders_review,
    (SELECT COUNT(*) FROM audit_runs au WHERE au.run_id = r.id) AS audit_records,
    (SELECT CAST(ROUND(AVG(au.duration_ms)) AS INTEGER) FROM audit_runs au WHERE au.run_id = r.id) AS avg_ms,
    r.started_at,
    r.finished_at
FROM runs r
ORDER BY r.id
"""

QUERY_DUPLICATES = """
SELECT o.source, o.external_id, COUNT(*) AS copies, GROUP_CONCAT(o.id) AS order_ids
FROM orders o
WHERE o.external_id IS NOT NULL
GROUP BY o.source, o.external_id
HAVING COUNT(*) > 1
ORDER BY copies DESC, o.source
"""


def _table(headers: list[str], rows: list[tuple]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join("" if value is None else str(value) for value in row) + " |")
    return lines


def _rows(cursor: sqlite3.Cursor) -> list[tuple]:
    return [tuple(row) for row in cursor.fetchall()]


def build_report(db: Path) -> str:
    conn = sqlite3.connect(db)
    try:
        share = _rows(conn.execute(QUERY_REVIEW_SHARE))
        runs = _rows(conn.execute(QUERY_RUN_COST))
        duplicates = _rows(conn.execute(QUERY_DUPLICATES))
        totals = conn.execute(
            "SELECT (SELECT COUNT(*) FROM orders), (SELECT COUNT(*) FROM analyses), "
            "(SELECT COUNT(*) FROM audit_runs), (SELECT COUNT(*) FROM runs)"
        ).fetchone()
    finally:
        conn.close()

    lines = [
        "# Урок 2. Отчёт по базе: три вопроса и что они показывают",
        "",
        f"База: `{db.name}`. Снято {datetime.now(UTC).strftime('%d.%m.%Y %H:%M')} UTC.",
        f"Строк: заказов — {totals[0]}, решений — {totals[1]}, записей аудита — {totals[2]}, "
        f"прогонов — {totals[3]}.",
        "",
        "## 1. Доля решений, ушедших человеку, по прогонам",
        "",
    ]
    lines += _table(["прогон", "решений", "к человеку", "доля, %"], share)
    lines += [
        "",
        "Если все решения лежат в строке «без прогона», значит прогон ещё не стал единицей "
        "учёта: числа есть, а условий запуска (модель, версия промпта, профиль) у них нет.",
        "",
        "## 2. Объём и длительность по прогонам",
        "",
    ]
    if runs:
        lines += _table(
            [
                "id",
                "тип",
                "модель",
                "промпт",
                "статус",
                "решений",
                "к человеку",
                "аудит",
                "ср. мс",
                "начат",
                "закрыт",
            ],
            runs,
        )
        lines += [
            "",
            "Стоимость прогона в базе не хранится: провайдерский usage доступен только внутри "
            "вызова, поэтому рубли считает `scripts/measure_cost.py` (39/155 ₽ за 1М токенов, "
            "20 заказов = 1,37 ₽). Это открытый пункт: чтобы стоимость была полем прогона, "
            "её надо писать при разборе, а не мерить снаружи.",
        ]
    else:
        lines += ["Прогонов нет: до миграции 0001 это понятие отсутствовало в схеме."]
    lines += ["", "## 3. Заказы, пришедшие повторно (по бизнес-ключу)", ""]
    if duplicates:
        lines += _table(["источник", "external_id", "копий", "id заказов"], duplicates)
    else:
        lines += [
            "Повторов нет: по (`source`, `external_id`) каждая пара уникальна. "
            "Именно этот запрос должен возвращать ноль после повторного прогона — "
            "если он вернёт строки, идемпотентность записи сломана.",
        ]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Отчёт по трём вопросам урока 2")
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
