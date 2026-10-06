"""Unit: разбор ответа LLM и обработка невалидного JSON (ТЗ §29.3, §32 особый тест)."""

from __future__ import annotations

import json

import pytest

from app.domain.models.analysis import Recommendation
from app.infrastructure.llm.base import (
    LLMInvalidResponseError,
    extract_json_object,
    parse_analysis_result,
)
from app.infrastructure.llm.mock_adapter import MockProvider


def test_parses_plain_json():
    raw = json.dumps(
        {
            "match_score": 0.87,
            "recommendation": "apply",
            "reason": "ок",
            "matched_skills": ["Python"],
            "missing_skills": [],
            "draft_reply": "Здравствуйте!",
            "needs_review": False,
            "review_reason": None,
        }
    )
    result = parse_analysis_result(raw)
    assert result.recommendation is Recommendation.APPLY


def test_parses_json_inside_markdown_fence():
    raw = '```json\n{"match_score": null, "recommendation": "review", "reason": "нет данных", "matched_skills": [], "missing_skills": [], "draft_reply": null, "needs_review": true, "review_reason": "нет бюджета"}\n```'
    result = parse_analysis_result(raw)
    assert result.needs_review is True
    assert result.review_reason == "нет бюджета"


def test_parses_json_with_surrounding_text():
    raw = 'Вот результат: {"match_score": 0.5, "recommendation": "skip", "reason": "не подходит", "matched_skills": [], "missing_skills": [], "draft_reply": null, "needs_review": false, "review_reason": null} Спасибо!'
    assert parse_analysis_result(raw).recommendation is Recommendation.SKIP


@pytest.mark.parametrize(
    "raw",
    [
        "полный мусор без json",
        "",
        "   ",
        "{не json}",
        "[1, 2, 3]",
        '{"match_score": "много"}',
        '{"recommendation": "apply"}',
    ],
)
def test_invalid_responses_raise(raw):
    with pytest.raises(LLMInvalidResponseError):
        parse_analysis_result(raw)


def test_extract_json_object_requires_object():
    with pytest.raises(LLMInvalidResponseError):
        extract_json_object('{"a": 1')
    assert extract_json_object('{"a": 1}') == {"a": 1}


async def test_mock_provider_bad_json_and_timeout_paths():
    provider = MockProvider(min_description_chars=1)
    from app.domain.models.order import Order
    from app.domain.models.profile import Profile

    profile = Profile(id=1, name="П", skills=["Python"])
    bad = Order(id=1, title="MOCK_BAD_JSON", description="x" * 50, budget_min=1)
    with pytest.raises(LLMInvalidResponseError):
        await provider.analyze_order(bad, profile)

    from app.infrastructure.llm.base import LLMTimeoutError

    slow = Order(id=2, title="MOCK_TIMEOUT", description="y" * 50, budget_min=1)
    with pytest.raises(LLMTimeoutError):
        await provider.analyze_order(slow, profile)


async def test_mock_provider_is_deterministic():
    provider = MockProvider(min_description_chars=10)
    from app.domain.models.order import Order
    from app.domain.models.profile import Profile

    order = Order(
        id=1,
        title="Telegram-бот на Python",
        description="Нужен бот на Python, FastAPI, Docker, LLM, REST API. " * 2,
        budget_min=30000,
    )
    # Профиль покрывает все навыки, которые лексикон находит в заказе
    # (включая Telegram из заголовка), поэтому ожидается полное совпадение.
    profile = Profile(
        id=1, name="П", skills=["Python", "FastAPI", "Docker", "LLM", "REST API", "Telegram"]
    )
    first = await provider.analyze_order(order, profile)
    second = await provider.analyze_order(order, profile)
    assert first.model_dump() == second.model_dump()
    assert first.match_score == 1.0
    assert first.recommendation is Recommendation.APPLY
