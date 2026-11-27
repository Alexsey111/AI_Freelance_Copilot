"""Подборка заказов под профиль через API: что взять и почему.

Отдельный маршрут, а не флаг у списка: у подборки своя логика и своя цена ошибки —
она отвечает на вопрос «с чего начать», а не «что вообще есть».
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.dependencies import get_order_service, get_session
from app.domain.shortlist import VERDICT_LABELS, Thresholds, build_shortlist
from app.infrastructure.database.repositories.profile_repository import ProfileRepository

router = APIRouter(tags=["shortlist"])


class FitOut(BaseModel):
    order_id: int
    title: str
    verdict: str
    verdict_label: str
    score: int
    matched_skills: list[str]
    reasons: list[str]
    budget: float | None = None
    responses: int | None = None
    age_hours: float | None = None


class ShortlistOut(BaseModel):
    items: list[FitOut]
    considered: int
    skills: list[str]
    min_budget_rub: float
    note: str


@router.get("/orders/shortlist", response_model=ShortlistOut, summary="Подборка под профиль")
def shortlist(
    limit: int = Query(10, ge=1, le=50),
    include_skipped: bool = Query(False),
    considered: int = Query(200, ge=1, le=1000),
    session=Depends(get_session),
    service=Depends(get_order_service),
) -> ShortlistOut:
    profile = ProfileRepository(session).get_active()
    skills = profile.normalized_skills if profile else []
    # Минимальный бюджет лежит в предпочтениях профиля: это требование человека,
    # а не константа программы.
    preferences = profile.preferences if profile else {}
    raw_budget = preferences.get("min_budget_rub")
    min_budget = float(raw_budget) if raw_budget else 50_000.0

    result = service.list_orders(page=1, page_size=considered, write_audit=False)
    fits = build_shortlist(
        result.items,
        skills=skills,
        thresholds=Thresholds(min_budget_rub=min_budget),
        limit=limit,
        include_skipped=include_skipped,
    )
    return ShortlistOut(
        items=[
            FitOut(
                order_id=fit.order_id,
                title=fit.title,
                verdict=fit.verdict,
                verdict_label=VERDICT_LABELS.get(fit.verdict, fit.verdict),
                score=fit.score,
                matched_skills=fit.matched_skills,
                reasons=fit.reasons,
                budget=fit.budget,
                responses=fit.responses,
                age_hours=fit.age_hours,
            )
            for fit in fits
        ],
        considered=len(result.items),
        skills=skills,
        min_budget_rub=min_budget,
        note="Подборка — это чтение за вас, а не отправка отклика: решает человек.",
    )
