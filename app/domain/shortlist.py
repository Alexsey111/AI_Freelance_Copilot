"""Подборка заказов под профиль: короткий список с причиной «почему этот».

Задача не «оценить заказ красиво», а снять с человека чтение ленты. Отсюда правила:

- причина в списке есть у каждого заказа, и она на русском: «в тексте: Python, LLM»;
- отказ тоже объясняется: «бюджет 3 000 ₽ ниже порога 50 000 ₽» — иначе список выглядит
  капризом системы;
- нет данных — не повод ни взять, ни выбросить: такой заказ идёт в «посмотреть самому»;
- решает человек: система не отправляет отклик, она показывает, из чего выбирать.

Оценка складывается из того, что можно проверить: совпадение навыков с текстом, бюджет
против порога профиля, свежесть публикации, число откликов. Ни одного «мне кажется».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

TAKE = "take"
REVIEW = "review"
SKIP = "skip"

VERDICT_LABELS = {
    TAKE: "берём",
    REVIEW: "посмотреть",
    SKIP: "не берём",
}


@dataclass(slots=True)
class Thresholds:
    """Пороги берутся из настроек и профиля, а не из кода."""

    min_budget_rub: float = 50_000.0
    fresh_hours: float = 6.0
    stale_hours: float = 12.0
    dead_hours: float = 24.0
    crowded_responses: int = 10
    hopeless_responses: int = 20


@dataclass(slots=True)
class Fit:
    order_id: int
    title: str
    verdict: str
    score: int
    matched_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    budget: float | None = None
    responses: int | None = None
    age_hours: float | None = None

    @property
    def verdict_label(self) -> str:
        return VERDICT_LABELS.get(self.verdict, self.verdict)


def _skills_in_text(skills: list[str], text: str) -> list[str]:
    haystack = text.lower()
    return [skill for skill in skills if skill and skill.lower() in haystack]


def _age_hours(published_at: datetime | None, now: datetime) -> float | None:
    if published_at is None:
        return None
    moment = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    return max(0.0, (now - moment).total_seconds() / 3600)


def evaluate(
    order,
    *,
    skills: list[str],
    thresholds: Thresholds,
    now: datetime | None = None,
) -> Fit:
    """Оценивает один заказ. `order` — доменный Order, ничего больше не требуется."""
    moment = now or datetime.now(UTC)
    text = f"{order.title} {order.description or ''}"
    matched = _skills_in_text(skills, text)
    reasons: list[str] = []
    score = 0
    blocked = False

    if matched:
        bonus = min(20 * len(matched), 40)
        score += bonus
        reasons.append(f"в тексте: {', '.join(matched)}")
    elif skills:
        reasons.append("ни одного вашего навыка в тексте")

    budget = order.budget_min if order.budget_min is not None else order.budget_max
    if budget is None:
        reasons.append("бюджет не указан — смотреть самому")
    elif budget >= thresholds.min_budget_rub:
        score += 25
        reasons.append(
            f"бюджет {budget:,.0f} ₽ ≥ порога {thresholds.min_budget_rub:,.0f} ₽".replace(",", " ")
        )
    else:
        blocked = True
        reasons.append(
            f"бюджет {budget:,.0f} ₽ ниже порога {thresholds.min_budget_rub:,.0f} ₽".replace(
                ",", " "
            )
        )

    age = _age_hours(order.published_at, moment)
    if age is None:
        reasons.append("возраст неизвестен")
    elif age <= thresholds.fresh_hours:
        score += 15
        reasons.append(f"опубликован {age:.1f} ч назад".replace(".", ","))
    elif age >= thresholds.dead_hours:
        blocked = True
        reasons.append(f"старше {thresholds.dead_hours:g} ч — позднее {age:.0f} ч в ленте")
    elif age >= thresholds.stale_hours:
        score -= 10
        reasons.append(f"на грани: {age:.0f} ч в ленте")

    responses = order.responses
    if responses is None:
        reasons.append("откликов не видно")
    elif responses >= thresholds.hopeless_responses:
        blocked = True
        reasons.append(
            f"уже {responses} откликов — {thresholds.hopeless_responses}+ значит «не берём»"
        )
    elif responses >= thresholds.crowded_responses:
        score -= 10
        reasons.append(f"тесно: {responses} откликов")
    else:
        score += 15
        reasons.append(f"свободно: {responses} откликов")

    if blocked:
        verdict = SKIP
    elif score >= 40 and (matched or not skills):
        # Без совпадения ни одного навыка заказ не «берём»: он может быть выгодным, но это
        # не ваша работа — пусть человек посмотрит и решит сам.
        verdict = TAKE
    elif score >= 15:
        verdict = REVIEW
    else:
        verdict = REVIEW if not skills else SKIP

    return Fit(
        order_id=order.id or 0,
        title=order.title,
        verdict=verdict,
        score=score,
        matched_skills=matched,
        reasons=reasons,
        budget=budget,
        responses=responses,
        age_hours=round(age, 1) if age is not None else None,
    )


def build_shortlist(
    orders,
    *,
    skills: list[str],
    thresholds: Thresholds,
    limit: int = 10,
    include_skipped: bool = False,
    now: datetime | None = None,
) -> list[Fit]:
    """Список под профиль: сначала «берём», потом «посмотреть»; отказы — по запросу."""
    fits = [evaluate(order, skills=skills, thresholds=thresholds, now=now) for order in orders]
    order_rank = {TAKE: 0, REVIEW: 1, SKIP: 2}
    fits.sort(key=lambda fit: (order_rank[fit.verdict], -fit.score))
    if not include_skipped:
        fits = [fit for fit in fits if fit.verdict != SKIP]
    return fits[:limit]
