"""Сборка LLM-провайдера по конфигурации (ТЗ §16)."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.infrastructure.llm.base import LLMError
from app.infrastructure.llm.mock_adapter import MockProvider
from app.infrastructure.llm.openai_adapter import OpenAIProvider


def build_llm_provider(
    settings: Settings | None = None, *, provider: str | None = None, **overrides
) -> object:
    """Вернуть LLM-провайдер согласно LLM_PROVIDER.

    Поддерживается: mock | openai (любой OpenAI-совместимый endpoint через LLM_BASE_URL).
    Остальные имена (ollama, deepseek, proxyapi) маппятся на openai-совместимый адаптер.
    """
    settings = settings or get_settings()
    name = (provider or settings.llm_provider or "mock").strip().lower()
    rules = {
        "min_description_chars": settings.min_description_chars,
        "match_score_review_threshold": settings.match_score_review_threshold,
    }
    if name in {"mock", "test", "fake"}:
        return MockProvider(
            model="mock-model",
            delay_s=overrides.pop("delay_s", 0.0),
            min_description_chars=settings.min_description_chars,
        )
    if name in {"openai", "ollama", "deepseek", "proxyapi", "custom", "openai_compatible"}:
        return OpenAIProvider(
            model=overrides.pop("model", settings.llm_model),
            api_key=overrides.pop("api_key", settings.llm_api_key),
            base_url=overrides.pop("base_url", settings.llm_base_url),
            timeout_s=overrides.pop("timeout_s", settings.llm_timeout_s),
            temperature=overrides.pop("temperature", settings.llm_temperature),
            max_output_tokens=overrides.pop(
                "max_output_tokens", settings.llm_max_output_tokens
            ),
            rules=rules,
        )
    raise LLMError(f"Неизвестный LLM_PROVIDER: {name!r} (доступны: mock, openai)")
