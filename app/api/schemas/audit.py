"""Схемы журнала аудита и метрик (ТЗ §8, §26, §34)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AuditRunOut(BaseModel):
    id: int
    action: str
    order_id: int | None = None
    input: str | None = None
    output: str | None = None
    status: str
    error: str | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None


class AuditListResponse(BaseModel):
    items: list[AuditRunOut]
    total: int
    page: int
    page_size: int


class EconomyOut(BaseModel):
    """Мини-экономика (ТЗ §33): по умолчанию замер владельца, разбивка ТЗ --- для сравнения."""

    hourly_rate_rub: float
    hourly_rate_hint: str = ""
    money_formula: str = ""

    manual_order_minutes: int
    assisted_order_minutes: int
    manual_order_minutes_spec: int = 13
    manual_time_source: str = ""
    assisted_time_source: str = ""

    manual_100_minutes: int
    assisted_100_minutes: int
    manual_100_hours: float
    assisted_100_hours: float
    saved_minutes_per_100: int
    saved_hours_per_100: float
    saved_money_rub_per_100: float

    # То же самое по разбивке из ТЗ §33 (13 мин вместо замера 8 мин) --- чтобы было видно,
    # насколько требование расходится с фактическими данными владельца.
    saved_minutes_per_100_spec: int = 1000
    saved_money_rub_per_100_spec: float = 25000.0

    measured_avg_analysis_seconds: float | None = None


class MetricsOut(BaseModel):
    """Метрики ТЗ §34. null означает "нет данных", а не ноль."""

    orders_total: int
    orders_by_status: dict[str, int] = Field(default_factory=dict)
    orders_recommended: int = 0
    orders_needs_review: int = 0

    analyses_total: int = 0
    analyses_needs_review: int = 0
    analyses_errors: int = 0
    analyses_by_recommendation: dict[str, int] = Field(default_factory=dict)
    avg_match_score: float | None = None

    audit_total: int = 0
    audit_by_status: dict[str, int] = Field(default_factory=dict)
    audit_by_action: dict[str, int] = Field(default_factory=dict)
    audit_errors: int = 0
    avg_analyze_duration_ms: float | None = None
    max_analyze_duration_ms: int | None = None

    json_valid_rate: float | None = None
    review_share: float | None = None
    apply_share: float | None = None

    economy: EconomyOut | None = None


class ProviderOut(BaseModel):
    """Состояние LLM-провайдера (для UI, чтобы человек видел, чем он работает)."""

    name: str
    model: str
    prompt_version: str
    is_live: bool = Field(description="True --- реальный внешний провайдер (тратит деньги)")
    warning: str | None = None


class HealthOut(BaseModel):
    status: str
    app_env: str
    database: str
    api_version: str
    provider: ProviderOut
