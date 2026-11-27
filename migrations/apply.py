"""Применение миграций схемы: файлы `.sql` по порядку + таблица `schema_version`.

Зачем это, если схема и так создаётся при старте (`create_all()`):
create_all умеет только создавать недостающие таблицы. Он не добавляет колонку в
существующую таблицу и не знает, что на живой базе (`data/live.db`, 36 заказов,
117 решений) уже лежит. Добавление `run_id` руками в редакторе БД заканчивается тем,
что тесты зелёные на чистой базе, а данные в другой форме.

Правило: любое изменение схемы — файл с номером в `migrations/`, применяемый этим
скриптом. Скрипт идемпотентен: повторный запуск ничего не делает.

Запуск:
    ./.venv/Scripts/python.exe -m migrations.apply --db data/live.db
    ./.venv/Scripts/python.exe -m migrations.apply --db data/app.db --dry-run
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent
VERSION_TABLE = "schema_version"
# Ошибки «уже применено»: миграция написана на живую базу, где колонка могла появиться
# раньше (например, база создана через create_all уже с новой моделью).
BENIGN_ERRORS = ("duplicate column name", "already exists")


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {VERSION_TABLE} ("
        "version VARCHAR(64) PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    ensure_version_table(conn)
    return {row[0] for row in conn.execute(f"SELECT version FROM {VERSION_TABLE}")}


def split_statements(sql: str) -> list[str]:
    """Разрезает файл на операторы по точке с запятой, не задевая строковые литералы."""
    statements: list[str] = []
    buffer: list[str] = []
    in_string = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'":
            in_string = not in_string
        if char == "-" and not in_string and sql[index : index + 2] == "--":
            newline = sql.find("\n", index)
            index = len(sql) if newline == -1 else newline
            continue
        if char == ";" and not in_string:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def apply(db_path: Path, dry_run: bool = False) -> list[str]:
    """Применяет недостающие миграции. Возвращает список применённых версий."""
    conn = sqlite3.connect(db_path)
    applied: list[str] = []
    try:
        done = applied_versions(conn)
        for path in migration_files():
            version = path.stem
            if version in done:
                continue
            statements = split_statements(path.read_text(encoding="utf-8"))
            if dry_run:
                print(f"[dry-run] {version}: {len(statements)} операторов")
                applied.append(version)
                continue
            print(f"[apply] {version}")
            for statement in statements:
                compact = re.sub(r"\s+", " ", statement).strip()
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if not any(benign in message for benign in BENIGN_ERRORS):
                        raise
                    print(f"  пропущено (уже есть): {compact[:70]}")
            conn.execute(
                f"INSERT INTO {VERSION_TABLE} (version) VALUES (?)",
                (version,),
            )
            conn.commit()
            applied.append(version)
    finally:
        conn.close()
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграции схемы (SQLite)")
    parser.add_argument("--db", required=True, help="путь к файлу базы")
    parser.add_argument("--dry-run", action="store_true", help="только показать план")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists() and not args.dry_run:
        print(f"Нет базы {db_path}. Для новой базы достаточно create_all() при старте.")
        return 1
    applied = apply(db_path, dry_run=args.dry_run)
    if not applied:
        print("Схема актуальна, применять нечего.")
    else:
        print("Применено: " + ", ".join(applied))
    return 0


if __name__ == "__main__":
    sys.exit(main())
