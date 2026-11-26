"""Unit: маскирование ПДн на границе «код → модель» (152-ФЗ; правовой паспорт проекта).

Проверяется не «функция что-то вернула», а граница: в промпт, который уходит внешнему
провайдеру, не попадают телефон, почта, ссылка и имя клиента.
"""

from __future__ import annotations

import json

from app.domain.models.order import Order
from app.domain.models.profile import Profile
from app.domain.privacy import (
    MASK_ADDRESS,
    MASK_CLIENT,
    MASK_EMAIL,
    MASK_LINK,
    MASK_NAME,
    MASK_PHONE,
    mask_order_payload,
    mask_personal_data,
)
from app.infrastructure.llm.base import build_order_prompt

PROFILE = Profile(id=1, name="Тест", skills=["Python", "LLM", "Docker"])


def _masked(text: str) -> str:
    """Маска возвращает Optional; в тестах вход всегда непустой — фиксируем это явно."""
    result = mask_personal_data(text)
    assert result is not None
    return result


def test_phone_is_masked_in_every_usual_format():
    text = (
        "Звоните +7 (916) 123-45-67, либо 8-800-555-35-35, "
        "либо пишите на 89161234567."
    )
    masked = _masked(text)

    assert masked.count(MASK_PHONE) == 3
    for leaked in ("916", "123-45-67", "800", "555-35-35", "89161234567"):
        assert leaked not in masked


def test_email_link_and_telegram_are_masked():
    text = (
        "Заказчик Иван, почта ivan.petrov@example.com, профиль "
        "https://fl.ru/projects/123, телеграм @ivan_petrov"
    )
    masked = _masked(text)

    assert "@example.com" not in masked
    assert "fl.ru" not in masked
    assert "@ivan_petrov" not in masked
    assert masked.count(MASK_EMAIL) == 1
    assert masked.count(MASK_LINK) == 2


def test_full_name_and_initials_are_masked_plain_text_is_not():
    masked = _masked(
        "Заказчик: Иванов Иван Иванович. Контакт — Петров П.С. "
        "Стек: Python и FastAPI, деплой в Docker."
    )

    assert "Иванов" not in masked and "Петров" not in masked
    assert masked.count(MASK_NAME) == 2
    assert "Python и FastAPI" in masked


def test_address_is_masked_but_ordinary_words_survive():
    masked = _masked(
        "Точка: г. Барнаул, ул. Ленина, д. 12, кв. 5. Работа в доме культуры."
    )

    assert "Барнаул" not in masked and "Ленина" not in masked
    assert masked.count(MASK_ADDRESS) == 4
    assert "доме культуры" in masked


def test_order_payload_masks_client_and_link_keeps_numbers():
    payload = {
        "id": 7,
        "title": "Нужен бот",
        "description": "Связаться: +7 916 123-45-67",
        "budget_min": 30000,
        "budget_max": None,
        "client_name": "Иванов Иван",
        "url": "https://fl.ru/projects/7",
        "source": "flru",
        "missing_data": ["не указан бюджет"],
    }
    masked = mask_order_payload(payload)

    assert masked["client_name"] == MASK_CLIENT
    assert masked["url"] == MASK_LINK
    assert masked["budget_min"] == 30000
    assert masked["missing_data"] == ["не указан бюджет"]
    assert "916" not in masked["description"]
    assert payload["client_name"] == "Иванов Иван"  # исходник не мутируется


def test_prompt_sent_to_provider_contains_no_personal_data():
    """Главная проверка границы: то же самое, что уйдёт в HTTP-запрос к модели."""
    order = Order(
        id=1,
        title="Telegram-бот для Иванова Ивана Ивановича",
        description=(
            "Нужен бот на Python с LLM. Связь: +7 (916) 123-45-67, "
            "почта ivan@example.com, профиль https://fl.ru/u/ivan."
        ),
        budget_min=30000,
        budget_max=50000,
        client_name="Иванов Иван Иванович",
        url="https://fl.ru/projects/1",
    )

    prompt = build_order_prompt(order, PROFILE)
    sent = prompt.system + prompt.user

    for leaked in ("916", "ivan@example.com", "fl.ru/u/ivan", "Иванов", "projects/1"):
        assert leaked not in sent
    assert MASK_PHONE in sent and MASK_EMAIL in sent and MASK_CLIENT in sent

    payload = json.loads(prompt.user.split("ДАННЫЕ О ЗАКАЗЕ:")[1].split("ПРОФИЛЬ")[0])
    assert payload["budget_max"] == 50000
    assert payload["description"].startswith("Нужен бот на Python с LLM")
