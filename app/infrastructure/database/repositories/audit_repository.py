"""Репозиторий журнала аудита (ТЗ §8, §26, §29.4)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models.audit import AuditRun, AuditStatus
from app.infrastructure.database.models import AuditRunModel


def _to_domain(model: AuditRunModel) -> AuditRun:
    return AuditRun(
        id=model.id,
        action=model.action,
        order_id=model.order_id,
        input=model.input,
        output=model.output,
        status=model.status,
        error=model.error,
        duration_ms=model.duration_ms,
        created_at=model.created_at,
    )


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: AuditRun) -> AuditRun:
        model = AuditRunModel(
            action=run.action,
            order_id=run.order_id,
            input=run.input,
            output=run.output,
            status=run.status,
            error=run.error,
            duration_ms=run.duration_ms,
        )
        self.session.add(model)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def get(self, run_id: int) -> AuditRun | None:
        model = self.session.get(AuditRunModel, run_id)
        return _to_domain(model) if model else None

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        action: str | None = None,
        status: str | None = None,
        order_id: int | None = None,
    ) -> tuple[list[AuditRun], int]:
        stmt = select(AuditRunModel)
        if action:
            stmt = stmt.where(AuditRunModel.action == action)
        if status:
            stmt = stmt.where(AuditRunModel.status == status)
        if order_id is not None:
            stmt = stmt.where(AuditRunModel.order_id == order_id)
        total = int(
            self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            ).scalar_one()
        )
        stmt = (
            stmt.order_by(AuditRunModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_domain(model) for model in self.session.execute(stmt).scalars().all()], total

    def count_by_action(self) -> dict[str, int]:
        stmt = select(AuditRunModel.action, func.count()).group_by(AuditRunModel.action)
        return {action: int(count) for action, count in self.session.execute(stmt).all()}

    def count_by_status(self) -> dict[str, int]:
        stmt = select(AuditRunModel.status, func.count()).group_by(AuditRunModel.status)
        return {status: int(count) for status, count in self.session.execute(stmt).all()}

    def count_all(self) -> int:
        return int(
            self.session.execute(select(func.count()).select_from(AuditRunModel)).scalar_one()
        )

    def count_errors(self) -> int:
        stmt = select(func.count()).select_from(AuditRunModel).where(
            AuditRunModel.status == AuditStatus.ERROR.value
        )
        return int(self.session.execute(stmt).scalar_one())

    def avg_duration_ms(self, action: str | None = None) -> float | None:
        stmt = select(func.avg(AuditRunModel.duration_ms)).where(
            AuditRunModel.duration_ms.is_not(None)
        )
        if action:
            stmt = stmt.where(AuditRunModel.action == action)
        value = self.session.execute(stmt).scalar_one()
        return float(value) if value is not None else None

    def max_duration_ms(self, action: str | None = None) -> int | None:
        stmt = select(func.max(AuditRunModel.duration_ms))
        if action:
            stmt = stmt.where(AuditRunModel.action == action)
        value = self.session.execute(stmt).scalar_one()
        return int(value) if value is not None else None
