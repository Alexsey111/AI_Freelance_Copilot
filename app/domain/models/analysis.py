"""Результат анализа (ТЗ §7, §12) --- строгая Pydantic-схема.

Принципиальный момент проекта: LLM не возвращает произвольный текст, она возвращает
строго структурированный результат, который валидируется до сохранения в БД.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Recommendation(str, Enum):
    APPLY = "apply"
    SKIP = "skip"
    REVIEW = "review"


class ReviewStatus(str, Enum):
    """Решение человека по записи, попавшей в ручную проверку (ТЗ §25)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AnalysisResult(BaseModel):
    """Строгая схема ответа ИИ (ТЗ §12)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    match_score: float | None = Field(default=None, ge=0.0, le=1.0)
    recommendation: Recommendation
    reason: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    draft_reply: str | None = None
    needs_review: bool
    review_reason: str | None = None

    @model_validator(mode="after")
    def _check_review_consistency(self) -> AnalysisResult:
        """ТЗ §12: needs_review=true -> review_reason обязателен;
        needs_review=false -> review_reason = null.
        """
        if self.needs_review and not (self.review_reason or "").strip():
            raise ValueError("needs_review=true требует непустой review_reason")
        if not self.needs_review and self.review_reason is not None:
            raise ValueError("needs_review=false требует review_reason=null")
        return self

    @model_validator(mode="after")
    def _check_review_is_safe(self) -> AnalysisResult:
        """ТЗ §13/§29: результат, ушедший на ручную проверку, безопасен ---
        без выдуманного скора и без готового к отправке текста.
        """
        if self.needs_review:
            if self.draft_reply is not None:
                raise ValueError("needs_review=true требует draft_reply=null")
            if self.recommendation is not Recommendation.REVIEW:
                raise ValueError("needs_review=true требует recommendation=review")
        if not self.needs_review and self.recommendation is Recommendation.REVIEW:
            raise ValueError("recommendation=review требует needs_review=true")
        return self

    @classmethod
    def review_fallback(cls, review_reason: str, reason: str) -> AnalysisResult:
        """Безопасный результат для случаев §14.2/§14.3/§14.5 (невалидный JSON, ошибка LLM,
        не удалось определить соответствие). Ничего не выдумывает.
        """
        return cls(
            match_score=None,
            recommendation=Recommendation.REVIEW,
            reason=reason,
            matched_skills=[],
            missing_skills=[],
            draft_reply=None,
            needs_review=True,
            review_reason=review_reason,
        )


@dataclass(slots=True)
class Analysis:
    """Сохранённый результат анализа (строка таблицы analyses)."""

    id: int | None = None
    order_id: int | None = None
    profile_id: int | None = None
    match_score: float | None = None
    recommendation: str = Recommendation.REVIEW.value
    reason: str = ""
    matched_skills: list[str] = None  # type: ignore[assignment]
    missing_skills: list[str] = None  # type: ignore[assignment]
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

    def __post_init__(self) -> None:
        if self.matched_skills is None:
            self.matched_skills = []
        if self.missing_skills is None:
            self.missing_skills = []
