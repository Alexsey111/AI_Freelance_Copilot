"""Integration: Endpoint №1 и №2 --- создание заказа и витрина (ТЗ §9, §10, §32)."""

from __future__ import annotations

from app.domain.models.order import OrderStatus


def test_create_order_returns_id_and_status(client, sample_payload):
    response = client.post("/api/v1/orders", json=sample_payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["status"] == OrderStatus.NEW.value


def test_created_order_is_visible_in_the_showcase(client, sample_payload):
    created = client.post("/api/v1/orders", json=sample_payload).json()

    listing = client.get("/api/v1/orders")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["id"] for item in body["items"]] == [created["id"]]
    assert body["items"][0]["budget_max"] == 50000
    assert body["items"][0]["source"] == "manual"


def test_order_card_exposes_raw_input(client, sample_payload):
    created = client.post("/api/v1/orders", json=sample_payload).json()
    card = client.get(f"/api/v1/orders/{created['id']}")
    assert card.status_code == 200
    body = card.json()
    assert body["raw_input"]["title"] == sample_payload["title"]
    assert body["description"].startswith("Нужен Telegram-бот")


def test_vague_order_is_flagged_for_review_at_creation(client, vague_payload):
    """Данных не хватает уже на входе: заказ сразу помечается (ТЗ §13)."""
    created = client.post("/api/v1/orders", json=vague_payload).json()
    assert created["needs_review"] is True


def test_pagination_and_filters(client):
    for index in range(5):
        client.post(
            "/api/v1/orders",
            json={
                "title": f"Заказ {index}",
                "description": "Описание достаточной длины для нормализации. " * 2,
                "budget_min": 1000 * (index + 1),
            },
        )
    page = client.get("/api/v1/orders", params={"page": 2, "page_size": 2}).json()
    assert page["total"] == 5
    assert page["page"] == 2
    assert len(page["items"]) == 2

    filtered = client.get("/api/v1/orders", params={"needs_review": "false"}).json()
    assert filtered["total"] == 5

    searched = client.get("/api/v1/orders", params={"search": "Заказ 3"}).json()
    assert searched["total"] == 1


def test_invalid_status_filter_is_rejected(client):
    response = client.get("/api/v1/orders", params={"status": "какой-то_статус"})
    assert response.status_code == 422


def test_unknown_source_is_rejected(client, sample_payload):
    payload = dict(sample_payload, source="vk")
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 422


def test_budget_validation(client):
    response = client.post(
        "/api/v1/orders",
        json={"title": "Заказ", "budget_min": 50000, "budget_max": 10000},
    )
    assert response.status_code == 422


def test_missing_order_returns_404(client):
    assert client.get("/api/v1/orders/999").status_code == 404


def test_deduplication_by_source_and_external_id(client, sample_payload):
    payload = dict(sample_payload, external_id="fl-12345")
    first = client.post("/api/v1/orders", json=payload).json()
    second = client.post("/api/v1/orders", json=payload).json()
    assert first["id"] == second["id"]
    assert client.get("/api/v1/orders").json()["total"] == 1
