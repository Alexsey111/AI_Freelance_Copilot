"""Журнал аудита (ТЗ §8, §29.4): любой запуск пишется, даже если он упал."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.models.audit import AuditRun, AuditStatus

# Поля, которые маскируются, если случайно попадут в лог (ключи не логируем никогда).
SENSITIVE_KEYS = {"api_key", "openai_api_key", "llm_api_key", "authorization", "password", "token"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if key.lower() in SENSITIVE_KEYS else _sanitize(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and len(value) > 4000:
        return value[:4000] + "...[обрезано]"
    return value


def to_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(_sanitize(value), ensure_ascii=False, default=str)


@dataclass(slots=True)
class AuditTimer:
    """Замер длительности операции (ТЗ §34: среднее время AI-анализа)."""

    started_at: datetime

    @classmethod
    def start(cls) -> AuditTimer:
        return cls(started_at=datetime.now(UTC))

    @property
    def duration_ms(self) -> int:
        delta = datetime.now(UTC) - self.started_at
        return int(delta.total_seconds() * 1000)


class AuditService:
    """Запись в журнал аудита. Единственный путь попадания данных в таблицу audit_runs."""

    def __init__(self, audit_repository) -> None:
        self.audit = audit_repository

    def record(
        self,
        action: str,
        *,
        input_payload: Any = None,
        output_payload: Any = None,
        status: str = AuditStatus.SUCCESS.value,
        error: str | None = None,
        duration_ms: int | None = None,
        order_id: int | None = None,
    ) -> AuditRun:
        return self.audit.add(
            AuditRun(
                action=action,
                order_id=order_id,
                input=to_json(input_payload),
                output=to_json(output_payload),
                status=status,
                error=error,
                duration_ms=duration_ms,
            )
        )
