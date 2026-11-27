"""API-тесты: нормы времени по типам задач и распределение недели.

Смысл проверок: часы берутся из нормы по ключевым словам (и это объясняется словами,
а не «модель решила»), норма правится из окна программы, а окно загрузки считает
занятые часы, свободные и долю загрузки — по тем же правилам, что и отбор заказов.
"""

from __future__ import annotations


def test_norms_are_seeded_so_window_is_not_empty(client):
    items = client.get("/api/v1/time-norms").json()
    by_kind = {item["task_kind"]: item for item in items}
    assert by_kind["bot"]["hours"] == 8.0
    assert by_kind["parser"]["hours"] == 6.0
    assert "telegram" in by_kind["bot"]["keywords"]


def test_estimate_explains_itself(client):
    answer = client.post(
        "/api/v1/time-norms/estimate",
        json={"title": "Разработка Telegram-бота на Python", "description": "Меню, оплата"},
    ).json()
    assert answer["task_kind"] == "bot"
    assert answer["hours"] == 8.0
    assert "telegram" in answer["reason"]


def test_estimate_says_so_when_type_is_unknown(client):
    answer = client.post(
        "/api/v1/time-norms/estimate",
        json={"title": "Нужно что-то сделать", "description": "Подробности в личке"},
    ).json()
    assert answer["hours"] is None
    assert "не определён" in answer["reason"]


def test_skills_catalog_covers_many_professions(client):
    payload = client.get("/api/v1/time-norms/skills-catalog").json()
    keys = {group["key"] for group in payload["professions"]}
    assert {"dev", "text", "design", "marketing", "video", "translate"} <= keys
    assert payload["total"] >= 100
    assert any("Копирайтинг" in group["skills"] for group in payload["professions"])


def test_skills_catalog_search_filters(client):
    payload = client.get("/api/v1/time-norms/skills-catalog?q=figma").json()
    skills = [s for group in payload["professions"] for s in group["skills"]]
    assert skills == ["Figma"]


def test_missing_norms_are_added_to_existing_base(client):
    """Новая версия приносит нормы для копирайтера — они должны появиться и у старой установки."""
    client.delete("/api/v1/time-norms/article")
    kinds = {item["task_kind"] for item in client.get("/api/v1/time-norms").json()}
    assert "article" in kinds


def test_estimate_works_for_text_work_not_only_it(client):
    answer = client.post(
        "/api/v1/time-norms/estimate",
        json={"title": "Нужна статья 8 000 знаков про налоги", "description": "для блога"},
    ).json()
    assert answer["task_kind"] == "article"
    assert answer["hours"] == 4.0


def test_norm_hours_are_editable(client):
    updated = client.put("/api/v1/time-norms/bot", json={"hours": 11.5})
    assert updated.status_code == 200
    assert updated.json()["hours"] == 11.5
    answer = client.post(
        "/api/v1/time-norms/estimate", json={"title": "Telegram-бот для заявок"}
    ).json()
    assert answer["hours"] == 11.5


def test_norm_rejects_zero_or_negative_hours(client):
    assert client.put("/api/v1/time-norms/bot", json={"hours": 0}).status_code == 422
    assert client.put("/api/v1/time-norms/bot", json={"hours": -3}).status_code == 422


def test_workload_counts_approved_orders_and_shows_free_hours(client, app):
    from datetime import UTC, datetime

    from app.domain.models.order import Order, OrderStatus
    from app.infrastructure.database.repositories.order_repository import OrderRepository

    with app.state.database.session() as session:
        repository = OrderRepository(session)
        repository.add(
            Order(
                source="manual",
                external_id="w-1",
                title="Telegram-бот для заявок",
                description="Меню и приём заявок",
                budget_min=30_000,
                currency="RUB",
                status=OrderStatus.APPROVED.value,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()

    load = client.get("/api/v1/time-norms/workload").json()
    assert load["orders"] == 1
    assert load["booked_hours"] == 8.0
    assert load["capacity_hours"] == 45.0
    assert load["free_hours"] == 37.0
    assert load["money"] == 30_000.0
    assert load["rows"][0]["task_kind"] == "bot"
    assert 0 < load["load_share"] < 1
