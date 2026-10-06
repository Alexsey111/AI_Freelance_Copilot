"""Заказы: Endpoint №1 (создание) и №2 (витрина) --- ТЗ §9, §10, §23.

Тут же лежит API-совместимый вход для будущих адаптеров источников (ТЗ §18):
приём заказа от FL.ru/Kwork/RSS/Telegram пойдёт тем же путём POST /orders
с другим source, и бизнес-логика об этом знать не будет.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_order_service
from app.api.schemas.analysis import AnalysisSummaryOut
from app.api.schemas.orders import (
    OrderCreate,
    OrderCreateResponse,
    OrderDetailOut,
    OrderListResponse,
    OrderOut,
)
from app.domain.models.order import Order, OrderSource, OrderStatus
from app.domain.services.order_service import OrderCreateInput, OrderService

router = APIRouter(prefix="/orders", tags=["orders"])

VALID_STATUSES = {item.value for item in OrderStatus}
VALID_RECOMMENDATIONS = {"apply", "skip", "review"}


def _summary(analysis) -> AnalysisSummaryOut | None:
    if analysis is None:
        return None
    return AnalysisSummaryOut(
        id=analysis.id,
        match_score=analysis.match_score,
        recommendation=analysis.recommendation,
        needs_review=bool(analysis.needs_review),
        review_reason=analysis.review_reason,
        review_status=analysis.review_status,
        created_at=analysis.created_at,
    )


def _to_out(order: Order, latest=None) -> OrderOut:
    return OrderOut(
        id=order.id,
        external_id=order.external_id,
        source=order.source,
        title=order.title,
        description=order.description,
        budget_min=order.budget_min,
        budget_max=order.budget_max,
        currency=order.currency,
        url=order.url,
        client_name=order.client_name,
        status=order.status,
        needs_review=bool(order.needs_review),
        created_at=order.created_at,
        updated_at=order.updated_at,
        latest_analysis=_summary(latest),
    )


@router.post(
    "",
    response_model=OrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Точка 1: создать заказ",
    description=(
        "Создаёт запись о фриланс-заказе, нормализует её в единую доменную модель "
        "и сохраняет в БД. Пишется в журнал аудита."
    ),
)
def create_order(payload: OrderCreate, service: OrderService = Depends(get_order_service)):
    if payload.source not in {item.value for item in OrderSource}:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Неизвестный источник заказа: {payload.source!r}. "
                f"Допустимые: {', '.join(sorted(item.value for item in OrderSource))}"
            ),
        )
    created = service.create_order(
        OrderCreateInput(
            title=payload.title,
            description=payload.description,
            budget_min=payload.budget_min,
            budget_max=payload.budget_max,
            currency=payload.currency,
            url=payload.url,
            client_name=payload.client_name,
            source=payload.source,
            external_id=payload.external_id,
            raw_input=payload.raw_input or payload.model_dump(mode="json"),
        )
    )
    return OrderCreateResponse(
        id=created.id,
        status=created.status,
        needs_review=bool(created.needs_review),
        created_at=created.created_at,
    )


@router.get(
    "",
    response_model=OrderListResponse,
    summary="Точка 2: витрина заказов",
    description="Список заказов с пагинацией и фильтрами: status, needs_review, source, recommendation, поиск.",
)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    needs_review: bool | None = Query(None),
    source: str | None = Query(None),
    recommendation: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    service: OrderService = Depends(get_order_service),
):
    if status_filter is not None and status_filter not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Недопустимый статус: {status_filter!r}")
    if recommendation is not None and recommendation not in VALID_RECOMMENDATIONS:
        raise HTTPException(
            status_code=422, detail=f"Недопустимая рекомендация: {recommendation!r}"
        )
    result = service.list_orders(
        page=page,
        page_size=page_size,
        status=status_filter,
        source=source,
        needs_review=needs_review,
        recommendation=recommendation,
        search=search,
    )
    items = [_to_out(order, result.latest.get(order.id)) for order in result.items]
    return OrderListResponse(
        items=items, total=result.total, page=result.page, page_size=result.page_size
    )


@router.get(
    "/{order_id}",
    response_model=OrderDetailOut,
    summary="Карточка заказа",
    description="Входные данные + сырой ввод (raw_input). Анализы --- отдельной точкой.",
)
def get_order(order_id: int, service: OrderService = Depends(get_order_service)):
    order = service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Заказ #{order_id} не найден")
    base = _to_out(order)
    return OrderDetailOut(
        **base.model_dump(),
        raw_input=order.raw_input if isinstance(order.raw_input, dict) else None,
    )


@router.get(
    "/{order_id}/analyses",
    summary="История анализов заказа",
    description="Все запуски ИИ по заказу: результат, модель, версия промпта, сырой вывод, ошибки.",
)
def list_order_analyses(order_id: int, service: OrderService = Depends(get_order_service)):
    order = service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Заказ #{order_id} не найден")
    return service.list_analyses(order_id)
