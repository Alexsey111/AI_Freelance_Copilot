"""Логика заказов: создание из входных данных, витрина, метрики.

Здесь же живёт Normalizer: что бы ни пришло (API, а в будущем --- FL.ru, Kwork, RSS,
Telegram), наружу выходит только доменный Order (ТЗ §18).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.domain.models.audit import AuditStatus
from app.domain.models.order import Order
from app.domain.services.audit_service import AuditService, AuditTimer
from app.infrastructure.sources.base import ExternalOrder, normalize_external_order

ACTION_CREATE = "create_order"
ACTION_LIST = "list_orders"


@dataclass(slots=True)
class OrderCreateInput:
    """Входные данные для создания заказа (Endpoint №1, ТЗ §9)."""

    title: str
    description: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "RUB"
    url: str | None = None
    client_name: str | None = None
    source: str = "manual"
    external_id: str | None = None
    raw_input: dict | None = None


@dataclass(slots=True)
class OrderListResult:
    items: list[Order]
    total: int
    page: int
    page_size: int
    latest: dict = None  # type: ignore[assignment]  # order_id -> AnalysisModel (для витрины)


class OrderService:
    def __init__(
        self,
        order_repository,
        audit_service: AuditService,
        settings: Settings | None = None,
        analysis_repository=None,
    ) -> None:
        self.orders = order_repository
        self.audit = audit_service
        self.analyses = analysis_repository
        self.settings = settings or get_settings()

    # --- Endpoint №1: создание (ТЗ §9) ---
    def create_order(self, payload: OrderCreateInput) -> Order:
        timer = AuditTimer.start()
        external = ExternalOrder(
            source=payload.source or "manual",
            external_id=payload.external_id,
            title=payload.title,
            description=payload.description,
            budget_min=payload.budget_min,
            budget_max=payload.budget_max,
            currency=payload.currency,
            url=payload.url,
            client_name=payload.client_name,
            raw=payload.raw_input or {},
        )
        order = normalize_external_order(
            external, min_description_chars=self.settings.min_description_chars
        )

        # Дедупликация по (source, external_id) --- задел под будущий автосбор (ТЗ §20).
        if order.external_id:
            existing = self.orders.find_by_external(order.source, order.external_id)
            if existing is not None:
                self.audit.record(
                    ACTION_CREATE,
                    input_payload={"source": order.source, "external_id": order.external_id},
                    output_payload={"id": existing.id, "deduplicated": True},
                    status=AuditStatus.SUCCESS.value,
                    duration_ms=timer.duration_ms,
                    order_id=existing.id,
                )
                return existing

        created = self.orders.add(order, raw_input=payload.raw_input)
        self.audit.record(
            ACTION_CREATE,
            input_payload={
                "title": payload.title,
                "source": payload.source,
                "budget_min": payload.budget_min,
                "budget_max": payload.budget_max,
            },
            output_payload={
                "id": created.id,
                "status": created.status,
                "needs_review_preliminary": created.needs_review,
            },
            status=(
                AuditStatus.REVIEW.value
                if created.needs_review
                else AuditStatus.SUCCESS.value
            ),
            duration_ms=timer.duration_ms,
            order_id=created.id,
        )
        return created

    # --- Endpoint №2: витрина (ТЗ §10, §23) ---
    def list_orders(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        source: str | None = None,
        needs_review: bool | None = None,
        recommendation: str | None = None,
        search: str | None = None,
        write_audit: bool = True,
    ) -> OrderListResult:
        timer = AuditTimer.start()
        items, total = self.orders.list(
            page=page,
            page_size=page_size,
            status=status,
            source=source,
            needs_review=needs_review,
            recommendation=recommendation,
            search=search,
        )
        latest = self.orders.latest_analyses([order.id for order in items])
        result = OrderListResult(
            items=items, total=total, page=page, page_size=page_size, latest=latest
        )
        if write_audit:
            self.audit.record(
                ACTION_LIST,
                input_payload={
                    "page": page,
                    "page_size": page_size,
                    "status": status,
                    "needs_review": needs_review,
                    "recommendation": recommendation,
                    "search": search,
                },
                output_payload={"total": total, "returned": len(items)},
                status=AuditStatus.SUCCESS.value,
                duration_ms=timer.duration_ms,
            )
        return result

    def get_order(self, order_id: int) -> Order | None:
        return self.orders.get(order_id)

    def list_analyses(self, order_id: int) -> list:
        """История анализов заказа (карточка заказа показывает все запуски ИИ)."""
        return self.analyses.list_for_order(order_id)

    def list_audit(self, **kwargs):
        """Журнал аудита (нужен сервисному слою и UI; репозиторий --- единственный источник)."""
        return self.audit.audit.list(**kwargs)
