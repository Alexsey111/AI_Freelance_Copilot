"""Unit: конкуренция по карточке заказа (урок 2, вопрос 5 — вторая половина).

Возраст — прокси. На FL.ru рядом со временем публикации стоит число откликов, и именно
оно решает: 9 ответов за 4 часа и 123 ответа за сутки — одинаково «старые» лишь по часам,
но шансы различаются на порядок. Проверяем вердикт по ответам, скорость их появления
и то, что «нет данных» не превращается в «свободно».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.competition import (
    CROWDED,
    HOPELESS,
    OPEN,
    UNKNOWN,
    measure,
    verdict,
    worth_applying,
)

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)


def _pub(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


@pytest.mark.parametrize(
    ("responses", "expected"),
    [(0, OPEN), (9, OPEN), (10, CROWDED), (19, CROWDED), (20, HOPELESS), (123, HOPELESS)],
)
def test_verdict_by_responses(responses, expected):
    assert verdict(measure(responses, _pub(4), now=NOW)) == expected


def test_missing_responses_is_unknown_not_open():
    competition = measure(None, _pub(4), now=NOW)
    assert verdict(competition) == UNKNOWN
    assert competition.per_hour is None
    assert worth_applying(competition, now=NOW) is None


def test_responses_per_hour_separates_fast_and_slow_orders():
    """9 ответов за 4 часа = 2,25/ч; те же 9 за 20 часов = 0,45/ч — разница в пять раз."""
    fast = measure(9, _pub(4), now=NOW)
    slow = measure(9, _pub(20), now=NOW)
    assert fast.per_hour == 2.25
    assert slow.per_hour == 0.45


def test_zero_hours_does_not_divide_by_zero():
    assert measure(3, NOW, now=NOW).per_hour == 3.0


def test_old_order_with_few_responses_is_still_alive():
    """Возраст вторичен: 24 часа, но всего 2 ответа — заказ ещё живой."""
    competition = measure(2, _pub(30), now=NOW)
    assert worth_applying(competition, now=NOW, dead_hours=24) is False  # возраст решает


def test_worth_applying_respects_both_filters():
    assert worth_applying(measure(3, _pub(2), now=NOW), now=NOW) is True
    assert worth_applying(measure(12, _pub(2), now=NOW), now=NOW) is False
    assert worth_applying(measure(3, _pub(30), now=NOW), now=NOW) is False
