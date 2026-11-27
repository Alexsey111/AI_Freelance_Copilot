"""Ставка за час: чем на самом деле измеряется «стоит ли брать заказ».

Абсолютный порог бюджета отсекает не плохие заказы, а мелкие. Четыре заказа по 15 000 ₽
дают 60 000 ₽ и, возможно, спокойную неделю — а фильтр «от 50 000 ₽» не пропустит ни один
из них. И наоборот: 50 000 ₽ за 60 часов работы — это 833 ₽/ч, то есть хуже, чем
15 000 ₽ за 8 часов (1 875 ₽/ч).

Поэтому сравниваем ставку с целевой (`min_rate_rub_per_hour`), а бюджет используем
пессимистично: если указан диапазон «от 15 000 до 20 000», считаем по нижней границе —
клиент платит нижнюю, а не верхнюю.

Без оценки часов ставка не считается: `None`, а не «средние 8 минут» из замера.
Восемь минут — это время разбора карточки, а не работы по заказу.
"""

from __future__ import annotations

from dataclasses import dataclass

BELOW = "below"  # ставка ниже цели: не берём, если только не ради портфолио
OK = "ok"  # ставка в целевой вилке
GREAT = "great"  # сильно выше цели: берём первым
UNKNOWN = "unknown"  # нет часов или бюджета — решает человек

LABELS = {
    BELOW: "ниже цели",
    OK: "в вилке",
    GREAT: "выше цели",
    UNKNOWN: "не оценено",
}


@dataclass(slots=True)
class Rate:
    budget: float | None
    hours: float | None

    @property
    def per_hour(self) -> float | None:
        if self.budget is None or self.hours is None or self.hours <= 0:
            return None
        return round(self.budget / self.hours, 0)


def pessimistic_budget(budget_min: float | None, budget_max: float | None) -> float | None:
    """Нижняя граница — то, что клиент реально заплатит. Диапазон не усредняем."""
    if budget_min is not None:
        return float(budget_min)
    if budget_max is not None:
        return float(budget_max)
    return None


def rate_for(
    budget_min: float | None, budget_max: float | None, hours: float | None
) -> Rate:
    return Rate(budget=pessimistic_budget(budget_min, budget_max), hours=hours)


def verdict(rate: Rate, *, min_rate_rub_per_hour: float = 1_500, great_factor: float = 2.0) -> str:
    per_hour = rate.per_hour
    if per_hour is None:
        return UNKNOWN
    if per_hour < min_rate_rub_per_hour:
        return BELOW
    if per_hour >= min_rate_rub_per_hour * great_factor:
        return GREAT
    return OK


def orders_per_week(
    hours: float | None, *, available_hours_per_week: float = 45.0
) -> int | None:
    """Сколько таких заказов помещается в неделю. Отвечает на «4 по 15 000 — это сколько»."""
    if hours is None or hours <= 0:
        return None
    return int(available_hours_per_week // hours)
