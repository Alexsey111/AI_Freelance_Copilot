"""Схемы ИИ-анализа и ручной проверки (ТЗ §11, §12, §25)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.analysis import AnalysisResult, Recommendation


class AnalyzeRequest(BaseModel):
    """Тело POST /api/v1/orders/{order_id}/analyze (ТЗ §11)."""

    model_config = ConfigDict(extra="forbid")

    profile_id: int | None = Field(
        default=None,
        description="Профиль исполнителя. Если не указан --- берётся активный профиль",
    )
    force: bool = Field(
        default=False,
        description="Перезапустить анализ, даже если он уже был (по умолчанию тоже перезапускает, "
        "флаг оставлен для явности в UI)",
    )


class AnalysisResultOut(BaseModel):
    """Результат анализа строго по схеме ТЗ §12."""

    match_score: float | None
    recommendation: Recommendation
    reason: str
    matched_skills: list[str]
    missing_skills: list[str]
    draft_reply: str | None
    needs_review: bool
    review_reason: str | None

    @classmethod
    def from_domain(cls, result: AnalysisResult) -> AnalysisResultOut:
        return cls(**result.model_dump())


class AnalysisSummaryOut(BaseModel):
    """Краткая сводка последнего анализа --- для витрины."""

    id: int
    match_score: float | None = None
    recommendation: str
    needs_review: bool
    review_reason: str | None = None
    review_status: str | None = None
    created_at: datetime | None = None


class AnalysisOut(BaseModel):
    """Полная запись анализа (карточка заказа, экран проверки, аудит)."""

    id: int
    order_id: int
    profile_id: int
    match_score: float | None = None
    recommendation: str
    reason: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    draft_reply: str | None = None
    needs_review: bool = False
    review_reason: str | None = None
    review_status: str | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
    raw_output: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    error: str | None = None
    created_at: datetime | None = None


class AnalyzeResponse(BaseModel):
    """Ответ POST /api/v1/orders/{order_id}/analyze.

    Поле result --- ровно та схема, что требует ТЗ §12. Остальное --- служебное,
    чтобы UI мог показать, куда заказ попал и сколько это заняло.
    """

    order_id: int
    order_status: str
    analysis_id: int
    duration_ms: int
    provider: str
    model: str
    audit_status: str
    result: AnalysisResultOut


class ReviewQueueItemOut(BaseModel):
    """Элемент очереди "Требуют проверки" (ТЗ §25)."""

    analysis_id: int
    order_id: int
    order_title: str
    order_status: str
    match_score: float | None = None
    recommendation: str
    review_reason: str | None = None
    review_status: str | None = None
    created_at: datetime | None = None


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItemOut]
    total: int
    page: int
    page_size: int


class ReviewDecisionRequest(BaseModel):
    """Тело POST /api/v1/analyses/{analysis_id}/review."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(description="approved | rejected")
    comment: str | None = Field(default=None, max_length=2000)


class ReviewDecisionResponse(BaseModel):
    analysis_id: int
    order_id: int
    review_status: str
    order_status: str
    review_comment: str | None = None
    reviewed_at: datetime | None = None
