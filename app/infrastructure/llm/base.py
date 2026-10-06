"""Абстракция LLM (ТЗ §16) и разбор её ответа.

Контракт принципиальный: провайдер возвращает либо валидный AnalysisResult,
либо поднимает LLMError. Произвольный текст наружу не выходит --- невалидный
JSON превращается в ошибку и уходит в ручную проверку (ТЗ §29.3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from app.config import PROMPTS_DIR
from app.domain.models.analysis import AnalysisResult
from app.domain.models.order import Order
from app.domain.models.profile import Profile

PROMPT_VERSION = "v1.0"
PROMPT_FILE = "order_analysis.txt"

# Сколько первых/последних символов "сырого" ответа модели хранить в audit/analyses.
RAW_OUTPUT_LIMIT = 20000


class LLMError(RuntimeError):
    """Базовая ошибка LLM-слоя. Любая такая ошибка -> ручная проверка (ТЗ §14.5)."""


class LLMUnavailableError(LLMError):
    """Провайдер не сконфигурирован/недоступен (нет ключа, сеть, 401/403/5xx)."""


class LLMTimeoutError(LLMError):
    """Провайдер не ответил в отведённое время (ТЗ §8, пример error="LLM timeout")."""


class LLMInvalidResponseError(LLMError):
    """Модель вернула невалидный JSON или JSON, не соответствующий схеме (ТЗ §29.3)."""


@runtime_checkable
class LLMProvider(Protocol):
    """Интерфейс провайдера (ТЗ §16)."""

    name: str
    model: str

    async def analyze_order(self, order: Order, profile: Profile) -> AnalysisResult:
        """Проанализировать заказ относительно профиля исполнителя."""
        ...


@dataclass(slots=True)
class OrderAnalysisPrompt:
    """Готовый промпт: системная часть + пользовательская часть + версия."""

    system: str
    user: str
    version: str = PROMPT_VERSION


def load_prompt_template(prompts_dir: Path | None = None) -> str:
    """Прочитать шаблон промпта из prompts/order_analysis.txt."""
    directory = prompts_dir or PROMPTS_DIR
    path = directory / PROMPT_FILE
    if not path.exists():  # pragma: no cover - защита от битой поставки
        raise LLMError(f"Не найден файл промпта: {path}")
    return path.read_text(encoding="utf-8")


def build_order_prompt(
    order: Order,
    profile: Profile,
    *,
    rules: dict | None = None,
    prompts_dir: Path | None = None,
) -> OrderAnalysisPrompt:
    """Собрать промпт: шаблон + факты о заказе и профиле (без додумывания данных)."""
    template = load_prompt_template(prompts_dir)
    facts = {
        "order": {
            "id": order.id,
            "title": order.title,
            "description": order.description,
            "budget_min": order.budget_min,
            "budget_max": order.budget_max,
            "currency": order.currency,
            "client_name": order.client_name,
            "url": order.url,
            "source": order.source,
            "missing_data": order.missing_data(
                (rules or {}).get("min_description_chars", 40)
            ),
        },
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "summary": profile.summary,
            "skills": profile.normalized_skills,
            "experience": profile.experience,
            "preferences": profile.preferences,
        },
    }
    user = (
        template.replace("{{ORDER_JSON}}", json.dumps(facts["order"], ensure_ascii=False, indent=2))
        .replace("{{PROFILE_JSON}}", json.dumps(facts["profile"], ensure_ascii=False, indent=2))
        .replace("{{RULES_JSON}}", json.dumps(rules or {}, ensure_ascii=False, indent=2))
    )
    system = (
        "Ты --- модуль анализа фриланс-заказов в системе AI Freelance Copilot. "
        "Ты отвечаешь единственным JSON-объектом по заданной схеме, без пояснений и markdown."
    )
    return OrderAnalysisPrompt(system=system, user=user)


def extract_json_object(raw: str) -> dict:
    """Достать JSON-объект из ответа модели.

    Модель может обернуть JSON в ```json ... ``` или добавить текст вокруг ---
    это допустимо, а вот отсутствие объекта --- уже ошибка.
    """
    if raw is None or not raw.strip():
        raise LLMInvalidResponseError("Модель вернула пустой ответ")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMInvalidResponseError(
                "В ответе модели не найден JSON-объект"
            ) from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(f"Невалидный JSON от модели: {exc}") from exc
    if not isinstance(payload, dict):
        raise LLMInvalidResponseError("Модель вернула JSON не-объект")
    return payload


def parse_analysis_result(raw: str) -> AnalysisResult:
    """Превратить сырой ответ модели в строгий AnalysisResult (ТЗ §12)."""
    payload = extract_json_object(raw)
    try:
        return AnalysisResult.model_validate(payload)
    except ValidationError as exc:
        raise LLMInvalidResponseError(
            f"Ответ модели не соответствует схеме AnalysisResult: {exc.error_count()} ошибок"
        ) from exc


def truncate_raw(raw: str | None, limit: int = RAW_OUTPUT_LIMIT) -> str | None:
    """Ограничить размер "сырого" ответа, сохраняемого в БД."""
    if raw is None:
        return None
    return raw if len(raw) <= limit else raw[:limit] + "\n...[обрезано]"
