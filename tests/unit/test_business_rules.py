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


# --- Правило бюджета, добавленное после живого прогона 03.11.2026 (DEF-022) ---

PROFILE_WITH_FLOOR = Profile(
    id=3,
    name="С минимумом",
    skills=["Python", "FastAPI", "Docker", "LLM", "REST API"],
    preferences={"min_budget_rub": 50000},
)

N8N_ORDER = Order(
    id=4,
    title="Настроить автоматизацию в n8n: заявки в Google Sheets",
    description=(
        "Хочу, чтобы заявки с сайта попадали в Google Sheets и по ним приходило уведомление "
        "в Telegram. Говорят, это делается за вечер. Бюджет до 20000 рублей."
    ),
    budget_min=20000,
    budget_max=20000,
)


def test_budget_below_profile_minimum_is_skipped():
    """Модель предложила взять заказ за 20 000 ₽, а минимум в профиле — 50 000: решение системы — отказ."""
    decision = _decide(N8N_ORDER, _llm_result(match_score=0.75), PROFILE_WITH_FLOOR)
    assert decision.result.recommendation is Recommendation.SKIP
    assert decision.result.needs_review is False
    assert decision.result.draft_reply is None
    assert decision.result.match_score is None, "оценка соответствия тут не решение: цена ниже минимума"
    assert "budget_below_profile_minimum" in decision.applied_rules
    assert "ниже минимума профиля" in decision.result.reason


def test_budget_at_profile_minimum_is_not_skipped():
    """Ровно на пороге — не отказ: правило строгое «ниже», а не «ниже или равно»."""
    order = Order(
        id=5,
        title="Telegram-бот на Python с LLM",
        description=(
            "Нужен Telegram-бот на Python с интеграцией LLM. Требуется FastAPI, REST API, Docker. "
            "Бюджет 50000-70000 рублей, срок 3 недели."
        ),
        budget_min=50000,
        budget_max=70000,
    )
    decision = _decide(order, _llm_result(), PROFILE_WITH_FLOOR)
    assert decision.result.recommendation is Recommendation.APPLY
    assert "budget_below_profile_minimum" not in decision.applied_rules


def test_profile_without_budget_floor_accepts_cheap_order():
    """Нет min_budget_rub в профиле — правило бюджета не применяется вообще.

    Итог всё равно review: в тестовых настройках расхождение с расчётом по профилю
    (0.75 против 0.00) ловит другое правило — здесь важно только, что бюджетное не сработало.
    """
    decision = _decide(N8N_ORDER, _llm_result(match_score=0.75), PROFILE)
    assert "budget_below_profile_minimum" not in decision.applied_rules
    assert decision.deterministic_score == 0.0


def test_review_with_partial_overlap_stays_review():
    """Хотя бы один навык совпал (Python) — сомнение модели остаётся человеку."""
    accounting = Order(
        id=7,
        title="Автоматизировать сборку отчётов из выгрузок 1С",
        description=(
            "Нужен скрипт на Python: свести 20 выгрузок из 1С в один файл, проверить расхождения. "
            "Бюджет 40000-50000 рублей."
        ),
        budget_min=40000,
        budget_max=50000,
    )
    result = _llm_result(
        match_score=0.5,
        recommendation="review",
        needs_review=True,
        missing_skills=["1С"],
        matched_skills=["Python"],
        draft_reply=None,
        review_reason="У исполнителя нет опыта с 1С",
    )
    decision = _decide(accounting, result, PROFILE)
    assert decision.result.needs_review is True
    assert decision.result.recommendation is Recommendation.REVIEW
    assert "no_skill_overlap_with_profile" not in decision.applied_rules


def test_budget_above_cap_goes_to_review():
    """Бюджет выше разумного предела — вероятная ошибка ввода, решает человек.

    Реальный случай: «от 15 000 до 20 000» на площадке разобрали как 1 500 020 000 ₽.
    Такой заказ нельзя ни откликать, ни отбрасывать автоматически.
    """
    broken = Order(
        id=11,
        title="Нужен парсер и выгрузка в Excel",
        description=(
            "Нужен парсер на Python: ежедневный сбор цен, выгрузка в Excel. "
            "Объём понятен, срок две недели."
        ),
        budget_min=1_500_020_000,
        budget_max=1_500_020_000,
    )
    decision = _decide(broken, _llm_result(), PROFILE_WITH_FLOOR)
    assert decision.result.recommendation is Recommendation.REVIEW
    assert decision.result.needs_review is True
    assert decision.result.match_score is None, "на проверку уходит без выдуманной оценки"
    assert decision.result.draft_reply is None, "и без готового отклика"
    assert "budget_above_review_cap" in decision.applied_rules
    assert "выше предела" in decision.result.review_reason


def test_budget_at_cap_is_not_reviewed():
    """Ровно 500 000 — ещё не повод для проверки: правило строгое «выше»."""
    at_cap = Order(
        id=12,
        title="Telegram-бот на Python с LLM",
        description=(
            "Нужен Telegram-бот на Python с интеграцией LLM. Требуется FastAPI, REST API, Docker. "
            "Бюджет 400000-500000 рублей, срок 3 недели."
        ),
        budget_min=400000,
        budget_max=500000,
    )
    decision = _decide(at_cap, _llm_result(), PROFILE_WITH_FLOOR)
    assert "budget_above_review_cap" not in decision.applied_rules


def test_budget_cap_does_not_override_cheap_skip():
    """Заказ ниже минимума профиля по-прежнему пропуск: правило предела его не перебивает."""
    decision = _decide(N8N_ORDER, _llm_result(), PROFILE_WITH_FLOOR)
    assert decision.result.recommendation is Recommendation.SKIP
    assert "budget_below_profile_minimum" in decision.applied_rules
    assert "budget_above_review_cap" not in decision.applied_rules
