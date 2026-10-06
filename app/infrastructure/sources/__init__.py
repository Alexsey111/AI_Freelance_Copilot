"""Адаптеры источников заказов (ТЗ §18)."""

from app.infrastructure.sources.base import ExternalOrder, OrderSource, normalize_external_order
from app.infrastructure.sources.manual_source import ManualOrderSource

__all__ = [
    "ExternalOrder",
    "ManualOrderSource",
    "OrderSource",
    "normalize_external_order",
]
