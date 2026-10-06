"""Unit: бизнес-правила поверх ответа LLM (ТЗ §13, §14, §15, §29).

Проверяется ключевой архитектурный принцип: решение принимает система, а не модель.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.models.analysis import AnalysisResult, Recommendation
from app.domain.models.order import Order
from app.domain.models.profile import Profile
from app.domain.services.analysis_service import AnalysisService

SETTINGS = Settings(
    _env_file=None,
    app_env="test",
    min_description_chars=40,
    match_score_review_threshold=0.35,
    llm_score_crosscheck_delta=0.05,
    min_draft_reply_chars=80,
)

PROFILE = Profile(id=1, name="Тест", skills=["Python", "FastAPI", "Docker", "LLM", "REST API"])
GOOD_ORDER = Order(
    id=1,
    title="Telegram-бот на Python с LLM",
    description=(
        "Нужен Telegram-бот на Python с интеграцией LLM. Требуется FastAPI, REST API, Docker. "
        "Бюджет указан, срок 3 недели, объём работ понятен."
    ),
    budget_min=30000,
    budget_max=50000,
)

LONG_DRAFT = "Здравствуйте! " + "Опыт в Python и LLM подтверждён. " * 5


def _service(llm) -> AnalysisService:
    return AnalysisService(
        order_repository=None,
        profile_repository=None,
        analysis_repository=None,
        audit_service=None,
        llm_provider=llm,
        settings=SETTINGS,
    )


def _llm_result(**overrides) -> AnalysisResult:
    payload = {
        "match_score": 0.8,
        "recommendation": "apply",
        "reason": "подходит",
        "matched_skills": ["Python", "LLM"],
        "missing_skills": [],
        "draft_reply": LONG_DRAFT,
        "needs_review": False,
        "review_reason": None,
    }
    payload.update(overrides)
    return AnalysisResult.model_validate(payload)


def _decide(order: Order, result: AnalysisResult, profile: Profile = PROFILE):
    """Правила применяются без БД: сервису нужен только метод _apply_business_rules."""
    return AnalysisService._apply_business_rules(_service(None), order, profile, result)


def test_missing_critical_data_goes_to_review():
    vague = Order(id=2, title="Нужен разработчик Python", description="Подробности лично.")
    decision = _decide(vague, _llm_result())
    assert decision.result.needs_review is True
    assert decision.result.match_score is None
    assert decision.result.draft_reply is None
    assert "не указан бюджет" in decision.result.review_reason
    assert "missing_critical_data" in decision.applied_rules


def test_llm_apply_without_draft_is_downgraded():
    decision = _decide(GOOD_ORDER, _llm_result(draft_reply=None))
    assert decision.result.needs_review is True
    assert decision.result.recommendation is Recommendation.REVIEW
    assert "черновик" in decision.result.review_reason.lower()


def test_score_mismatch_with_deterministic_matching_goes_to_review():
    """Модель завышает оценку относительно расчёта по профилю --- это повод для человека.

    Порог расхождения берём 0.05: заявленные 0.99 против расчётных 0.83 --- это больше.
    """
    decision = _decide(GOOD_ORDER, _llm_result(match_score=0.99, matched_skills=["Python"]))
    assert decision.result.needs_review is True
    assert "расходится" in decision.result.review_reason
    assert "score_mismatch_with_deterministic_matching" in decision.applied_rules


def test_low_confidence_goes_to_review():
    decision = _decide(GOOD_ORDER, _llm_result(match_score=0.1, recommendation="skip", draft_reply=None))
    assert decision.result.needs_review is True
    assert "score_below_review_threshold" in decision.applied_rules


def test_confident_skip_stays_skip():
    """Явно неподходящий заказ: расчёт по профилю тоже низкий --- человека не дёргаем."""
    irrelevant_order = Order(
        id=3,
        title="Вёрстка лендинга на Tilda",
        description=(
            "Требуется свёрстанный лендинг на Tilda с адаптивом, дизайн готов в Figma. "
            "Опыт вёрстки обязателен, бюджет 25000 рублей."
        ),
        budget_min=25000,
    )
    decision = _decide(
        irrelevant_order,
        _llm_result(match_score=0.0, recommendation="skip", draft_reply=None),
    )
    assert decision.result.needs_review is False
    assert decision.result.recommendation is Recommendation.SKIP
    assert decision.deterministic_score == 0.0


def test_llm_requested_review_is_kept():
    result = _llm_result(
        match_score=0.5,
        recommendation="review",
        needs_review=True,
        draft_reply=None,
        review_reason="Модель не уверена",
    )
    decision = _decide(GOOD_ORDER, result)
    assert decision.result.needs_review is True
    assert decision.result.review_reason == "Модель не уверена"
    assert "llm_requested_review" in decision.applied_rules


def test_undetermined_matching_goes_to_review():
    profile_without_skills = Profile(id=2, name="Пустой", skills=[])
    decision = _decide(GOOD_ORDER, _llm_result(), profile_without_skills)
    assert decision.result.needs_review is True
    assert "matching_undetermined" in decision.applied_rules


def test_good_case_passes_through_unchanged():
    decision = _decide(GOOD_ORDER, _llm_result())
    assert decision.result.needs_review is False
    assert decision.result.recommendation is Recommendation.APPLY
    assert decision.deterministic_score is not None
    assert decision.applied_rules == ["llm_result_accepted"]
