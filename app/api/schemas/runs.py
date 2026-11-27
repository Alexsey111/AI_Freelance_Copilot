"""Схемы API прогонов (урок 2: у каждого решения есть контекст запуска)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RunStartRequest(BaseModel):
    kind: str = Field(default="analyze_batch", max_length=32, description="Тип прогона")
    model: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=32)
    profile_id: int | None = None
    note: str | None = None


class RunOut(BaseModel):
    id: int
    kind: str
    status: str
    model: str | None = None
    prompt_version: str | None = None
    profile_id: int | None = None
    orders_total: int
    orders_review: int
    review_share: float | None = None
    audit_records: int = 0
    note: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunStartResponse(BaseModel):
    run_id: int
    header: str = "X-Run-Id"
    hint: str = "Передавайте X-Run-Id в запросах анализа, чтобы решения попали в этот прогон."
