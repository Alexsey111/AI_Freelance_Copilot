"""Unit: ставка за час вместо абсолютного бюджета (урок 2, вопрос 6 после правки).

Проверяется главное: порог «от 50 000 ₽» отсекает хорошие мелкие заказы. 15 000 ₽ за 8 часов
дают 1 875 ₽/ч и должны проходить; 50 000 ₽ за 60 часов — 833 ₽/ч и должны отсекаться.
Диапазон бюджета считается по нижней границе; без оценки часов вердикта нет вовсе.
"""

from __future__ import annotations

import pytest

from app.domain.rate import BELOW, GREAT, OK, UNKNOWN, orders_per_week, rate_for, verdict


@pytest.mark.parametrize(
    ("budget", "hours", "expected"),
    [
        (15_000, 8, OK),  # 1 875 ₽/ч — проходит, хотя бюджет ниже 50 000
        (50_000, 60, BELOW),  # 833 ₽/ч — отсекается, хотя бюджет «солидный»
        (12_000, 4, GREAT),  # 3 000 ₽/ч
        (15_000, 30, BELOW),  # 500 ₽/ч
    ],
)
def test_rate_decides_not_budget(budget, hours, expected):
    assert verdict(rate_for(budget, None, hours)) == expected


def test_range_is_judged_by_lower_bound():
    """«От 15 000 до 20 000» — считаем 15 000: клиент платит нижнюю границу."""
    rate = rate_for(15_000, 20_000, 10)
    assert rate.budget == 15_000
    assert rate.per_hour == 1_500


def test_only_upper_bound_is_used_when_no_lower():
    assert rate_for(None, 20_000, 10).budget == 20_000


def test_no_hours_means_no_verdict():
    assert verdict(rate_for(80_000, None, None)) == UNKNOWN
    assert verdict(rate_for(None, None, 8)) == UNKNOWN


def test_zero_hours_does_not_divide_by_zero():
    assert rate_for(10_000, None, 0).per_hour is None
    assert verdict(rate_for(10_000, None, 0)) == UNKNOWN


def test_orders_per_week_answers_the_four_by_15000_question():
    """4 × 15 000 ₽ по 8 часов — это 32 часа из 45 доступных: помещается."""
    assert orders_per_week(8) == 5
    assert orders_per_week(12) == 3
    assert orders_per_week(None) is None
