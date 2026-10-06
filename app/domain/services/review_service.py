"""Ручная проверка (ТЗ §13, §25).

Система не делает вид, что уверена: сомнительный результат уходит человеку,
человек подтверждает или отклоняет, решение фиксируется в аудите.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models.analysis import Analysis, ReviewStatus
from app.domain.models.audit import AuditStatus
from app.domain.models.order import Order, OrderStatus
from app.domain.services.audit_service import AuditService, AuditTimer

ACTION_REVIEW = "review_decision"


@dataclass(slots=True)
class ReviewQueue:
    items: list[Analysis]
    total: int
    page: int
    page_size: int


class ReviewService:
    def __init__(self, analysis_repository, order_repository, audit_service: AuditService) -> None:
        self.analyses = analysis_repository
        self.orders = order_repository
        self.audit = audit_service

    def list_queue(
        self, *, page: int = 1, page_size: int = 20, review_status: str | None = None
    ) -> ReviewQueue:
        items, total = self.analyses.list_needs_review(
            page=page, page_size=page_size, review_status=review_status
        )
        return ReviewQueue(items=items, total=total, page=page, page_size=page_size)

    def decide(
        self, analysis_id: int, decision: str, comment: str | None = None
    ) -> tuple[Analysis, Order | None]:
        """Подтвердить (approved) или отклонить (rejected) результат анализа."""
        timer = AuditTimer.start()
        if decision not in {ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value}:
            raise ValueError("decision должен быть 'approved' или 'rejected'")

        analysis = self.analyses.set_review_decision(analysis_id, decision, comment)
        if analysis is None:
            self.audit.record(
                ACTION_REVIEW,
                input_payload={"analysis_id": analysis_id, "decision": decision},
                status=AuditStatus.ERROR.value,
                error=f"Анализ #{analysis_id} не найден",
                duration_ms=timer.duration_ms,
            )
            raise LookupError(f"Анализ #{analysis_id} не найден")

        order_status = (
            OrderStatus.APPROVED.value
            if decision == ReviewStatus.APPROVED.value
            else OrderStatus.REJECTED.value
        )
        order = self.orders.update_status(analysis.order_id, order_status, needs_review=False)
        self.audit.record(
            ACTION_REVIEW,
            input_payload={
                "analysis_id": analysis_id,
                "order_id": analysis.order_id,
                "decision": decision,
                "comment": comment,
            },
            output_payload={
                "review_status": analysis.review_status,
                "order_status": order_status,
                "note": "Действия (отправка отклика) на MVP не выполняются --- ТЗ §22",
            },
            status=AuditStatus.SUCCESS.value,
            duration_ms=timer.duration_ms,
            order_id=analysis.order_id,
        )
        return analysis, order
