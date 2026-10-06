"""Unit: детерминированный расчёт соответствия (ТЗ §32: расчёт match score)."""

from __future__ import annotations

from app.domain.matching import compute_match_score, extract_skills, match_order_to_profile

PROFILE_SKILLS = ["Python", "FastAPI", "PostgreSQL", "Docker", "LLM", "REST API", "AI automation"]


def test_extract_skills_finds_technologies():
    text = "Нужен Telegram-бот на Python с LLM и интеграцией по REST API, деплой в Docker"
    found = extract_skills(text)
    assert {"Python", "LLM", "REST API", "Docker", "Telegram"} <= set(found)


def test_extract_skills_no_false_positive_on_substring():
    """Латинские сокращения ищутся по границам слова: 'API' не должно ловиться в 'capital'."""
    assert "REST API" not in extract_skills("Мы работаем с capital management")


def test_score_is_coverage_of_order_requirements():
    assert compute_match_score(["Python", "FastAPI"], PROFILE_SKILLS) == 1.0
    assert compute_match_score(["Python", "Kubernetes"], PROFILE_SKILLS) == 0.5
    assert compute_match_score(["1C", "Excel"], PROFILE_SKILLS) == 0.0


def test_score_returns_none_without_data():
    """Нет данных --- это None, а не 0: 'не смогли посчитать' != 'ничего не совпало'."""
    assert compute_match_score([], PROFILE_SKILLS) is None
    assert compute_match_score(["Python"], []) is None


def test_match_outcome_lists_skills():
    outcome = match_order_to_profile(["Python", "Kubernetes"], PROFILE_SKILLS)
    assert outcome.matched_skills == ["Python"]
    assert outcome.missing_skills == ["Kubernetes"]
    assert outcome.score == 0.5
    assert outcome.is_determined is True


def test_match_undetermined_paths():
    no_order_skills = match_order_to_profile([], PROFILE_SKILLS)
    assert no_order_skills.is_determined is False
    no_profile_skills = match_order_to_profile(["Python"], [])
    assert no_profile_skills.is_determined is False
