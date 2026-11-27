"""Репозиторий прогонов (миграция 0001, урок 2: схема из вопросов).

Здесь же лежат три вопроса к базе из урока 2, на которые отвечает эта таблица:
доля решений, ушедших человеку, по прогонам; что изменилось между прогонами;
и стоимость прогона (стоимость приходит из `scripts/measure_cost.py`, в базе она
пока не хранится --- это открытый пункт, см. gaps.md).
"""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domain.models.run import Run
from app.infrastructure.database.models import AnalysisModel, AuditRunModel, RunModel, utcnow

STATUS_REVIEW = "review"


def _to_domain(model: RunModel) -> Run:
    return Run(
        id=model.id,
        kind=model.kind,
        status=model.status,
        model=model.model,
        prompt_version=model.prompt_version,
        profile_id=model.profile_id,
        orders_total=model.orders_total,
        orders_review=model.orders_review,
        note=model.note,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: Run) -> Run:
        model = RunModel(
            kind=run.kind,
            status=run.status,
            model=run.model,
            prompt_version=run.prompt_version,
            profile_id=run.profile_id,
            orders_total=run.orders_total,
            orders_review=run.orders_review,
            note=run.note,
        )
        self.session.add(model)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def get(self, run_id: int) -> Run | None:
        model = self.session.get(RunModel, run_id)
        return _to_domain(model) if model else None

    def list(self, limit: int = 20) -> list[Run]:
        stmt = select(RunModel).order_by(RunModel.id.desc()).limit(limit)
        return [_to_domain(model) for model in self.session.execute(stmt).scalars().all()]

    def count_decisions(self, run_id: int) -> tuple[int, int]:
        """(всего решений, решений с needs_review) по прогону --- одним запросом."""
        stmt = select(
            func.count(AnalysisModel.id),
            func.coalesce(func.sum(case((AnalysisModel.needs_review.is_(True), 1), else_=0)), 0),
        ).where(AnalysisModel.run_id == run_id)
        total, review = self.session.execute(stmt).one()
        return int(total or 0), int(review or 0)

    def count_audit(self, run_id: int) -> int:
        stmt = select(func.count()).select_from(AuditRunModel).where(AuditRunModel.run_id == run_id)
        return int(self.session.execute(stmt).scalar_one())

    def close(self, run_id: int, status: str) -> Run | None:
        """Закрывает прогон и фиксирует итог по фактическим записям, а не по словам."""
        model = self.session.get(RunModel, run_id)
        if model is None:
            return None
        total, review = self.count_decisions(run_id)
        model.orders_total = total
        model.orders_review = review
        model.status = status
        model.finished_at = utcnow()
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)
