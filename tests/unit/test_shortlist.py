"""Подборка под профиль: список с причиной, а не «рейтинг ИИ».

Что здесь важно проверить:

1. Совпадение навыков поднимает заказ и называется словами.
2. Бюджет ниже порога профиля — сразу отказ, даже если заказ свежий и свободный.
3. Двадцать откликов — отказ: конкуренция важнее возраста.
4. Старше суток — отказ: «позднее 24 ч в ленте».
5. Без совпадения навыков заказ не попадает в «берём» — это не ваша работа.
6. Нет данных — не приговор: заказ уходит в «посмотреть», а не в мусор.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.shortlist import REVIEW, SKIP, TAKE, Thresholds, build_shortlist, evaluate

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
SKILLS = ["Python", "FastAPI", "LLM"]


@dataclass
class FakeOrder:
    id: int
    title: str
    description: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    published_at: datetime | None = None
    responses: int | None = None


def _fit(**kwargs) -> object:
    order = FakeOrder(**kwargs)
    return evaluate(order, skills=SKILLS, thresholds=Thresholds(min_budget_rub=50_000), now=NOW)


def test_skill_match_is_named_in_reason():
    fit = _fit(
        id=1,
        title="Telegram-бот на Python",
        description="Нужен бот с LLM-ответами",
        budget_min=80_000,
        published_at=NOW - timedelta(hours=1),
        responses=3,
    )
    assert fit.verdict == TAKE
    assert fit.matched_skills == ["Python", "LLM"]
    assert any("в тексте: Python, LLM" in reason for reason in fit.reasons)


def test_budget_below_threshold_is_refused():
    fit = _fit(id=2, title="Правки на Python", budget_min=3_000, published_at=NOW, responses=1)
    assert fit.verdict == SKIP
    assert any("ниже порога" in reason for reason in fit.reasons)


def test_too_many_responses_is_refused():
    fit = _fit(
        id=3,
        title="Python-скрипт",
        budget_min=90_000,
        published_at=NOW - timedelta(hours=1),
        responses=174,
    )
    assert fit.verdict == SKIP
    assert any("174 откликов" in reason for reason in fit.reasons)


def test_stale_order_is_refused():
    fit = _fit(
        id=4,
        title="Python-парсер",
        budget_min=90_000,
        published_at=NOW - timedelta(hours=30),
        responses=2,
    )
    assert fit.verdict == SKIP
    assert any("старше" in reason for reason in fit.reasons)


def test_no_skill_match_is_never_take():
    fit = _fit(
        id=5,
        title="Написать 4 отзыва",
        description="Тексты для маркетплейса",
        budget_min=200_000,
        published_at=NOW,
        responses=1,
    )
    assert fit.verdict == REVIEW
    assert any("ни одного вашего навыка" in reason for reason in fit.reasons)


def test_missing_data_goes_to_review_not_trash():
    fit = _fit(id=6, title="Нужен специалист", description="Python и API")
    assert fit.verdict == REVIEW
    assert any("бюджет не указан" in reason for reason in fit.reasons)
    assert any("возраст неизвестен" in reason for reason in fit.reasons)


def test_shortlist_sorts_take_first_and_hides_skips():
    fits = build_shortlist(
        [
            FakeOrder(id=10, title="Правки", budget_min=1_000, published_at=NOW, responses=1),
            FakeOrder(
                id=11,
                title="Python-бот",
                budget_min=120_000,
                published_at=NOW - timedelta(hours=1),
                responses=2,
            ),
        ],
        skills=SKILLS,
        thresholds=Thresholds(min_budget_rub=50_000),
        now=NOW,
    )
    assert [fit.order_id for fit in fits] == [11]
    assert fits[0].verdict == TAKE
