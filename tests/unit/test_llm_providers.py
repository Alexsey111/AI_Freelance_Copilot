"""Unit: провайдеры LLM и фабрика (ТЗ §16, §17).

Реальные сетевые вызовы не делаются: клиент OpenAI подменяется фейком, поэтому проверяется
именно наш код --- сборка промпта, разбор ответа, обработка таймаута и ошибок транспорта.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.domain.models.analysis import Recommendation
from app.domain.models.order import Order
from app.domain.models.profile import Profile
from app.infrastructure.llm.base import (
    LLMError,
    LLMInvalidResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    build_order_prompt,
)
from app.infrastructure.llm.factory import build_llm_provider
from app.infrastructure.llm.mock_adapter import MockProvider
from app.infrastructure.llm.openai_adapter import OpenAIProvider

ORDER = Order(
    id=15,
    title="Разработка Telegram-бота",
    description="Нужен бот на Python с интеграцией LLM, REST API, Docker.",
    budget_min=30000,
    budget_max=50000,
)
PROFILE = Profile(id=1, name="Основной профиль", skills=["Python", "LLM", "REST API"], summary="Python-разработчик")

# Полный ответ по схеме ТЗ §12: без needs_review/review_reason схема его отвергнет,
# и это проверяется отдельным тестом ниже.
VALID_RAW = (
    '{"match_score": 0.67, "recommendation": "apply", "reason": "подходит", '
    '"matched_skills": ["Python"], "missing_skills": ["Docker"], '
    '"draft_reply": "Здравствуйте! Готов обсудить проект.", '
    '"needs_review": false, "review_reason": null}'
)


class _FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None, delay: float = 0.0):
        self.content = content
        self.error = error
        self.delay = delay

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _provider(completions: _FakeCompletions, **kwargs) -> OpenAIProvider:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAIProvider(
        model="test-model", api_key="test-key", client=client, rules={"min_description_chars": 40}, **kwargs
    )


async def test_openai_provider_parses_valid_json():
    provider = _provider(_FakeCompletions(content=VALID_RAW))
    result = await provider.analyze_order(ORDER, PROFILE)
    assert result.recommendation is Recommendation.APPLY
    assert result.match_score == 0.67
    assert provider.last_raw_output == VALID_RAW


async def test_openai_provider_asks_for_json_object():
    completions = _FakeCompletions(content=VALID_RAW)
    await _provider(completions).analyze_order(ORDER, PROFILE)
    assert completions.last_kwargs["response_format"] == {"type": "json_object"}
    assert completions.last_kwargs["model"] == "test-model"


async def test_openai_provider_rejects_incomplete_answer():
    """Модель забыла обязательное поле --- ответ не проходит схему (ТЗ §12)."""
    incomplete = '{"match_score": 0.67, "recommendation": "apply", "reason": "подходит"}'
    provider = _provider(_FakeCompletions(content=incomplete))
    with pytest.raises(LLMInvalidResponseError):
        await provider.analyze_order(ORDER, PROFILE)


async def test_openai_provider_rejects_garbage():
    provider = _provider(_FakeCompletions(content="извините, не могу"))
    with pytest.raises(LLMInvalidResponseError):
        await provider.analyze_order(ORDER, PROFILE)


async def test_openai_provider_raises_unavailable_on_transport_error():
    provider = _provider(_FakeCompletions(error=RuntimeError("connection reset")))
    with pytest.raises(LLMUnavailableError):
        await provider.analyze_order(ORDER, PROFILE)


async def test_openai_provider_raises_timeout():
    provider = _provider(_FakeCompletions(content=VALID_RAW, delay=0.6), timeout_s=0.05)
    with pytest.raises(LLMTimeoutError):
        await provider.analyze_order(ORDER, PROFILE)


def test_openai_provider_requires_api_key():
    with pytest.raises(LLMUnavailableError):
        OpenAIProvider(model="m", api_key=None)


def test_prompt_contains_facts_and_version():
    prompt = build_order_prompt(ORDER, PROFILE, rules={"min_description_chars": 40})
    assert prompt.version == "v1.0"
    assert "Разработка Telegram-бота" in prompt.user
    assert "Python" in prompt.user
    assert "не указан бюджет" not in prompt.user  # бюджет указан, значит и выдумывать нечего
    assert "JSON" in prompt.user


def test_prompt_marks_missing_data_without_inventing_it():
    vague = Order(id=16, title="Нужен разработчик Python", description="Подробности лично.")
    prompt = build_order_prompt(vague, PROFILE, rules={"min_description_chars": 40})
    assert "не указан бюджет" in prompt.user
    assert '"budget_min": null' in prompt.user


def test_factory_builds_mock_by_default():
    settings = Settings(_env_file=None, app_env="test", llm_provider="mock")
    provider = build_llm_provider(settings)
    assert isinstance(provider, MockProvider)
    assert provider.name == "mock"


def test_factory_rejects_unknown_provider():
    settings = Settings(_env_file=None, app_env="test", llm_provider="некая-модель")
    with pytest.raises(LLMError):
        build_llm_provider(settings)


def test_factory_maps_openai_compatible_gateway():
    """proxyapi/ollama/deepseek идут через один OpenAI-совместимый адаптер (ТЗ §16)."""
    settings = Settings(_env_file=None, app_env="test", llm_provider="openai", llm_api_key="k")
    provider = build_llm_provider(settings, provider="proxyapi")
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"
