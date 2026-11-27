"""Два режима порога: жёсткий и «набор на промежуток».

Жёсткий (`hard`): берём только заказы с бюджетом не ниже порога профиля. Просто,
предсказуемо и отсекает всё мелкое — включая четыре заказа по 15 000 ₽, которые вместе
дают больше порога и укладываются в свободные часы.

Гибкий (`portfolio`): порог применяется не к одному заказу, а к промежутку. Промежуток —
это неделя, и меряется он **часами**, а не рублями: часов в неделе конечное число (45),
и именно они решают, сколько заказов физически помещается. Заказы складываются в неделю
по сроку сдачи (`deadline_at`); если срока нет — окно считается скользящим, от сегодня
на семь дней, и это помечается как «окно по умолчанию», а не выдаётся за план.

Правило приёмки в гибком режиме:
  1. ставка заказа не ниже цели — берём, если в окне есть свободные часы;
  2. ставка ниже цели — берём только как добивку простоя: когда набранная сумма недели
     ещё не достигла цели и часы простаивают иначе;
  3. часов в окне не хватает — не берём, какая бы ни была ставка.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.rate import Rate
from app.domain.rate import verdict as rate_verdict

HARD = "hard"
PORTFOLIO = "portfolio"

ADMIT = "admit"  # берём: ставка в норме и часы есть
FILLER = "filler"  # берём как добивку: ставка ниже цели, но неделя не набрана
SKIP = "skip"  # не берём

LABELS = {
    ADMIT: "берём",
    FILLER: "добивка простоя",
    SKIP: "не берём",
}

WEEK = 7


@dataclass(slots=True)
class Window:
    """Промежуток, в который складываются заказы."""

    start: datetime
    end: datetime
    from_deadline: bool  # True — окно по сроку сдачи, False — скользящее по умолчанию

    @property
    def days(self) -> int:
        return max((self.end - self.start).days, 1)


def week_of(deadline_at: datetime | None, *, now: datetime | None = None) -> Window:
    """Неделя, в которую попадает срок сдачи; без срока — скользящие 7 дней от сегодня."""
    now = now or datetime.now(UTC)
    if deadline_at is None:
        return Window(start=now, end=now + timedelta(days=WEEK), from_deadline=False)
    moment = deadline_at if deadline_at.tzinfo else deadline_at.replace(tzinfo=UTC)
    start = moment - timedelta(days=moment.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return Window(start=start, end=start + timedelta(days=WEEK), from_deadline=True)


@dataclass(slots=True)
class Load:
    """Что уже набрано в окне."""

    hours: float = 0.0
    money: float = 0.0
    orders: list[int] = field(default_factory=list)

    def free_hours(self, capacity: float) -> float:
        return max(capacity - self.hours, 0.0)


@dataclass(slots=True)
class Decision:
    action: str
    reason: str
    window: Window
    free_hours: float


def decide(
    rate: Rate,
    hours: float | None,
    load: Load,
    *,
    window: Window,
    capacity_hours: float = 45.0,
    target_week_rub: float = 75_000.0,
    min_rate_rub_per_hour: float = 1_500.0,
    budget_floor_rub: float | None = None,
    mode: str = PORTFOLIO,
) -> Decision:
    """Приёмка заказа в окне. Гибкий режим не отменяет порог — он применяется к неделе."""
    if hours is None:
        return Decision(
            action=SKIP,
            reason="Нет оценки часов: нечем измерить ни ставку, ни занятость",
            window=window,
            free_hours=load.free_hours(capacity_hours),
        )

    if mode == HARD:
        # Жёсткий режим — ровно то правило, что стоит в ядре сейчас: порог профиля
        # по сумме заказа. Он и отсекает 4 × 15 000 ₽, хотя неделя ими набирается.
        if (
            budget_floor_rub is not None
            and rate.budget is not None
            and rate.budget < budget_floor_rub
        ):
            return Decision(
                action=SKIP,
                reason=(
                    f"Жёсткий режим: бюджет {rate.budget:.0f} ₽ ниже порога профиля "
                    f"{budget_floor_rub:.0f} ₽"
                ),
                window=window,
                free_hours=load.free_hours(capacity_hours),
            )
        if rate.per_hour is None or rate.per_hour < min_rate_rub_per_hour:
            return Decision(
                action=SKIP,
                reason=f"Жёсткий режим: ставка {rate.per_hour} ₽/ч ниже цели {min_rate_rub_per_hour:.0f}",
                window=window,
                free_hours=load.free_hours(capacity_hours),
            )
        if load.free_hours(capacity_hours) < hours:
            return Decision(
                action=SKIP,
                reason=f"В окне осталось {load.free_hours(capacity_hours):.0f} ч, нужно {hours:.0f}",
                window=window,
                free_hours=load.free_hours(capacity_hours),
            )
        return Decision(
            action=ADMIT,
            reason=f"Ставка {rate.per_hour} ₽/ч, часы есть",
            window=window,
            free_hours=load.free_hours(capacity_hours),
        )

    free = load.free_hours(capacity_hours)
    if free < hours:
        return Decision(
            action=SKIP,
            reason=(
                f"В окне {window.start:%d.%m}–{window.end:%d.%m} осталось {free:.0f} ч из "
                f"{capacity_hours:.0f}, нужно {hours:.0f}"
            ),
            window=window,
            free_hours=free,
        )

    category = rate_verdict(rate, min_rate_rub_per_hour=min_rate_rub_per_hour)
    if category in {"ok", "great"}:
        return Decision(
            action=ADMIT,
            reason=f"Ставка {rate.per_hour} ₽/ч, свободно {free:.0f} ч",
            window=window,
            free_hours=free,
        )

    if load.money + (rate.budget or 0) <= target_week_rub:
        return Decision(
            action=FILLER,
            reason=(
                f"Ставка {rate.per_hour} ₽/ч ниже цели, но в неделе набрано "
                f"{load.money:.0f} ₽ из {target_week_rub:.0f} и часы простаивают"
            ),
            window=window,
            free_hours=free,
        )

    return Decision(
        action=SKIP,
        reason=(f"Ставка {rate.per_hour} ₽/ч ниже цели, а неделя уже набрана: {load.money:.0f} ₽"),
        window=window,
        free_hours=free,
    )
