"""Модель журнала аудита (ТЗ §8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AuditStatus(str, Enum):
    """Статус запуска. SUCCESS --- всё хорошо, REVIEW --- ушло человеку,
    ERROR --- ошибка (в том числе ошибка LLM или невалидный ответ модели).
    """

    SUCCESS = "success"
    REVIEW = "review"
    ERROR = "error"


@dataclass(slots=True)
class AuditRun:
    """Одна запись журнала аудита."""

    id: int | None = None
    action: str = ""
    order_id: int | None = None
    input: str | None = None
    output: str | None = None
    status: str = AuditStatus.SUCCESS.value
    error: str | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None
