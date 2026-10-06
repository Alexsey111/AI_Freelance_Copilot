"""Демо-данные для защиты: несколько заказов через Endpoint №1 и прогон ИИ-анализа.

Запуск (backend должен быть уже поднят):
    ./.venv/Scripts/python.exe scripts/seed_demo.py
    ./.venv/Scripts/python.exe scripts/seed_demo.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys

import requests

DEMO_ORDERS = [
    {
        "title": "Разработка Telegram-бота на Python с ИИ-ассистентом",
        "description": (
            "Нужен Telegram-бот на Python с интеграцией LLM (GPT). Требуется опыт FastAPI, "
            "REST API, Docker, работа с PostgreSQL. Бюджет фиксированный, срок 3 недели. "
            "Опишите похожие проекты и предложите план работ."
        ),
        "budget_min": 30000,
        "budget_max": 50000,
        "currency": "RUB",
        "url": "https://example.com/orders/1001",
        "client_name": "Иван",
        "source": "manual",
        "external_id": "demo-1001",
    },
    {
        "title": "Нужен разработчик Python",
        "description": "Подробности обсудим лично.",
        "source": "manual",
        "external_id": "demo-1002",  # нет бюджета и нет объёма работ --- уйдёт на проверку
    },
    {
        "title": "Вёрстка лендинга на Tilda",
        "description": (
            "Требуется свёрстанный лендинг на Tilda с адаптивом под мобильные устройства. "
            "Дизайн готов в Figma, тексты предоставлены. Бюджет 25000 рублей, срок 5 дней. "
            "Опыт вёрстки обязателен, покажите портфолио."
        ),
        "budget_min": 25000,
        "budget_max": 25000,
        "currency": "RUB",
        "source": "manual",
        "external_id": "demo-1003",  # профиль не подходит: система предложит пропустить
    },
    {
        "title": "Автоматизация отчётности: парсер на Python + выгрузка в Excel",
        "description": (
            "Есть сайт-агрегатор, нужно ежедневно собирать данные (Python, парсинг, BeautifulSoup), "
            "складывать в PostgreSQL и формировать Excel-отчёт. Требуется Docker для запуска по "
            "расписанию, REST API для выдачи отчёта. Бюджет 40000-60000 руб."
        ),
        "budget_min": 40000,
        "budget_max": 60000,
        "currency": "RUB",
        "source": "manual",
        "external_id": "demo-1004",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Наполнить систему демонстрационными данными")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--analyze", action="store_true", default=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        health = requests.get(f"{base}/api/v1/health", timeout=10).json()
    except requests.RequestException as exc:
        print(f"Backend недоступен по адресу {base}: {exc}")
        print("Сначала запустите: uvicorn app.main:app --port 8000")
        return 1

    print(f"Backend: {health['status']} · провайдер LLM: {health['provider']['name']}")
    if health["provider"]["is_live"]:
        print("ВНИМАНИЕ: активен реальный LLM-провайдер, запуск анализа тратит деньги.")

    created_ids = []
    for payload in DEMO_ORDERS:
        response = requests.post(f"{base}/api/v1/orders", json=payload, timeout=20)
        response.raise_for_status()
        body = response.json()
        flag = " (сразу на проверку)" if body.get("needs_review") else ""
        print(f"  заказ #{body['id']}: {payload['title'][:50]}{flag}")
        created_ids.append(body["id"])

    print("\nИИ-анализ:")
    for order_id in created_ids:
        response = requests.post(
            f"{base}/api/v1/orders/{order_id}/analyze", json={}, timeout=120
        )
        response.raise_for_status()
        body = response.json()
        result = body["result"]
        match = "—" if result["match_score"] is None else f"{result['match_score'] * 100:.0f}%"
        line = (
            f"  #{order_id}: {result['recommendation']:>6} · match {match:>4} · "
            f"{body['duration_ms']} мс · аудит: {body['audit_status']}"
        )
        if result["needs_review"]:
            line += f" · на проверку: {result['review_reason']}"
        print(line)

    metrics = requests.get(f"{base}/api/v1/metrics", timeout=20).json()
    print("\nМетрики:")
    print(json.dumps(
        {
            "orders_total": metrics["orders_total"],
            "analyses_total": metrics["analyses_total"],
            "orders_needs_review": metrics["orders_needs_review"],
            "json_valid_rate": metrics["json_valid_rate"],
            "review_share": metrics["review_share"],
            "avg_analyze_duration_ms": metrics["avg_analyze_duration_ms"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    print("\nГотово. Откройте панель: streamlit run frontend/streamlit/app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
