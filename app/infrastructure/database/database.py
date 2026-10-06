"""Инфраструктурный слой доступа к БД.

Repository Layer выше не знает, SQLite там или PostgreSQL: он работает через Session.
Замена SQLite -> PostgreSQL делается здесь, бизнес-логика не меняется (ТЗ §31).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей."""


def _is_memory_sqlite(url: str) -> bool:
    """In-memory база (в т.ч. sqlite:// или sqlite+pysqlite:///:memory:)."""
    if not url.startswith("sqlite") or ":memory:" in url:
        return ":memory:" in url
    return url.split("///", 1)[-1] in {"", "sqlite://"}


def _ensure_sqlite_directory(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    raw_path = url.split("///", 1)[-1]
    if not raw_path or raw_path == ":memory:" or raw_path.startswith("file:"):
        return
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


class Database:
    """Обёртка над SQLAlchemy engine/sessionmaker."""

    def __init__(self, url: str, echo: bool = False) -> None:
        _ensure_sqlite_directory(url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine_kwargs: dict = {"echo": echo, "future": True, "connect_args": connect_args}
        if _is_memory_sqlite(url):
            # In-memory SQLite живёт внутри соединения: без StaticPool каждая сессия
            # получила бы свою пустую базу. Нужно для тестов.
            from sqlalchemy.pool import StaticPool

            engine_kwargs["poolclass"] = StaticPool
        self.url = url
        self.engine: Engine = create_engine(url, **engine_kwargs)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )
        if url.startswith("sqlite"):
            self._enable_sqlite_foreign_keys()

    def _enable_sqlite_foreign_keys(self) -> None:
        @event.listens_for(self.engine, "connect")
        def _set_pragma(dbapi_connection, _connection_record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def create_all(self) -> None:
        from app.infrastructure.database import models  # noqa: F401  (регистрация моделей)

        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    def new_session(self) -> Session:
        return self._session_factory()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
