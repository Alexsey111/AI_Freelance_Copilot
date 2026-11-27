"""Миграции при запуске приложения.

Зачем: `create_all()` создаёт отсутствующие таблицы, но не умеет добавлять колонки
в уже существующую базу. Без этого новая версия программы открывала бы старую базу
и падала на первом запросе к новой колонке. Для окна на Windows это недопустимо:
пользователь не обязан помнить про `python -m migrations.apply`.

In-memory база тестов пропускается: файла нет, применять некуда, а схему создаёт
`create_all()`.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def sqlite_file_of(url: str) -> Path | None:
    """Путь к файлу базы, если это файловая SQLite. Иначе None."""
    if not url.startswith("sqlite"):
        return None
    raw = url.split("///", 1)[-1]
    if not raw or raw == ":memory:" or raw.startswith("file:"):
        return None
    return Path(raw).expanduser()


def apply_migrations(url: str) -> list[str]:
    """Применить недостающие миграции к файловой базе. Ошибку не скрываем, но и не падаем.

    Приложение должно подняться: если миграция не применилась, в лог пишется причина,
    а не происходит молчаливое падение на первом запросе.
    """
    path = sqlite_file_of(url)
    if path is None or not path.exists():
        return []
    try:
        from migrations.apply import apply
    except ImportError:  # запуск не из корня проекта
        logger.warning("миграции не применены: пакет migrations недоступен")
        return []
    try:
        applied = apply(path)
    except Exception as exc:  # noqa: BLE001 - сообщение важнее трейсбека в этом месте
        logger.error("миграции не применены: %s", exc)
        return []
    if applied:
        logger.info("применены миграции: %s", ", ".join(applied))
    return applied
