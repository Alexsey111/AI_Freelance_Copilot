"""Источник manual: заказ создан вручную через API (ТЗ §5.1, §9).

Реального подключения к площадкам в MVP нет и не требуется (ТЗ §22).
"""

from __future__ import annotations

from app.domain.models.order import Order
from app.infrastructure.sources.base import ExternalOrder, normalize_external_order


class ManualOrderSource:
    """Заказы, пришедшие руками/через API. fetch_orders() намеренно пуст."""

    name = "manual"

    def __init__(
        self, pending: list[ExternalOrder] | None = None, *, min_description_chars: int = 40
    ) -> None:
        self._pending = list(pending or [])
        self.min_description_chars = min_description_chars

    async def fetch_orders(self) -> list[ExternalOrder]:
        pending, self._pending = self._pending, []
        return pending

    def push(self, external: ExternalOrder) -> None:
        """Положить заказ в очередь источника (используется API-слоем)."""
        self._pending.append(external)

    def to_domain(self, external: ExternalOrder) -> Order:
        return normalize_external_order(
            external, min_description_chars=self.min_description_chars
        )
