"""API-тесты: журнал откликов и цена одного найма.

Смысл: отклик на бирже стоит денег, поэтому экономика заказа считается не «бюджет ÷ часы»,
а с вычетом цены попыток. Проверяем, что журнал ведётся, воронка считается и что найм
переводит заказ в работу.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _order(app, *, budget=30000, title="Telegram-бот"):
    from app.domain.models.order import Order, OrderStatus
    from app.infrastructure.database.repositories.order_repository import OrderRepository

    with app.state.database.session() as session:
        order = OrderRepository(session).add(
            Order(
                source="manual",
                external_id=f"r-{title}-{budget}",
                title=title,
                description="описание",
                budget_min=budget,
                currency="RUB",
                status=OrderStatus.NEW.value,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
        return order.id


def test_response_is_recorded_and_listed(client, app):
    order_id = _order(app)
    created = client.post(
        "/api/v1/responses",
        json={"order_id": order_id, "platform": "fl.ru", "cost_rub": 150, "status": "sent"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["platform"] == "fl.ru"
    assert body["status_label"] == "отправлен"

    listed = client.get("/api/v1/responses").json()
    assert listed[0]["order_id"] == order_id


def test_funnel_counts_cost_per_hire(client, app):
    first = _order(app, budget=30000)
    second = _order(app, budget=50000)
    client.post("/api/v1/responses", json={"order_id": first, "cost_rub": 100, "status": "silent"})
    client.post("/api/v1/responses", json={"order_id": second, "cost_rub": 300, "status": "hired"})

    funnel = client.get("/api/v1/responses/funnel").json()
    assert funnel["sent"] == 2
    assert funnel["hired"] == 1
    assert funnel["cost"] == 400.0
    assert funnel["cost_per_hire"] == 400.0
    assert funnel["hire_rate"] == 0.5
    assert funnel["hired_money"] == 50000.0
    assert funnel["modes"]["draft_only"].startswith("только черновик")


def test_hired_moves_order_into_work(client, app):
    order_id = _order(app)
    client.post("/api/v1/responses", json={"order_id": order_id, "status": "hired"})
    active = client.get("/api/v1/time-norms/workload").json()
    assert active["orders"] == 1


def test_unknown_status_and_order_are_rejected(client):
    assert (
        client.post("/api/v1/responses", json={"order_id": 1, "status": "оплачен"}).status_code
        == 422
    )
    assert client.post("/api/v1/responses", json={"order_id": 99999}).status_code == 404


def test_net_rate_shows_when_paid_responses_eat_the_budget():
    """(Бюджет − цена попыток) ÷ часы: 15 000 ₽ за 8 ч при 500 ₽ за отклик и 10 попытках."""
    from app.domain.responses import NetRate

    case = NetRate(budget=15_000, hours=8, response_cost=500, expected_responses=10)
    assert case.spend == 5000
    assert case.net_budget == 10_000
    assert case.net_rate == 1_250
    hopeless = NetRate(budget=3_000, hours=8, response_cost=500, expected_responses=10)
    assert hopeless.worth_it is False
