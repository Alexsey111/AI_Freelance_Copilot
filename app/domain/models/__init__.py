"""Доменные модели (не зависят от FastAPI, SQLAlchemy и конкретной LLM)."""

from app.domain.models.analysis import (
    Analysis,
    AnalysisResult,
    Recommendation,
    ReviewStatus,
)
from app.domain.models.audit import AuditRun, AuditStatus
from app.domain.models.order import Order, OrderSource, OrderStatus
from app.domain.models.profile import Profile

__all__ = [
    "Analysis",
    "AnalysisResult",
    "AuditRun",
    "AuditStatus",
    "Order",
    "OrderSource",
    "OrderStatus",
    "Profile",
    "Recommendation",
    "ReviewStatus",
]
