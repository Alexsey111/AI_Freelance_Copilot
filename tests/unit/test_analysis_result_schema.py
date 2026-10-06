"""Unit: строгая схема AnalysisResult (ТЗ §12) и правила согласованности."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.analysis import AnalysisResult, Recommendation


def _valid(**overrides):
    payload = {
        "match_score": 0.87,
        "recommendation": "apply",
        "reason": "Заказ соответствует опыту Python и AI-интеграций",
        "matched_skills": ["Python", "LLM", "API", "Telegram"],
        "missing_skills": [],
        "draft_reply": "Здравствуйте! Готов обсудить проект.",
        "needs_review": False,
        "review_reason": None,
    }
    payload.update(overrides)
    return payload


def test_valid_result_parses():
    result = AnalysisResult.model_validate(_valid())
    assert result.recommendation is Recommendation.APPLY
    assert result.match_score == 0.87


def test_needs_review_requires_reason():
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(
            _valid(needs_review=True, recommendation="review", draft_reply=None, review_reason=None)
        )


def test_no_review_requires_null_reason():
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(_valid(review_reason="что-то не так"))


def test_review_result_must_be_safe():
    """Результат, ушедший человеку, не содержит выдуманного скора и готового отклика."""
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(
            _valid(
                recommendation="review",
                needs_review=True,
                review_reason="нет бюджета",
                draft_reply="Здравствуйте, отправляю отклик",
            )
        )
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(
            _valid(recommendation="review", needs_review=True, review_reason="нет бюджета")
        )
    ok = AnalysisResult.model_validate(
        _valid(
            match_score=None,
            recommendation="review",
            needs_review=True,
            draft_reply=None,
            review_reason="не указан бюджет",
        )
    )
    assert ok.draft_reply is None and ok.match_score is None


def test_review_recommendation_requires_needs_review():
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(
            _valid(recommendation="review", needs_review=False, draft_reply=None)
        )


@pytest.mark.parametrize("score", [-0.1, 1.5, "ноль"])
def test_match_score_bounds(score):
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(_valid(match_score=score))


def test_extra_fields_rejected():
    """Модель не может протащить лишние поля вроде send_message (ТЗ §15)."""
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(_valid(send_message=True))


def test_fallback_is_safe():
    fallback = AnalysisResult.review_fallback("LLM timeout", "Результат ИИ недоступен")
    assert fallback.needs_review is True
    assert fallback.review_reason == "LLM timeout"
    assert fallback.draft_reply is None
    assert fallback.match_score is None
    assert fallback.recommendation is Recommendation.REVIEW
