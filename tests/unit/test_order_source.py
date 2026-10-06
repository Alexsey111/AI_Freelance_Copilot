"""Unit: адаптер источника заказов и нормализация (ТЗ §18) --- фундамент будущих источников."""

from __future__ import annotations

import asyncio

from app.domain.models.order import OrderStatus
from app.infrastructure.sources.base import ExternalOrder, normalize_external_order
from app.infrastructure.sources.manual_source import ManualOrderSource


def test_normalizer_maps_external_order_to_domain():
    external = ExternalOrder(
        source="manual",
        external_id="ord-1",
        title="  Заказ с пробелами  ",
        description="Описание достаточной длины, чтобы данных хватило. " * 2,
        budget_min=1000,
        budget_max=2000,
        raw={"whatever": "как есть"},
    )
    order = normalize_external_order(external, min_description_chars=40)
    assert order.title == "Заказ с пробелами"
    assert order.status == OrderStatus.NEW.value
    assert order.budget_min == 1000 and order.budget_max == 2000
    assert order.raw_input == {"whatever": "как есть"}
    assert order.needs_review is False


def test_normalizer_does_not_invent_missing_budget():
    external = ExternalOrder(source="manual", title="Заказ", description="Подробности лично.")
    order = normalize_external_order(external, min_description_chars=40)
    assert order.budget_min is None and order.budget_max is None
    assert order.needs_review is True
    assert "не указан бюджет" in order.missing_data(40)


def test_manual_source_queues_and_drains():
    source = ManualOrderSource(min_description_chars=10)
    source.push(ExternalOrder(source="manual", title="A", description="описание достаточной длины"))
    first_fetch = asyncio.run(source.fetch_orders())
    assert len(first_fetch) == 1
    assert asyncio.run(source.fetch_orders()) == []


def test_manual_source_interface_is_protocol_compatible():
    from app.infrastructure.sources.base import OrderSource

    assert isinstance(ManualOrderSource(), OrderSource)
    assert ManualOrderSource.name == "manual"


def test_unknown_source_value_is_kept_as_is():
    """Источники будущего (flru/kwork/...) не ломают нормализацию уже сейчас."""
    external = ExternalOrder(source="kwork", title="Заказ", description="описание " * 10, budget_min=500)
    order = normalize_external_order(external, min_description_chars=40)
    assert order.source == "kwork"
