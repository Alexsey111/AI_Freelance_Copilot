"""Репозиторий заказов. Работает с доменными объектами Order, наружу SQL не протекает."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.domain.models.analysis import Recommendation
from app.domain.models.order import Order, OrderStatus
from app.infrastructure.database.models import AnalysisModel, OrderModel


def _to_domain(model: OrderModel) -> Order:
    return Order(
        id=model.id,
        external_id=model.external_id,
        source=model.source,
        title=model.title,
        description=model.description or "",
        budget_min=model.budget_min,
        budget_max=model.budget_max,
        currency=model.currency,
        url=model.url,
        client_name=model.client_name,
        status=model.status,
        needs_review=bool(model.needs_review),
        raw_input=model.raw_input,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class OrderRepository:
    """CRUD и выборки по заказам."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # --- запись ---
    def add(self, order: Order, raw_input: dict | None = None) -> Order:
        model = OrderModel(
            external_id=order.external_id,
            source=order.source,
            title=order.title,
            description=order.description,
            budget_min=order.budget_min,
            budget_max=order.budget_max,
            currency=order.currency,
            url=order.url,
            client_name=order.client_name,
            status=order.status or OrderStatus.NEW.value,
            needs_review=bool(order.needs_review),
            raw_input=raw_input if raw_input is not None else order.raw_input,
        )
        self.session.add(model)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def update_status(
        self, order_id: int, status: str, *, needs_review: bool | None = None
    ) -> Order | None:
        model = self.session.get(OrderModel, order_id)
        if model is None:
            return None
        model.status = status
        if needs_review is not None:
            model.needs_review = needs_review
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def set_needs_review(self, order_id: int, value: bool) -> Order | None:
        model = self.session.get(OrderModel, order_id)
        if model is None:
            return None
        model.needs_review = value
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def find_by_external(self, source: str, external_id: str) -> Order | None:
        stmt = select(OrderModel).where(
            OrderModel.source == source, OrderModel.external_id == external_id
        )
        model = self.session.execute(stmt).scalars().first()
        return _to_domain(model) if model else None

    # --- чтение ---
    def get(self, order_id: int) -> Order | None:
        model = self.session.get(OrderModel, order_id)
        return _to_domain(model) if model else None

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        source: str | None = None,
        needs_review: bool | None = None,
        recommendation: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Order], int]:
        """Витрина заказов (ТЗ §10, §23) с пагинацией и фильтрами."""
        stmt = select(OrderModel)
        if status:
            stmt = stmt.where(OrderModel.status == status)
        if source:
            stmt = stmt.where(OrderModel.source == source)
        if needs_review is not None:
            stmt = stmt.where(OrderModel.needs_review.is_(bool(needs_review)))
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(OrderModel.title.ilike(pattern), OrderModel.description.ilike(pattern))
            )
        if recommendation:
            latest = (
                select(
                    AnalysisModel.order_id,
                    func.max(AnalysisModel.id).label("last_id"),
                )
                .group_by(AnalysisModel.order_id)
                .subquery()
            )
            stmt = stmt.join(latest, latest.c.order_id == OrderModel.id).join(
                AnalysisModel, AnalysisModel.id == latest.c.last_id
            ).where(AnalysisModel.recommendation == recommendation)

        total = int(
            self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            ).scalar_one()
        )
        stmt = (
            stmt.order_by(OrderModel.created_at.desc(), OrderModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(selectinload(OrderModel.analyses))
        )
        models = self.session.execute(stmt).scalars().unique().all()
        return [_to_domain(model) for model in models], total

    def latest_analyses(self, order_ids: list[int]) -> dict[int, AnalysisModel]:
        """Последний анализ по каждому заказу --- для витрины (match score, review)."""
        if not order_ids:
            return {}
        latest = (
            select(
                AnalysisModel.order_id,
                func.max(AnalysisModel.id).label("last_id"),
            )
            .where(AnalysisModel.order_id.in_(order_ids))
            .group_by(AnalysisModel.order_id)
            .subquery()
        )
        stmt = select(AnalysisModel).join(latest, AnalysisModel.id == latest.c.last_id)
        return {model.order_id: model for model in self.session.execute(stmt).scalars().all()}

    # --- метрики (ТЗ §34) ---
    def count_by_status(self) -> dict[str, int]:
        stmt = select(OrderModel.status, func.count()).group_by(OrderModel.status)
        return {status: int(count) for status, count in self.session.execute(stmt).all()}

    def count_recommended(self) -> int:
        latest = (
            select(
                AnalysisModel.order_id,
                func.max(AnalysisModel.id).label("last_id"),
            )
            .group_by(AnalysisModel.order_id)
            .subquery()
        )
        stmt = select(func.count()).select_from(
            select(AnalysisModel.id)
            .join(latest, AnalysisModel.id == latest.c.last_id)
            .where(AnalysisModel.recommendation == Recommendation.APPLY.value)
            .subquery()
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_all(self) -> int:
        return int(self.session.execute(select(func.count()).select_from(OrderModel)).scalar_one())
