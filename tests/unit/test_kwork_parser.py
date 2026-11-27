"""Разбор Kwork: проверяем на карточках, снятых с живой страницы 27.11.2026.

Kwork отдаёт ленту только браузеру, поэтому проверять разбор на «серверном» HTML нечего —
фикстура лежит в том виде, в каком её видит окно программы.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.sources.parsing import parse_kwork
from app.main import app

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "kwork_cards.json"


@pytest.fixture(scope="module")
def cards() -> list[str]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_карточки_разбираются_в_заказы(cards: list[str]) -> None:
    orders = parse_kwork(cards)
    assert len(orders) == 4
    assert all(order.source == "kwork" for order in orders)
    assert all(order.external_id and order.external_id.isdigit() for order in orders)
    assert all(order.url == f"https://kwork.ru/projects/{order.external_id}" for order in orders)


def test_берётся_допустимый_бюджет_а_не_желаемый(cards: list[str]) -> None:
    """«Желаемый 2 000» и «допустимый 6 000» — платить будут до 6 000, берём верхнюю границу."""
    orders = {order.external_id: order for order in parse_kwork(cards)}
    assert orders["3275880"].budget_max == 6000
    assert orders["3275883"].budget_max == 1500
    # Когда есть только цена, она и есть граница.
    assert orders["3275885"].budget_max == 500
    assert all(order.budget_min is None for order in orders.values())


def test_описание_берётся_полное_а_не_обрезанное(cards: list[str]) -> None:
    orders = {order.external_id: order for order in parse_kwork(cards)}
    long_order = orders["3275880"]
    assert len(long_order.description) > 500
    assert "Показать полностью" not in long_order.description
    assert "Скрыть" not in long_order.description
    assert "Ozon" in long_order.description or "OZON" in long_order.description


def test_число_откликов_и_заказчик(cards: list[str]) -> None:
    orders = {order.external_id: order for order in parse_kwork(cards)}
    assert orders["3275880"].responses == 1
    assert orders["3275885"].responses == 0
    assert orders["3275885"].client_name == "ykroperr"


def test_возраст_не_выдумывается_а_срок_считается(cards: list[str]) -> None:
    """Время размещения Kwork не показывает: published_at пуст, а «Осталось» — срок от сейчас."""
    moment = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
    orders = parse_kwork(cards[:1], now=moment)
    order = orders[0]
    assert order.published_at is None
    assert order.deadline_at is not None
    assert order.deadline_at > moment
    assert (order.deadline_at - moment).total_seconds() == pytest.approx((2 * 24 + 23) * 3600)


def test_мусор_не_становится_заказом() -> None:
    assert parse_kwork([]) == []
    assert parse_kwork(["<div class='want-card'>пустая оболочка</div>"]) == []


def test_api_принимает_карточки_из_окна(cards: list[str]) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/sources/ingest", json={"source": "kwork", "cards": cards})
        assert response.status_code == 200
        body = response.json()
        assert body["fetched"] == 4
        assert body["available"] is True
        # Повторная отправка тех же карточек не плодит дубли.
        again = client.post(
            "/api/v1/sources/ingest", json={"source": "kwork", "cards": cards}
        ).json()
        assert again["created"] == 0
        assert again["unchanged"] == 4


def test_kwork_не_тянется_загрузкой_страницы() -> None:
    """Ленту Kwork нельзя получить запросом: об этом говорится прямо, а не «заказов нет»."""
    with TestClient(app) as client:
        response = client.post("/api/v1/sources/refresh", json={"source": "kwork"})
        assert response.status_code == 409
        assert "браузер" in response.json()["detail"]
        items = client.post("/api/v1/sources/refresh", json={"source": "all", "limit": 1}).json()[
            "items"
        ]
        assert [item["source"] for item in items] == ["flru", "freelance_ru"]


def test_браузерный_разбор_не_принимает_чужие_источники(cards: list[str]) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/sources/ingest", json={"source": "flru", "cards": cards})
        assert response.status_code == 422
