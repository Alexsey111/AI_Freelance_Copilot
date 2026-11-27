"""Unit: миграция схемы прогонов (урок 2, п.2 практики).

Проверяем не «файл существует», а то, что миграция работает на живой базе:
берём базу со СТАРОЙ схемой (без runs и без run_id), применяем и смотрим, что
данные на месте, а колонки появились. Второй прогон ничего не должен менять.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from migrations.apply import applied_versions, apply, split_statements

LEGACY_SCHEMA = """
CREATE TABLE profiles (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    needs_review BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
);
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    recommendation VARCHAR(16) NOT NULL,
    needs_review BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE audit_runs (
    id INTEGER PRIMARY KEY,
    action VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL
);
INSERT INTO profiles (id, name) VALUES (1, 'Старый профиль');
INSERT INTO orders (id, title, needs_review, created_at)
    VALUES (1, 'Заказ до миграции', 0, '2026-11-01 09:00:00');
INSERT INTO analyses (order_id, recommendation, needs_review, created_at)
    VALUES (1, 'apply', 0, '2026-11-01 10:00:00');
INSERT INTO audit_runs (action, status, created_at)
    VALUES ('analyze_order', 'success', '2026-11-01 10:00:01');
"""


def _legacy_db(tmp_path: Path) -> Path:
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(LEGACY_SCHEMA)
    conn.commit()
    conn.close()
    return db


def _columns(db: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
    finally:
        conn.close()


def _scalar(db: Path, sql: str):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchone()
    finally:
        conn.close()


def _table_names(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_migration_adds_runs_and_run_id_without_losing_data(tmp_path):
    db = _legacy_db(tmp_path)

    applied = apply(db)

    assert applied == ["0001_runs_and_audit", "0002_aging", "0003_backfill_queue", "0004_competition", "0005_rate", "0006_portfolio", "0007_usage", "0008_settings", "0009_time_norms"]
    assert "runs" in _table_names(db)
    assert "run_id" in _columns(db, "analyses")
    assert "run_id" in _columns(db, "audit_runs")
    assert {"published_at", "queued_at", "views", "responses", "estimated_hours"} <= _columns(db, "orders")
    # Старые строки на месте и с run_id = NULL: история не приписывается прогонам.
    assert _scalar(db, "SELECT count(*) FROM analyses") == (1,)
    assert _scalar(db, "SELECT run_id FROM analyses") == (None,)
    assert _scalar(db, "SELECT title FROM orders WHERE id = 1") == ("Заказ до миграции",)


def test_second_run_is_idempotent(tmp_path):
    db = _legacy_db(tmp_path)
    apply(db)

    assert apply(db) == []
    conn = sqlite3.connect(db)
    try:
        versions = list(conn.execute("SELECT version FROM schema_version"))
    finally:
        conn.close()
    assert [v for (v,) in versions] == ["0001_runs_and_audit", "0002_aging", "0003_backfill_queue", "0004_competition", "0005_rate", "0006_portfolio", "0007_usage", "0008_settings", "0009_time_norms"]


def test_migration_survives_schema_created_by_create_all(tmp_path):
    """Свежая база после create_all уже содержит run_id: миграция не должна падать."""
    from app.infrastructure.database.database import Database

    db = tmp_path / "fresh.db"
    database = Database(f"sqlite:///{db.as_posix()}")
    database.create_all()
    database.dispose()

    assert apply(db) == ["0001_runs_and_audit", "0002_aging", "0003_backfill_queue", "0004_competition", "0005_rate", "0006_portfolio", "0007_usage", "0008_settings", "0009_time_norms"]
    assert "run_id" in _columns(db, "analyses")


def test_versions_are_readable_and_statements_split_correctly(tmp_path):
    db = _legacy_db(tmp_path)
    apply(db)
    conn = sqlite3.connect(db)
    try:
        assert applied_versions(conn) == {"0001_runs_and_audit", "0002_aging", "0003_backfill_queue", "0004_competition", "0005_rate", "0006_portfolio", "0007_usage", "0008_settings", "0009_time_norms"}
    finally:
        conn.close()

    # Комментарии и точки с запятой внутри строк не должны разрезать оператор.
    assert split_statements("-- комментарий; с точкой\nSELECT 'a;b';") == ["SELECT 'a;b'"]
