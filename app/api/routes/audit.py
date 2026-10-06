"""Журнал аудита, метрики и состояние системы (ТЗ §26, §33, §34)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_metrics_service, get_order_service
from app.api.schemas.audit import AuditListResponse, AuditRunOut, EconomyOut, MetricsOut
from app.domain.models.audit import AuditStatus
from app.domain.services.metrics_service import DEFAULT_HOURLY_RATE_RUB, MetricsService
from app.domain.services.order_service import OrderService

router = APIRouter(tags=["audit"])


@router.get(
    "/audit",
    response_model=AuditListResponse,
    summary="Журнал аудита",
    description="Каждый запуск: действие, вход, выход, статус, ошибка, длительность.",
)
def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    action: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    order_id: int | None = Query(None),
    service: OrderService = Depends(get_order_service),
):
    items, total = service.list_audit(
        page=page, page_size=page_size, action=action, status=status_filter, order_id=order_id
    )
    return AuditListResponse(
        items=[AuditRunOut(**asdict(run)) for run in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/audit/actions",
    summary="Какие действия вообще писались в аудит",
    description="Список action со счётчиками --- для фильтров в UI.",
)
def audit_actions(service: OrderService = Depends(get_order_service)):
    actions = service.audit.audit.count_by_action()
    statuses = service.audit.audit.count_by_status()
    return {
        "actions": actions,
        "statuses": {item.value: statuses.get(item.value, 0) for item in AuditStatus},
        "total": sum(actions.values()),
    }


@router.get(
    "/metrics",
    response_model=MetricsOut,
    summary="Метрики проекта и мини-экономика",
    description=(
        "KPI ТЗ §34 и мини-экономика §33. Значение null означает 'нет данных' "
        "(например, доля корректных JSON при нуле анализов), а не ноль."
    ),
)
def metrics(
    hourly_rate_rub: float = Query(DEFAULT_HOURLY_RATE_RUB, gt=0, le=100000),
    service: MetricsService = Depends(get_metrics_service),
):
    snapshot = service.collect()
    return MetricsOut(
        **{
            "orders_total": snapshot.orders_total,
            "orders_by_status": snapshot.orders_by_status,
            "orders_recommended": snapshot.orders_recommended,
            "orders_needs_review": snapshot.orders_needs_review,
            "analyses_total": snapshot.analyses_total,
            "analyses_needs_review": snapshot.analyses_needs_review,
            "analyses_errors": snapshot.analyses_errors,
            "analyses_by_recommendation": snapshot.analyses_by_recommendation,
            "avg_match_score": snapshot.avg_match_score,
            "audit_total": snapshot.audit_total,
            "audit_by_status": snapshot.audit_by_status,
            "audit_by_action": snapshot.audit_by_action,
            "audit_errors": snapshot.audit_errors,
            "avg_analyze_duration_ms": snapshot.avg_analyze_duration_ms,
            "max_analyze_duration_ms": snapshot.max_analyze_duration_ms,
            "json_valid_rate": snapshot.json_valid_rate,
            "review_share": snapshot.review_share,
            "apply_share": snapshot.apply_share,
            "economy": EconomyOut(**snapshot.economy(hourly_rate_rub)),
        }
    )
