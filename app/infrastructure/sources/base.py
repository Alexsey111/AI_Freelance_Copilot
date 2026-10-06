"""Абстракция источника заказов (ТЗ §18).

Сейчас реализован только manual (заказ приходит через API вручную), но контракт
рассчитан на будущие источники: FL.ru, Kwork, Freelance.ru, Telegram, RSS, API, webhooks.
Ключевой принцип: любой источник приводит данные к ExternalOrder, дальше Normalizer
делает из него доменный Order --- и бизнес-логика уже не знает, откуда он пришёл.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.models.order import Order, OrderStatus
from app.domain.models.order import OrderSource as OrderSourceKind

# Внимание: имя OrderSource занято интерфейсом источника (ТЗ §18), поэтому доменный
# перечень источников заказа импортируется под псевдонимом OrderSourceKind.


MIN_DESCRIPTION_CHARS = 40  # значение по умолчанию для нормализации (см. Settings)


@dataclass(slots=True)
class ExternalOrder:
    """Сырые данные заказа в терминах источника (до нормализации)."""

    source: str
    external_id: str | None = None
    title: str = ""
    description: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "RUB"
    url: str | None = None
    client_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime | None = None


@runtime_checkable
class OrderSource(Protocol):
    """Интерфейс источника заказов (ТЗ §18)."""

    name: str

    async def fetch_orders(self) -> list[ExternalOrder]:
        """Получить заказы из источника."""
        ...


def normalize_external_order(
    external: ExternalOrder, *, min_description_chars: int = MIN_DESCRIPTION_CHARS
) -> Order:
    """Normalizer: ExternalOrder -> Order (единая доменная модель).

    Ничего не выдумывает: если бюджета нет, он остаётся None (ТЗ §29.2).
    """
    source = external.source if external.source else OrderSourceKind.MANUAL.value
    order = Order(
        external_id=external.external_id,
        source=source,
        title=(external.title or "").strip(),
        description=(external.description or "").strip(),
        budget_min=external.budget_min,
        budget_max=external.budget_max,
        currency=external.currency or "RUB",
        url=external.url,
        client_name=external.client_name,
        status=OrderStatus.NEW.value,
        needs_review=False,
        raw_input=external.raw or None,
    )
    # Предварительная пометка: критически важных данных не хватает ---
    # окончательное решение всё равно принимает бизнес-логика (analysis_service).
    order.needs_review = bool(order.missing_data(min_description_chars))
    if external.fetched_at is not None:
        order.created_at = external.fetched_at
    return order


def utcnow() -> datetime:
    return datetime.now(UTC)
