"""Возраст заказа: две разные величины, которые нельзя смешивать.

`published_at` — когда заказ опубликован на площадке. С ним растёт конкуренция:
к третьему часу на заказе уже пять откликов, к суткам — двадцать, и отклик
бессмысленен независимо от того, насколько хорошо он написан.

`queued_at` — когда решение ушло человеку. Это наш собственный долг: заказ может быть
свежим, а просроченным будет разбор.

Пороги берутся из настроек, чтобы правило менялось одним числом, а не поиском
по коду: по умолчанию 6 часов — свежий, 12 — на грани, 24 — не смотреть.
"""

from __future__ import annotations

from datetime import UTC, datetime

FRESH = "fresh"
USABLE = "usable"
STALE = "stale"
DEAD = "dead"
UNKNOWN = "unknown"

LABELS = {
    FRESH: "свежий (< 6 ч)",
    USABLE: "рабочий (6–12 ч)",
    STALE: "на грани (12–24 ч)",
    DEAD: "просрочен (> 24 ч)",
    UNKNOWN: "возраст неизвестен",
}


def age_hours(moment: datetime | None, now: datetime | None = None) -> float | None:
    """Возраст в часах. None, если момент неизвестен; будущее считаем нулём."""
    if moment is None:
        return None
    now = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    delta = (now - moment).total_seconds() / 3600
    return round(max(delta, 0.0), 2)


def freshness(
    published_at: datetime | None,
    *,
    now: datetime | None = None,
    fresh_hours: float = 6,
    stale_hours: float = 12,
    dead_hours: float = 24,
) -> str:
    """Категория свежести по дате публикации. Без даты — UNKNOWN, а не «свежий»."""
    hours = age_hours(published_at, now)
    if hours is None:
        return UNKNOWN
    if hours < fresh_hours:
        return FRESH
    if hours < stale_hours:
        return USABLE
    if hours < dead_hours:
        return STALE
    return DEAD


def is_worth_looking(
    published_at: datetime | None,
    *,
    now: datetime | None = None,
    dead_hours: float = 24,
) -> bool | None:
    """Стоит ли смотреть заказ. None — возраст неизвестен, решение за человеком."""
    hours = age_hours(published_at, now)
    if hours is None:
        return None
    return hours < dead_hours


def queue_overdue_hours(
    queued_at: datetime | None, *, now: datetime | None = None
) -> float | None:
    """Сколько часов решение ждёт человека. None — не в очереди."""
    return age_hours(queued_at, now)
