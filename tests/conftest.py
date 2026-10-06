"""Общая обвязка тестов: приложение на in-memory SQLite + MockProvider.

Ни один тест не ходит в сеть и не тратит деньги: провайдер всегда mock (ТЗ §17).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "test")

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite://",
        llm_provider="mock",
        min_description_chars=40,
    )


@pytest.fixture()
def app(settings):
    application = create_app(settings)
    yield application
    application.state.database.dispose()


@pytest.fixture()
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sample_payload() -> dict:
    """Хороший заказ: данных достаточно, профиль подходит."""
    return {
        "title": "Разработка Telegram-бота на Python с ИИ",
        "description": (
            "Нужен Telegram-бот на Python с интеграцией LLM. Требуется опыт FastAPI, "
            "REST API, Docker, работа с PostgreSQL. Бюджет фиксированный, срок 3 недели. "
            "Опишите, пожалуйста, похожие проекты и предложите план работ."
        ),
        "budget_min": 30000,
        "budget_max": 50000,
        "currency": "RUB",
        "url": "https://example.com/order/123",
        "source": "manual",
    }


@pytest.fixture()
def vague_payload() -> dict:
    """Плохой заказ: не хватает критически важных данных (ТЗ §13)."""
    return {
        "title": "Нужен разработчик Python",
        "description": "Подробности обсудим лично.",
        "source": "manual",
    }
