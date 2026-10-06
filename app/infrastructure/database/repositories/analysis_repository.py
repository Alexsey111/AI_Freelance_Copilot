"""Репозиторий результатов анализа (ТЗ §7, §12, §25)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models.analysis import Analysis, Recommendation, ReviewStatus
from app.infrastructure.database.models import AnalysisModel


def _to_domain(model: AnalysisModel) -> Analysis:
    return Analysis(
        id=model.id,
        order_id=model.order_id,
        profile_id=model.profile_id,
        match_score=model.match_score,
        recommendation=model.recommendation,
        reason=model.reason or "",
        matched_skills=list(model.matched_skills or []),
        missing_skills=list(model.missing_skills or []),
        draft_reply=model.draft_reply,
        needs_review=bool(model.needs_review),
        review_reason=model.review_reason,
        review_status=model.review_status,
        review_comment=model.review_comment,
        reviewed_at=model.reviewed_at,
        raw_output=model.raw_output,
        model=model.model,
        prompt_version=model.prompt_version,
        error=model.error,
        created_at=model.created_at,
    )


class AnalysisRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, analysis: Analysis) -> Analysis:
        model = AnalysisModel(
            order_id=analysis.order_id,
            profile_id=analysis.profile_id,
            match_score=analysis.match_score,
            recommendation=analysis.recommendation,
            reason=analysis.reason,
            matched_skills=analysis.matched_skills,
            missing_skills=analysis.missing_skills,
            draft_reply=analysis.draft_reply,
            needs_review=analysis.needs_review,
            review_reason=analysis.review_reason,
            review_status=analysis.review_status,
            review_comment=analysis.review_comment,
            reviewed_at=analysis.reviewed_at,
            raw_output=analysis.raw_output,
            model=analysis.model,
            prompt_version=analysis.prompt_version,
            error=analysis.error,
        )
        self.session.add(model)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def get(self, analysis_id: int) -> Analysis | None:
        model = self.session.get(AnalysisModel, analysis_id)
        return _to_domain(model) if model else None

    def latest_for_order(self, order_id: int) -> Analysis | None:
        stmt = (
            select(AnalysisModel)
            .where(AnalysisModel.order_id == order_id)
            .order_by(AnalysisModel.id.desc())
            .limit(1)
        )
        model = self.session.execute(stmt).scalars().first()
        return _to_domain(model) if model else None

    def list_for_order(self, order_id: int) -> list[Analysis]:
        stmt = (
            select(AnalysisModel)
            .where(AnalysisModel.order_id == order_id)
            .order_by(AnalysisModel.id.desc())
        )
        return [_to_domain(model) for model in self.session.execute(stmt).scalars().all()]

    def list_needs_review(
        self, *, page: int = 1, page_size: int = 20, review_status: str | None = None
    ) -> tuple[list[Analysis], int]:
        """Записи, попавшие в ручную проверку (ТЗ §25, экран "Требуют проверки")."""
        stmt = select(AnalysisModel).where(AnalysisModel.needs_review.is_(True))
        if review_status:
            stmt = stmt.where(AnalysisModel.review_status == review_status)
        total = int(
            self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            ).scalar_one()
        )
        stmt = (
            stmt.order_by(AnalysisModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_domain(model) for model in self.session.execute(stmt).scalars().all()], total

    def set_review_decision(
        self, analysis_id: int, review_status: str, comment: str | None = None
    ) -> Analysis | None:
        if review_status not in {status.value for status in ReviewStatus}:
            raise ValueError(f"Недопустимый review_status: {review_status}")
        model = self.session.get(AnalysisModel, analysis_id)
        if model is None:
            return None
        model.review_status = review_status
        model.review_comment = comment
        model.reviewed_at = datetime.now(UTC)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    # --- метрики (ТЗ §34) ---
    def count_all(self) -> int:
        return int(
            self.session.execute(select(func.count()).select_from(AnalysisModel)).scalar_one()
        )

    def count_needs_review(self) -> int:
        stmt = select(func.count()).select_from(AnalysisModel).where(
            AnalysisModel.needs_review.is_(True)
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_recommendation(self) -> dict[str, int]:
        stmt = select(AnalysisModel.recommendation, func.count()).group_by(
            AnalysisModel.recommendation
        )
        return {rec: int(count) for rec, count in self.session.execute(stmt).all()}

    def avg_match_score(self) -> float | None:
        stmt = select(func.avg(AnalysisModel.match_score)).where(
            AnalysisModel.match_score.is_not(None)
        )
        value = self.session.execute(stmt).scalar_one()
        return float(value) if value is not None else None

    def count_errors(self) -> int:
        stmt = select(func.count()).select_from(AnalysisModel).where(
            AnalysisModel.error.is_not(None)
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_apply(self) -> int:
        stmt = select(func.count()).select_from(AnalysisModel).where(
            AnalysisModel.recommendation == Recommendation.APPLY.value
        )
        return int(self.session.execute(stmt).scalar_one())
