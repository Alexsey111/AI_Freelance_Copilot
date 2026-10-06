"""Карточка заказа отдаёт последний анализ (иначе панель и клиент API видят null)."""

from __future__ import annotations


def _create_and_analyze(client, external_id: str = "detail-01") -> int:
    created = client.post(
        "/api/v1/orders",
        json={
            "title": "Разработка Telegram-бота на Python",
            "description": (
                "Нужен бот на Python с интеграцией LLM, стек: FastAPI, REST API, Docker, "
                "PostgreSQL, парсинг и выгрузка в Excel. Бюджет 30000-50000 руб, срок 3 недели."
            ),
            "budget_min": 30000,
            "budget_max": 50000,
            "currency": "RUB",
            "source": "manual",
            "external_id": external_id,
        },
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    analyzed = client.post(f"/api/v1/orders/{order_id}/analyze", json={})
    assert analyzed.status_code == 200, analyzed.text
    return order_id


def test_order_detail_contains_latest_analysis(client):
    """GET /orders/{id} должен вернуть результат анализа, а не null."""
    order_id = _create_and_analyze(client)

    detail = client.get(f"/api/v1/orders/{order_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["latest_analysis"] is not None, "карточка заказа потеряла последний анализ"
    latest = body["latest_analysis"]
    assert latest["recommendation"] in {"apply", "skip", "review"}
    assert latest["match_score"] is not None


def test_order_detail_analysis_matches_showcase(client):
    """Карточка и витрина должны показывать один и тот же последний анализ."""
    order_id = _create_and_analyze(client, external_id="detail-02")

    detail = client.get(f"/api/v1/orders/{order_id}").json()["latest_analysis"]
    listed = next(
        item
        for item in client.get("/api/v1/orders", params={"search": "Telegram-бота"}).json()["items"]
        if item["id"] == order_id
    )["latest_analysis"]

    assert detail == listed, "карточка заказа и витрина расходятся в последнем анализе"


def test_order_detail_latest_analysis_is_the_newest_run(client):
    """При нескольких запусках карточка показывает последний по времени анализ."""
    order_id = _create_and_analyze(client, external_id="detail-03")
    first = client.get(f"/api/v1/orders/{order_id}").json()["latest_analysis"]

    client.post(f"/api/v1/orders/{order_id}/analyze", json={})
    second = client.get(f"/api/v1/orders/{order_id}").json()["latest_analysis"]

    assert second["id"] > first["id"], "карточка показывает не последний анализ"


def test_order_detail_without_analysis_has_none(client):
    """У заказа без анализа поле остаётся пустым (не выдумываем результат)."""
    created = client.post(
        "/api/v1/orders",
        json={
            "title": "Заказ без анализа",
            "description": "Просто заказ для проверки пустого поля, без запуска ИИ.",
            "source": "manual",
            "external_id": "detail-04",
        },
    )
    order_id = created.json()["id"]
    body = client.get(f"/api/v1/orders/{order_id}").json()
    assert body["latest_analysis"] is None
