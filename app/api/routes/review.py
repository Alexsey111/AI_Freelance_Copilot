"""Ручная проверка: очередь сомнительных результатов и решение человека (ТЗ §13, §25)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_review_service
from app.api.schemas.analysis import (
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueItemOut,
    ReviewQueueResponse,
)
from app.domain.models.analysis import ReviewStatus
from app.domain.services.review_service import ReviewService

router = APIRouter(tags=["review"])


@router.get(
    "/review-queue",
    response_model=ReviewQueueResponse,
    summary="Очередь 'Требуют проверки'",
    description="Результаты, где система не уверена: needs_review=true, с причиной проверки.",
)
def review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    review_status: str | None = Query(None, description="pending | approved | rejected"),
    service: ReviewService = Depends(get_review_service),
):
    if review_status is not None and review_status not in {s.value for s in ReviewStatus}:
        raise HTTPException(status_code=422, detail=f"Недопустимый review_status: {review_status!r}")
    queue = service.list_queue(page=page, page_size=page_size, review_status=review_status)
    items: list[ReviewQueueItemOut] = []
    for analysis in queue.items:
        order = service.orders.get(analysis.order_id)
        items.append(
            ReviewQueueItemOut(
                analysis_id=analysis.id,
                order_id=analysis.order_id,
                order_title=order.title if order else "(заказ удалён)",
                order_status=order.status if order else "unknown",
                match_score=analysis.match_score,
                recommendation=analysis.recommendation,
                review_reason=analysis.review_reason,
                review_status=analysis.review_status,
                created_at=analysis.created_at,
            )
        )
    return ReviewQueueResponse(
        items=items, total=queue.total, page=queue.page, page_size=queue.page_size
    )


@router.post(
    "/analyses/{analysis_id}/review",
    response_model=ReviewDecisionResponse,
    summary="Подтвердить или отклонить результат проверки",
    description=(
        "Человек принимает решение по записи, ушедшей в ручную проверку. Решение пишется "
        "в аудит. Никакие действия (отправка отклика) на MVP не выполняются --- ТЗ §22."
    ),
)
def decide_review(
    analysis_id: int,
    payload: ReviewDecisionRequest,
    service: ReviewService = Depends(get_review_service),
):
    try:
        analysis, order = service.decide(analysis_id, payload.decision, payload.comment)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewDecisionResponse(
        analysis_id=analysis.id,
        order_id=analysis.order_id,
        review_status=analysis.review_status or "",
        order_status=order.status if order else "unknown",
        review_comment=analysis.review_comment,
        reviewed_at=analysis.reviewed_at,
    )
