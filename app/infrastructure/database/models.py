"""ORM-модели (4 доменные таблицы + таблица аудита) --- ТЗ §5---§8.

Единственное место, где описано физическое хранение. Доменные модели
(app/domain/models) от него не зависят.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrderModel(Base):
    """orders --- основная сущность (ТЗ §5.1)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    # Денормализованный флаг последнего анализа: нужен для фильтра ?needs_review=true
    # и экрана "Требуют проверки". Держится в синхроне с status == "needs_review".
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    analyses: Mapped[list[AnalysisModel]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="AnalysisModel.id"
    )

    __table_args__ = (
        Index("ix_orders_source_external", "source", "external_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_needs_review", "needs_review"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<OrderModel id={self.id} status={self.status!r} title={self.title!r}>"


class ProfileModel(Base):
    """profiles --- профиль исполнителя (ТЗ §6). На MVP один активный профиль."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    experience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    portfolio: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ProfileModel id={self.id} name={self.name!r}>"


class AnalysisModel(Base):
    """analyses --- результат ИИ-анализа заказа (ТЗ §7)."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)

    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    draft_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Человеческое решение по записи, попавшей в ручную проверку (ТЗ §25)
    review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[OrderModel] = relationship(back_populates="analyses")

    __table_args__ = (Index("ix_analyses_order_id", "order_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<AnalysisModel id={self.id} order_id={self.order_id} "
            f"score={self.match_score} review={self.needs_review}>"
        )


class AuditRunModel(Base):
    """audit_runs --- журнал аудита (ТЗ §8). Пишется на каждый запуск, включая ошибки."""

    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # Дублирует order_id из input для быстрой выборки по заказу (техническое поле)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_audit_runs_action", "action"),
        Index("ix_audit_runs_status", "status"),
        Index("ix_audit_runs_order_id", "order_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuditRunModel id={self.id} action={self.action!r} status={self.status!r}>"
