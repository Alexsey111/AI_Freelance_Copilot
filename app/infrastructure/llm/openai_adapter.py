"""OpenAI-совместимый провайдер (ТЗ §16).

Специально сделан OpenAI-СОВМЕСТИМЫМ (параметр base_url), чтобы без правки бизнес-логики
работать с любым шлюзом: OpenAI, proxyapi.ru, DeepSeek, локальная ollama (/v1).
Ключ читается только из окружения/.env и никогда не логируется.
"""

from __future__ import annotations

import asyncio

from app.domain.models.analysis import AnalysisResult
from app.domain.models.order import Order
from app.domain.models.profile import Profile
from app.infrastructure.llm.base import (
    PROMPT_VERSION,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    build_order_prompt,
    parse_analysis_result,
    truncate_raw,
)


class OpenAIProvider:
    """Провайдер поверх openai.AsyncOpenAI (chat.completions)."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None = None,
        timeout_s: float = 60.0,
        temperature: float = 0.0,
        max_output_tokens: int = 1500,
        client=None,
        rules: dict | None = None,
    ) -> None:
        if client is None and not api_key:
            raise LLMUnavailableError(
                "Не задан LLM_API_KEY: укажите ключ в .env или используйте LLM_PROVIDER=mock"
            )
        self.model = model
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.rules = rules or {}
        self.prompt_version = PROMPT_VERSION
        self.last_raw_output: str | None = None
        if client is not None:
            self._client = client
        else:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0
            )

    async def analyze_order(self, order: Order, profile: Profile) -> AnalysisResult:
        prompt = build_order_prompt(order, profile, rules=self.rules)
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": prompt.system},
                        {"role": "user", "content": prompt.user},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_output_tokens,
                    response_format={"type": "json_object"},
                ),
                timeout=self.timeout_s,
            )
        except TimeoutError as exc:
            raise LLMTimeoutError(f"LLM timeout после {self.timeout_s:g} c") from exc
        except Exception as exc:  # сеть/401/429/5xx и т.п.
            raise LLMUnavailableError(f"Провайдер LLM недоступен: {type(exc).__name__}: {exc}") from exc

        raw = (response.choices[0].message.content or "") if response.choices else ""
        self.last_raw_output = truncate_raw(raw)
        if not raw.strip():
            raise LLMError("Провайдер вернул пустой ответ")
        return parse_analysis_result(raw)
