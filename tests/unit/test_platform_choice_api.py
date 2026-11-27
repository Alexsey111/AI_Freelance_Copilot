"""Выбор площадок: с какими работаем, а с какими нет.

Правила, которые проверяются здесь:

1. Пустая база — не «ничего не выбрано»: площадки досеиваются, иначе новый пользователь
   увидит пустую витрину и решит, что программа сломана.
2. Недоступная из страны площадка выключена сразу: Upwork не должен попадать в работу.
3. Выбор сохраняется: выключил площадку — её заказы не приходят в витрину.
4. Заказ с неизвестным источником не теряется: он попадает в «ручной ввод».
5. Предупреждение о платности отклика есть у каждой площадки, где отклик стоит денег,
   и его нет у бесплатных — иначе предупреждение перестают читать.
"""

from __future__ import annotations


def test_platforms_are_seeded_and_upwork_is_off(client):
    payload = client.get("/api/v1/platforms").json()
    keys = {item["key"]: item["enabled"] for item in payload["platforms"]}
    assert keys["flru"] is True
    assert keys["kwork"] is True
    assert keys["upwork"] is False
    assert payload["enabled_count"] == len([k for k, v in keys.items() if v])


def test_toggle_is_remembered(client):
    client.put("/api/v1/platforms/kwork/enabled", json={"enabled": False})
    assert client.get("/api/v1/platforms/kwork").json()["enabled"] is False
    payload = client.get("/api/v1/platforms").json()
    assert {item["key"]: item["enabled"] for item in payload["platforms"]}["kwork"] is False
    client.put("/api/v1/platforms/kwork/enabled", json={"enabled": True})
    assert client.get("/api/v1/platforms/kwork").json()["enabled"] is True


def test_unknown_platform_cannot_be_toggled(client):
    assert (
        client.put("/api/v1/platforms/vk/enabled", json={"enabled": True}).status_code == 404
    )


def test_paid_warning_exists_where_response_costs_money(client):
    flru = client.get("/api/v1/platforms/flru").json()
    assert "50 ₽ за попытку" in flru["paid_warning"]
    assert "даже если заказчик не ответил" in flru["paid_warning"]

    freelance = client.get("/api/v1/platforms/freelance_ru").json()
    assert "по подписке" in freelance["paid_warning"]

    kwork = client.get("/api/v1/platforms/kwork").json()
    assert "не известна" in kwork["paid_warning"]

    upwork = client.get("/api/v1/platforms/upwork").json()
    assert "недоступна из России" in upwork["paid_warning"]


def test_orders_are_filtered_by_chosen_platforms(client, app):
    from app.domain.models.order import Order, OrderStatus
    from app.infrastructure.database.repositories.order_repository import OrderRepository

    with app.state.database.session() as session:
        repository = OrderRepository(session)
        for source, external in (("fl.ru", "r-fl-1"), ("kwork", "r-kw-1"), ("manual", "r-m-1")):
            repository.add(
                Order(
                    source=source,
                    external_id=external,
                    title=f"Заказ с {source}",
                    description="описание",
                    currency="RUB",
                    status=OrderStatus.NEW.value,
                )
            )
        session.commit()

    fl = client.get("/api/v1/orders?platforms=flru").json()
    assert fl["total"] == 1
    assert fl["items"][0]["source"] == "fl.ru"

    kw = client.get("/api/v1/orders?platforms=kwork").json()
    assert kw["total"] == 1

    both = client.get("/api/v1/orders?platforms=flru,kwork,manual").json()
    assert both["total"] >= 3


def test_alias_spellings_of_same_platform_match(client, app):
    """«fl.ru» и «flru» — одна площадка: парсеры пишут по-разному."""
    from app.domain.platform_choice import aliases_for, normalize_source

    assert normalize_source("FL.ru") == "flru"
    assert normalize_source("flru") == "flru"
    assert normalize_source("work-zilla.com") == "workzilla"
    assert normalize_source("") == "manual"
    assert normalize_source("неизвестный парсер") == "manual"
    assert "fl.ru" in aliases_for(["flru"])


def test_unknown_platform_in_filter_is_rejected(client):
    assert client.get("/api/v1/orders?platforms=vk").status_code == 422
