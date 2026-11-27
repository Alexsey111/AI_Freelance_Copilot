"""Unit: число запросов к базе на одну операцию (урок 2, п.5 практики).

Дефект N+1 не виден на 20 строках: 21 запрос вместо 1 отрабатывает за миллисекунды.
Видно его только счётчиком. Поэтому здесь число SQL-операторов на ОДИН HTTP-запрос
сравнивается на 1 заказе и на 15 заказах: если число выросло --- в коде цикл с запросом.

Порог задан равенством, а не «примерно»: любое «столько же, сколько строк» --- провал.
"""

from __future__ import annotations

from sqlalchemy import event

from app.config import Settings
from app.main import create_app

SHOWCASE_BASELINE = 6  # замер 27.11.2026: витрина, 1 заказ и 15 заказов -> по 6 запросов


def _queries_with(client, method: str, url: str, **kwargs) -> int:
    """Считает SQL-операторы, выполненные за один вызов."""
    engine = client.app.state.database.engine
    counter = {"count": 0}

    def _before(*_args, **_kwargs):  # pragma: no cover - тривиальный счётчик
        counter["count"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 200, response.text
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return counter["count"]


def _create_orders(client, payload: dict, count: int) -> list[int]:
    ids = []
    for index in range(count):
        body = dict(payload)
        body["title"] = f"{payload['title']} #{index}"
        body["external_id"] = f"ext-{index}"
        ids.append(client.post("/api/v1/orders", json=body).json()["id"])
    return ids


def _fresh_client():
    """Отдельное приложение на своей in-memory базе: мерить надо на чистой таблице."""
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite://",
        llm_provider="mock",
        min_description_chars=40,
    )
    client = TestClient(create_app(settings))
    client.__enter__()
    return client


def test_showcase_query_count_is_constant(sample_payload):
    """Число запросов витрины не зависит от количества заказов в выборке.

    Сравнение строгое: «столько же, сколько строк» --- это и есть дефект.
    """
    small = _fresh_client()
    try:
        _create_orders(small, sample_payload, 1)
        one_order = _queries_with(small, "get", "/api/v1/orders")
    finally:
        small.__exit__(None, None, None)

    big = _fresh_client()
    try:
        _create_orders(big, sample_payload, 15)
        fifteen_orders = _queries_with(big, "get", "/api/v1/orders")
    finally:
        big.__exit__(None, None, None)

    assert one_order == fifteen_orders, (
        f"витрина делает {fifteen_orders} запросов на 15 заказах против {one_order} "
        "на одном: это N+1"
    )
    assert one_order <= SHOWCASE_BASELINE


def test_single_analyze_is_constant_regardless_of_table_size(client, sample_payload):
    """Один разбор заказа не должен зависеть от числа заказов в базе."""
    first = _create_orders(client, sample_payload, 1)[0]
    small = _queries_with(client, "post", f"/api/v1/orders/{first}/analyze", json={})

    _create_orders(client, sample_payload, 14)
    second = _create_orders(client, sample_payload, 1)[0]
    big = _queries_with(client, "post", f"/api/v1/orders/{second}/analyze", json={})

    assert big <= small + 1, f"разбор на большой базе делает {big} запросов вместо {small}"
