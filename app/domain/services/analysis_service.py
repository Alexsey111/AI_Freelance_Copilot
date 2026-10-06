"""Сервис ИИ-анализа --- центральная часть проекта.

Ключевой архитектурный принцип (ТЗ §15):
    LLM говорит, ЧТО СИСТЕМА СЧИТАЕТ.
    Бизнес-правила этого модуля решают, ЧТО СИСТЕМЕ РАЗРЕШЕНО СДЕЛАТЬ.

Поэтому ни один флаг вида "send_message" из модели не принимается: любое решение
о действии проходит через review, а результат, ушедший на ручную проверку,
гарантированно безопасен (без выдуманного скора и без готового отклика).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.domain.matching import extract_skills, match_order_to_profile
from app.domain.models.analysis import (
    Analysis,
    AnalysisResult,
    Recommendation,
    ReviewStatus,
)
from app.domain.models.audit import AuditStatus
from app.domain.models.order import Order, OrderStatus
from app.domain.services.audit_service import AuditService, AuditTimer
from app.infrastructure.llm.base import (
    PROMPT_VERSION,
    LLMError,
    LLMInvalidResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    truncate_raw,
)

logger = logging.getLogger(__name__)

ACTION_ANALYZE = "analyze_order"


@dataclass(slots=True)
class AnalyzeOutcome:
    """Результат анализа, отданный наружу (API/UI)."""

    analysis: Analysis
    result: AnalysisResult
    order: Order
    duration_ms: int
    provider: str
    model: str
    audit_status: str


class AnalysisService:
    def __init__(
        self,
        order_repository,
        profile_repository,
        analysis_repository,
        audit_service: AuditService,
        llm_provider,
        settings: Settings | None = None,
    ) -> None:
        self.orders = order_repository
        self.profiles = profile_repository
        self.analyses = analysis_repository
        self.audit = audit_service
        self.llm = llm_provider
        self.settings = settings or get_settings()

    # --- Endpoint №3: ИИ-обработка (ТЗ §11) ---
    async def analyze_order(self, order_id: int, profile_id: int | None = None) -> AnalyzeOutcome:
        timer = AuditTimer.start()
        order = self.orders.get(order_id)
        if order is None:
            self.audit.record(
                ACTION_ANALYZE,
                input_payload={"order_id": order_id, "profile_id": profile_id},
                status=AuditStatus.ERROR.value,
                error=f"Заказ #{order_id} не найден",
                duration_ms=timer.duration_ms,
                order_id=order_id,
            )
            raise LookupError(f"Заказ #{order_id} не найден")

        profile = (
            self.profiles.get(profile_id)
            if profile_id is not None
            else self.profiles.get_active()
        )
        if profile is None:
            self.audit.record(
                ACTION_ANALYZE,
                input_payload={"order_id": order_id, "profile_id": profile_id},
                status=AuditStatus.ERROR.value,
                error="Профиль исполнителя не найден",
                duration_ms=timer.duration_ms,
                order_id=order_id,
            )
            raise LookupError("Профиль исполнителя не найден")

        prompt_version = getattr(self.llm, "prompt_version", PROMPT_VERSION)
        audit_input = {
            "order_id": order_id,
            "profile_id": profile.id,
            "provider": getattr(self.llm, "name", "unknown"),
            "model": getattr(self.llm, "model", "unknown"),
            "prompt_version": prompt_version,
        }

        # Заказ ушёл в обработку (жизненный цикл ТЗ §28).
        self.orders.update_status(order_id, OrderStatus.ANALYZING.value)

        try:
            llm_result = await self.llm.analyze_order(order, profile)
        except LLMError as exc:
            return self._handle_llm_error(order, profile, exc, timer, audit_input, prompt_version)

        # Слой бизнес-правил поверх мнения модели (ТЗ §15).
        decision = self._apply_business_rules(order, profile, llm_result)
        analysis = self._persist(
            order=order,
            profile_id=profile.id,
            result=decision.result,
            raw_output=self._raw_output(),
            prompt_version=prompt_version,
            error=decision.error,
        )
        order_after = self._update_order_status(order, decision.result)

        status = (
            AuditStatus.REVIEW.value
            if decision.result.needs_review
            else AuditStatus.SUCCESS.value
        )
        self.audit.record(
            ACTION_ANALYZE,
            input_payload=audit_input,
            output_payload={
                "analysis_id": analysis.id,
                "match_score": decision.result.match_score,
                "recommendation": decision.result.recommendation.value,
                "needs_review": decision.result.needs_review,
                "review_reason": decision.result.review_reason,
                "business_rules_applied": decision.applied_rules,
                "deterministic_score": decision.deterministic_score,
            },
            status=status,
            duration_ms=timer.duration_ms,
            order_id=order_id,
        )
        return AnalyzeOutcome(
            analysis=analysis,
            result=decision.result,
            order=order_after,
            duration_ms=timer.duration_ms,
            provider=getattr(self.llm, "name", "unknown"),
            model=getattr(self.llm, "model", "unknown"),
            audit_status=status,
        )

    # ------------------------------------------------------------------ #
    # Бизнес-правила (решение системы, а не модели)
    # ------------------------------------------------------------------ #
    @dataclass(slots=True)
    class _Decision:
        result: AnalysisResult
        applied_rules: list[str]
        deterministic_score: float | None = None
        error: str | None = None

    def _apply_business_rules(self, order: Order, profile, llm_result: AnalysisResult) -> _Decision:
        applied: list[str] = []
        order_skills = extract_skills(order.full_text)
        deterministic = match_order_to_profile(order_skills, profile.normalized_skills)

        # Правило 1 (ТЗ §13, §14.1): не хватает критически важных данных.
        missing = order.missing_data(self.settings.min_description_chars)
        if missing:
            applied.append("missing_critical_data")
            return self._Decision(
                result=AnalysisResult.review_fallback(
                    "; ".join(missing), "Недостаточно данных для надёжной оценки"
                ),
                applied_rules=applied,
                deterministic_score=deterministic.score,
            )

        # Правило 2 (ТЗ §14.3): соответствие профилю определить не удалось.
        if not deterministic.is_determined:
            applied.append("matching_undetermined")
            return self._Decision(
                result=AnalysisResult(
                    match_score=None,
                    recommendation=Recommendation.REVIEW,
                    reason=deterministic.reason or "Не удалось определить соответствие профилю",
                    matched_skills=deterministic.matched_skills,
                    missing_skills=deterministic.missing_skills,
                    draft_reply=None,
                    needs_review=True,
                    review_reason="Не удалось определить соответствие профилю исполнителя",
                ),
                applied_rules=applied,
                deterministic_score=None,
            )

        result = llm_result
        applied.append("llm_result_accepted")

        # Правило 3: модель сама попросила проверку --- сохраняем её решение.
        if result.needs_review:
            applied.append("llm_requested_review")
            return self._Decision(
                result=result, applied_rules=applied, deterministic_score=deterministic.score
            )

        # Правило 4: рекомендация apply требует готового безопасного отклика (ТЗ §14.4).
        if result.recommendation is Recommendation.APPLY:
            draft = (result.draft_reply or "").strip()
            if len(draft) < self.settings.min_draft_reply_chars:
                applied.append("draft_reply_missing_or_too_short")
                return self._Decision(
                    result=AnalysisResult(
                        match_score=result.match_score,
                        recommendation=Recommendation.REVIEW,
                        reason=result.reason,
                        matched_skills=result.matched_skills,
                        missing_skills=result.missing_skills,
                        draft_reply=None,
                        needs_review=True,
                        review_reason=(
                            "Недостаточно информации для безопасной генерации отклика "
                            "(черновик пуст или слишком короткий)"
                        ),
                    ),
                    applied_rules=applied,
                    deterministic_score=deterministic.score,
                )

        # Правило 5: уверенность ниже порога доверия.
        # Исключение: если независимый расчёт по профилю тоже ниже порога и модель
        # рекомендует пропустить --- это уверенный отказ ("не наш заказ"), а не сомнение.
        confidently_irrelevant = (
            deterministic.score is not None
            and deterministic.score < self.settings.match_score_review_threshold
            and result.recommendation is Recommendation.SKIP
        )
        if (
            result.match_score is not None
            and result.match_score < self.settings.match_score_review_threshold
            and not confidently_irrelevant
        ):
            applied.append("score_below_review_threshold")
            return self._Decision(
                result=AnalysisResult(
                    match_score=result.match_score,
                    recommendation=Recommendation.REVIEW,
                    reason=result.reason,
                    matched_skills=result.matched_skills,
                    missing_skills=result.missing_skills,
                    draft_reply=None,
                    needs_review=True,
                    review_reason=(
                        "Низкая уверенность модели (score "
                        f"{result.match_score:.2f} < {self.settings.match_score_review_threshold:.2f})"
                    ),
                ),
                applied_rules=applied,
                deterministic_score=deterministic.score,
            )

        # Правило 6: расхождение мнения модели и детерминированного расчёта.
        if result.match_score is not None:
            delta = abs(result.match_score - deterministic.score)
            if delta > self.settings.llm_score_crosscheck_delta:
                applied.append("score_mismatch_with_deterministic_matching")
                return self._Decision(
                    result=AnalysisResult(
                        match_score=None,
                        recommendation=Recommendation.REVIEW,
                        reason=result.reason,
                        matched_skills=result.matched_skills,
                        missing_skills=result.missing_skills,
                        draft_reply=None,
                        needs_review=True,
                        review_reason=(
                            "Оценка модели расходится с расчётом по профилю "
                            f"({result.match_score:.2f} против {deterministic.score:.2f})"
                        ),
                    ),
                    applied_rules=applied,
                    deterministic_score=deterministic.score,
                )

        return self._Decision(
            result=result, applied_rules=applied, deterministic_score=deterministic.score
        )

    # ------------------------------------------------------------------ #
    # Ошибки LLM (ТЗ §14.2, §14.5, §29.3)
    # ------------------------------------------------------------------ #
    def _handle_llm_error(
        self, order: Order, profile, exc: LLMError, timer, audit_input: dict, prompt_version: str
    ) -> AnalyzeOutcome:
        if isinstance(exc, (LLMUnavailableError, LLMTimeoutError)):
            # Инфраструктурная ошибка: заказ уходит в ERROR, но человек об этом узнаёт.
            reason = (
                f"Ошибка LLM: {exc}" if not isinstance(exc, LLMTimeoutError)
                else f"LLM timeout: {exc}"
            )
            status = AuditStatus.ERROR.value
            order_status = OrderStatus.ERROR.value
        elif isinstance(exc, LLMInvalidResponseError):
            # Модель ответила, но мусором: результат невалиден, отдаём человеку (ТЗ §29.3).
            reason = f"Модель вернула невалидный JSON: {exc}"
            status = AuditStatus.REVIEW.value
            order_status = OrderStatus.NEEDS_REVIEW.value
        else:
            reason = f"Ошибка LLM: {exc}"
            status = AuditStatus.ERROR.value
            order_status = OrderStatus.ERROR.value

        result = AnalysisResult.review_fallback(reason, "Результат ИИ недоступен")
        analysis = self._persist(
            order=order,
            profile_id=profile.id,
            result=result,
            raw_output=self._raw_output(),
            prompt_version=prompt_version,
            error=str(exc),
        )
        order_after = self.orders.update_status(order.id, order_status, needs_review=True) or order
        self.audit.record(
            ACTION_ANALYZE,
            input_payload=audit_input,
            output_payload={
                "analysis_id": analysis.id,
                "needs_review": True,
                "review_reason": reason,
            },
            status=status,
            error=str(exc),
            duration_ms=timer.duration_ms,
            order_id=order.id,
        )
        logger.warning("analyze_order #%s упал: %s", order.id, exc)
        return AnalyzeOutcome(
            analysis=analysis,
            result=result,
            order=order_after,
            duration_ms=timer.duration_ms,
            provider=getattr(self.llm, "name", "unknown"),
            model=getattr(self.llm, "model", "unknown"),
            audit_status=status,
        )

    # ------------------------------------------------------------------ #
    # Внутреннее
    # ------------------------------------------------------------------ #
    def _raw_output(self) -> str | None:
        raw = getattr(self.llm, "last_raw_output", None)
        if raw is None:
            return None
        return truncate_raw(raw)

    def _persist(
        self,
        *,
        order: Order,
        profile_id: int,
        result: AnalysisResult,
        raw_output: str | None,
        prompt_version: str,
        error: str | None = None,
    ) -> Analysis:
        return self.analyses.add(
            Analysis(
                order_id=order.id,
                profile_id=profile_id,
                match_score=result.match_score,
                recommendation=result.recommendation.value,
                reason=result.reason,
                matched_skills=result.matched_skills,
                missing_skills=result.missing_skills,
                draft_reply=result.draft_reply,
                needs_review=result.needs_review,
                review_reason=result.review_reason,
                review_status=(
                    ReviewStatus.PENDING.value if result.needs_review else None
                ),
                raw_output=raw_output,
                model=getattr(self.llm, "model", None),
                prompt_version=prompt_version,
                error=error,
            )
        )

    def _update_order_status(self, order: Order, result: AnalysisResult) -> Order:
        if result.needs_review:
            status = OrderStatus.NEEDS_REVIEW.value
        elif result.recommendation is Recommendation.APPLY or result.recommendation is Recommendation.SKIP:
            status = OrderStatus.ANALYZED.value
        else:
            status = OrderStatus.NEEDS_REVIEW.value
        return (
            self.orders.update_status(order.id, status, needs_review=result.needs_review) or order
        )


def audit_input_json(order_id: int, profile_id: int | None, prompt_version: str) -> str:
    """Утилита для тестов/логов: как выглядит вход аудита."""
    return json.dumps(
        {"order_id": order_id, "profile_id": profile_id, "prompt_version": prompt_version},
        ensure_ascii=False,
    )
