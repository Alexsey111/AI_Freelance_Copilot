"""Unit: возраст заказа и возраст в очереди (урок 2, вопрос 5).

Проверяется не «функция вернула строку», а правило: заказ, опубликованный сутки назад,
в разбор не берётся; отсутствие даты публикации — «возраст неизвестен», а не «свежий»
(иначе отчёт врёт в удобную сторону); будущая дата не даёт отрицательного возраста.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.aging import (
    DEAD,
    FRESH,
    STALE,
    UNKNOWN,
    USABLE,
    age_hours,
    freshness,
    is_worth_looking,
    queue_overdue_hours,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def _ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (0.5, FRESH),
        (5.99, FRESH),
        (6.0, USABLE),
        (11.9, USABLE),
        (12.0, STALE),
        (23.9, STALE),
        (24.0, DEAD),
        (72.0, DEAD),
    ],
)
def test_freshness_buckets(hours, expected):
    assert freshness(_ago(hours), now=NOW) == expected


def test_missing_date_is_unknown_not_fresh():
    assert freshness(None, now=NOW) == UNKNOWN
    assert age_hours(None, NOW) is None
    assert is_worth_looking(None, now=NOW) is None


def test_future_date_is_zero_age_not_negative():
    future = NOW + timedelta(hours=3)
    assert age_hours(future, NOW) == 0.0
    assert freshness(future, now=NOW) == FRESH


def test_naive_datetime_is_read_as_utc():
    naive = datetime(2026, 11, 27, 6, 0)  # 6 часов назад, без tzinfo
    assert freshness(naive, now=NOW) == USABLE


def test_worth_looking_uses_dead_threshold():
    assert is_worth_looking(_ago(23.9), now=NOW) is True
    assert is_worth_looking(_ago(24.0), now=NOW) is False


def test_thresholds_come_from_arguments_not_constants():
    """Тот же заказ при dead_hours=12 уже не берём: порог задаётся, а не зашит."""
    moment = _ago(14)
    assert is_worth_looking(moment, now=NOW) is True
    assert is_worth_looking(moment, now=NOW, dead_hours=12) is False


def test_queue_overdue_hours():
    assert queue_overdue_hours(_ago(30), now=NOW) == 30.0
    assert queue_overdue_hours(None, now=NOW) is None
