"""Unit: два режима порога — жёсткий и набор на неделю (вопрос 6, финал).

Главный пример — тот, из-за которого всё началось: четыре-пять заказов по 15 000 ₽.
В жёстком режиме порог профиля 50 000 ₽ их не пропускает вообще; в режиме набора
неделя из пяти таких заказов даёт 75 000 ₽ и 40 часов из 45 — и это нормальная неделя.

Второе, что проверяется: окно меряется часами, а не рублями, и мелкий заказ ниже ставки
берётся только как добивка простоя, а не «потому что бюджет всё равно наберётся».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.portfolio import (
    ADMIT,
    FILLER,
    HARD,
    PORTFOLIO,
    SKIP,
    Load,
    decide,
    week_of,
)
from app.domain.rate import rate_for

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # пятница


def _load(hours: float = 0.0, money: float = 0.0) -> Load:
    return Load(hours=hours, money=money)


def _decide(
    budget,
    hours,
    load,
    *,
    mode=PORTFOLIO,
    deadline=None,
    capacity=45.0,
    target=75_000,
    floor=50_000,
):
    return decide(
        rate_for(budget, None, hours),
        hours,
        load,
        window=week_of(deadline, now=NOW),
        capacity_hours=capacity,
        target_week_rub=target,
        budget_floor_rub=floor,
        mode=mode,
    )


def test_hard_mode_rejects_small_orders_regardless_of_week():
    """Ставка 1 875 ₽/ч высокая, но порог профиля по сумме её всё равно режет."""
    decision = _decide(15_000, 8, _load(), mode=HARD)
    assert decision.action == SKIP
    assert "ниже порога профиля" in decision.reason


def test_hard_mode_admits_large_order_if_hours_fit():
    decision = _decide(60_000, 20, _load(), mode=HARD)
    assert decision.action == ADMIT


def test_portfolio_mode_admits_five_small_orders_instead_of_rejecting_all():
    """Пять заказов по 15 000 ₽ за 8 часов — 75 000 ₽ и 40 часов: неделя набрана."""
    load = _load()
    actions = []
    for _ in range(5):
        decision = _decide(15_000, 8, load)
        actions.append(decision.action)
        if decision.action != SKIP:
            load = Load(hours=load.hours + 8, money=load.money + 15_000)
    assert actions == [ADMIT] * 5
    assert load.hours == 40
    assert load.money == 75_000


def test_sixth_order_does_not_fit_in_the_week():
    decision = _decide(15_000, 8, _load(hours=40, money=75_000))
    assert decision.action == SKIP
    assert "осталось 5 ч" in decision.reason


def test_low_rate_order_is_only_filler():
    """10 000 ₽ за 8 часов = 1 250 ₽/ч: добивка пустой недели, но не набранной."""
    assert _decide(10_000, 8, _load()).action == FILLER
    # 70 000 + 10 000 = 80 000 > цели недели: добивка уже не нужна.
    assert _decide(10_000, 8, _load(hours=32, money=70_000)).action == SKIP


def test_hours_are_the_limit_not_money():
    """Даже очень дорогой заказ не берём, если часов в неделе не осталось."""
    decision = _decide(200_000, 20, _load(hours=30, money=0))
    assert decision.action == SKIP


def test_missing_hours_means_skip_not_guess():
    decision = decide(
        rate_for(50_000, None, None),
        None,
        _load(),
        window=week_of(None, now=NOW),
    )
    assert decision.action == SKIP
    assert "Нет оценки часов" in decision.reason


@pytest.mark.parametrize(
    ("deadline", "from_deadline"),
    [(None, False), (NOW + timedelta(days=3), True)],
)
def test_window_is_week_of_deadline_or_rolling(deadline, from_deadline):
    window = week_of(deadline, now=NOW)
    assert window.from_deadline is from_deadline
    assert window.days == 7


def test_window_starts_monday_for_deadline():
    window = week_of(NOW + timedelta(days=1), now=NOW)  # суббота -> неделя с понедельника
    assert window.start.weekday() == 0
    assert window.start <= NOW + timedelta(days=1) < window.end
