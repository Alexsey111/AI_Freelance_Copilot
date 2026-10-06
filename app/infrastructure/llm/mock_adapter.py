"""Детерминированный офлайн-провайдер (ТЗ §17).

Нужен, чтобы тесты и демонстрация не зависели от API и денег. Никаких сетевых вызовов.
Поведение воспроизводит все ветки ТЗ §14: нехватка данных, низкое соответствие,
невалидный JSON, таймаут.
"""

from __future__ import annotations

import asyncio
import json

from app.domain.matching import match_order_to_profile
from app.domain.models.analysis import AnalysisResult, Recommendation
from app.domain.models.order import Order
from app.domain.models.profile import Profile
from app.infrastructure.llm.base import (
    PROMPT_VERSION,
    LLMInvalidResponseError,
    LLMTimeoutError,
)

# Ключевые слова, включающие сценарии в mock-провайдере (только для тестов и демонстрации).
# Каждый триггер соответствует одному из случаев ТЗ §14, чтобы правило проверялось сквозь API,
# а не только юнит-тестом на внутреннем методе.
TRIGGER_BAD_JSON = "MOCK_BAD_JSON"            # §14.2 невалидный ответ модели
TRIGGER_TIMEOUT = "MOCK_TIMEOUT"              # §14.5 ошибка LLM
TRIGGER_LOW_MATCH = "MOCK_LOW_MATCH"          # низкая уверенность при хорошем расчёте по профилю
TRIGGER_LOW_CONFIDENCE = "MOCK_LOW_CONFIDENCE"  # модель сама просит проверку
TRIGGER_INFLATED = "MOCK_INFLATED"            # завышенная оценка: расхождение с расчётом по профилю
TRIGGER_NO_DRAFT = "MOCK_NO_DRAFT"            # apply без черновика отклика


class MockProvider:
    """MockProvider из ТЗ §17: заранее известный, детерминированный результат."""

    name = "mock"

    def __init__(
        self,
        model: str = "mock-model",
        *,
        delay_s: float = 0.0,
        min_description_chars: int = 40,
    ) -> None:
        self.model = model
        self.delay_s = delay_s
        self.min_description_chars = min_description_chars
        self.calls: list[dict] = []

    async def analyze_order(self, order: Order, profile: Profile) -> AnalysisResult:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        self.calls.append({"order_id": order.id, "profile_id": profile.id})
        text = order.full_text.upper()

        if TRIGGER_TIMEOUT in text:
            raise LLMTimeoutError("LLM timeout (mock)")
        if TRIGGER_BAD_JSON in text:
            raise LLMInvalidResponseError('Mock: модель вернула "не json" вместо JSON')

        missing = order.missing_data(self.min_description_chars)
        if missing:
            return AnalysisResult(
                match_score=None,
                recommendation=Recommendation.REVIEW,
                reason="Недостаточно данных для надёжной оценки",
                matched_skills=[],
                missing_skills=[],
                draft_reply=None,
                needs_review=True,
                review_reason="; ".join(missing),
            )

        outcome = match_order_to_profile(_order_skills(order), profile.normalized_skills)
        score = outcome.score
        if TRIGGER_LOW_MATCH in text and score is not None:
            score = min(score, 0.1)
        if score is None:
            return AnalysisResult(
                match_score=None,
                recommendation=Recommendation.REVIEW,
                reason=outcome.reason or "Не удалось определить соответствие профилю",
                matched_skills=outcome.matched_skills,
                missing_skills=outcome.missing_skills,
                draft_reply=None,
                needs_review=True,
                review_reason="Не удалось определить соответствие профилю исполнителя",
            )

        if TRIGGER_LOW_CONFIDENCE in text:
            score = 0.5
            return AnalysisResult(
                match_score=score,
                recommendation=Recommendation.REVIEW,
                reason="Mock: модель не уверена в оценке соответствия",
                matched_skills=outcome.matched_skills,
                missing_skills=outcome.missing_skills,
                draft_reply=None,
                needs_review=True,
                review_reason="Низкая уверенность модели --- требуется проверка человеком",
            )

        # §14.4: модель рекомендует отклик, но черновик не сформирован --- бизнес-логика
        # обязана понизить решение до ручной проверки.
        if TRIGGER_NO_DRAFT in text:
            return AnalysisResult(
                match_score=score,
                recommendation=Recommendation.APPLY,
                reason="Mock: заказ подходит профилю",
                matched_skills=outcome.matched_skills,
                missing_skills=outcome.missing_skills,
                draft_reply=None,
                needs_review=False,
                review_reason=None,
            )

        # §14.3/§14.6: модель завышает оценку относительно расчёта по профилю.
        if TRIGGER_INFLATED in text:
            return AnalysisResult(
                match_score=0.99,
                recommendation=Recommendation.APPLY,
                reason="Mock: заказ отлично подходит профилю",
                matched_skills=outcome.matched_skills,
                missing_skills=outcome.missing_skills,
                draft_reply=_draft_reply(order, profile, outcome.matched_skills or ["Python"]),
                needs_review=False,
                review_reason=None,
            )

        recommendation = (
            Recommendation.APPLY if score >= 0.5 else Recommendation.SKIP
        )
        draft = None
        if recommendation is Recommendation.APPLY:
            draft = _draft_reply(order, profile, outcome.matched_skills)
        return AnalysisResult(
            match_score=score,
            recommendation=recommendation,
            reason=outcome.reason,
            matched_skills=outcome.matched_skills,
            missing_skills=outcome.missing_skills,
            draft_reply=draft,
            needs_review=False,
            review_reason=None,
        )

    # Вспомогательное: mock умеет отдавать свой "сырой" ответ так же, как реальный провайдер.
    def raw_of(self, result: AnalysisResult) -> str:
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION


def _order_skills(order: Order) -> list[str]:
    from app.domain.matching import extract_skills

    return extract_skills(order.full_text)


def _draft_reply(order: Order, profile: Profile, matched: list[str]) -> str:
    skills = ", ".join(matched) if matched else "Python"
    return (
        f"Здравствуйте!\n\n"
        f"Меня заинтересовал ваш заказ «{order.title}». "
        f"По профилю у меня есть опыт в: {skills}. "
        f"{profile.summary}\n\n"
        f"По вашей задаче могу предложить следующий план: уточнить требования, "
        f"собрать прототип ключевой части, показать результат и затем довести до "
        f"полной реализации с тестами и документацией.\n\n"
        f"Готов начать в ближайшее время и держать вас в курсе на каждом этапе. "
        f"Подскажите, пожалуйста, удобный формат связи и есть ли уже наработки по проекту?\n\n"
        f"С уважением,\n{profile.name}"
    )
