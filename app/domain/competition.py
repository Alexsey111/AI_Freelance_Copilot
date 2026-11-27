"""Конкуренция по заказу: сколько откликов уже собрано и с какой скоростью.

Возраст заказа — прокси, а не измерение. На FL.ru рядом с «Заказ 3 часа 57 минут назад»
стоит «9 ответов», а у соседнего, опубликованного 16 часов назад, — «46 ответов»,
и ещё у одного за сутки — «123». Откликаться в третий бессмысленно независимо от того,
насколько свежим он кажется.

Поэтому решаем по ответам и скорости их появления (`ответов в час`), а возраст оставляем
как второй фильтр: старый заказ с малым числом ответов ещё может быть живым.

`responses = None` — данных нет (старые записи, ручной ввод). Это не ноль: ноль ответов
и «неизвестно» дают противоположные решения.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.aging import age_hours

OPEN = "open"  # мест полно: можно откликаться
CROWDED = "crowded"  # тесно, шанс мал: только если заказ действительно ваш
HOPELESS = "hopeless"  # откликов больше, чем клиент прочитает
UNKNOWN = "unknown"  # данных о конкуренции нет

LABELS = {
    OPEN: "свободно",
    CROWDED: "тесно",
    HOPELESS: "не берём",
    UNKNOWN: "нет данных",
}


@dataclass(slots=True)
class Competition:
    responses: int | None
    hours: float | None

    @property
    def per_hour(self) -> float | None:
        """Скорость появления откликов. 0.0 вместо деления на ноль для свежих заказов."""
        if self.responses is None or self.hours is None:
            return None
        if self.hours <= 0:
            return float(self.responses)
        return round(self.responses / self.hours, 2)


def measure(
    responses: int | None, published_at: datetime | None, *, now: datetime | None = None
) -> Competition:
    return Competition(responses=responses, hours=age_hours(published_at, now))


def verdict(
    competition: Competition,
    *,
    max_responses: int = 10,
    hard_responses: int = 20,
) -> str:
    """Категория конкуренции. Без данных — UNKNOWN, а не «свободно»."""
    if competition.responses is None:
        return UNKNOWN
    if competition.responses >= hard_responses:
        return HOPELESS
    if competition.responses >= max_responses:
        return CROWDED
    return OPEN


def worth_applying(
    competition: Competition,
    *,
    max_responses: int = 10,
    now: datetime | None = None,
    dead_hours: float = 24,
) -> bool | None:
    """Стоит ли вообще рассматривать заказ. None — конкуренция неизвестна.

    Возраст учитывается только когда он известен: у заказов из ручного ввода даты
    публикации нет, и отбрасывать их за это было бы ошибкой.
    """
    if competition.responses is None:
        return None
    too_many = competition.responses >= max_responses
    too_old = competition.hours is not None and competition.hours >= dead_hours
    return not (too_many or too_old)
