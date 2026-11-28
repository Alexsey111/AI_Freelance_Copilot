"""Unit: домен входящих заявок в том же движке.

Проверяется, что второй домен не требует второго приложения:
профиль компании выбирает промпт, лексикон товаров и правило «бюджет не обязателен»,
а схема ответа и правила ядра остаются прежними.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.intake import detect_region, parse_deferment_days
from app.domain.models.analysis import AnalysisResult, Recommendation
from app.domain.models.order import Order
from app.domain.models.profile import Profile
from app.domain.services.analysis_service import AnalysisService
from app.infrastructure.llm.base import build_order_prompt, prompt_for_domain

SETTINGS = Settings(
    _env_file=None,
    app_env="test",
    min_description_chars=40,
    match_score_review_threshold=0.35,
    llm_score_crosscheck_delta=0.05,
    min_draft_reply_chars=80,
    budget_review_cap_rub=500_000,
)

LEXICON = {
    "Арматура": ["арматур", "а500", "а500с"],
    "Профнастил": ["профнастил", "с8"],
}

COMPANY = Profile(
    id=10,
    name="ООО «СибМеталл-Снаб»",
    summary="Опт металлопроката, регионы Сибири, минимум 50 000 ₽",
    skills=["Арматура", "Профнастил"],
    preferences={
        "domain": "intake",
        "min_budget_rub": 50000,
        "require_budget": False,
        "max_deferment_days": 30,
        "large_order_review_rub": 500000,
        "regions": ["Барнаул", "Новосибирск", "Томск", "Кемерово", "Красноярск"],
        "out_of_area": ["Казахстан", "Астана", "Москва"],
        "skill_lexicon": LEXICON,
    },
)

LONG_DRAFT = "Здравствуйте! Заявку получили. " + "Уточните, пожалуйста, объём и срок. " * 4

REQUEST = Order(
    id=1,
    external_id="biz-001",
    title="Арматура А500С Ø12 — 5 тонн",
    description=(
        "Нужна арматура А500С диаметр 12, 5 тонн, доставка в Барнаул на объект. "
        "Оплата по счёту, отсрочка 14 дней. Бюджет до 280 000 рублей."
    ),
    budget_min=250000,
    budget_max=280000,
    client_name="ООО «Стройбаза-Алтай»",
)


def _service() -> AnalysisService:
    return AnalysisService(
        order_repository=None,
        profile_repository=None,
        analysis_repository=None,
        audit_service=None,
        llm_provider=None,
        settings=SETTINGS,
    )


def _llm_result(**overrides) -> AnalysisResult:
    payload = {
        "match_score": 1.0,
        "recommendation": "apply",
        "reason": "арматура в наличии по профилю, регион и объём подходят",
        "matched_skills": ["Арматура"],
        "missing_skills": [],
        "draft_reply": LONG_DRAFT,
        "needs_review": False,
        "review_reason": None,
    }
    payload.update(overrides)
    return AnalysisResult.model_validate(payload)


def test_intake_domain_has_own_prompt_file():
    filename, version, system = prompt_for_domain("intake")
    assert filename == "request_triage.txt"
    assert version == "v1.0-intake"
    assert "заявок" in system


def test_unknown_domain_falls_back_to_freelance():
    assert prompt_for_domain(None)[0] == "order_analysis.txt"
    assert prompt_for_domain("нет-такого")[0] == "order_analysis.txt"


def test_company_profile_builds_intake_prompt():
    prompt = build_order_prompt(REQUEST, COMPANY)
    assert "ДАННЫЕ О ЗАЯВКЕ" in prompt.user
    assert "профиль компании" in prompt.user.lower()
    assert prompt.version == "v1.0-intake"
    assert "фриланс" not in prompt.system.lower()


def test_budget_is_not_required_for_intake_domain():
    """В опте сумму называют не в первом письме: это не повод останавливать разбор."""
    no_budget = Order(
        id=2,
        title="Профнастил С8 — 200 м²",
        description="Нужен профнастил С8, 200 квадратных метров, объект в Барнауле, срок до конца месяца.",
    )
    assert no_budget.missing_data(40) != []
    assert no_budget.missing_data(40, require_budget=False) == []


def test_intake_rule_set_uses_company_lexicon():
    """Лексикон товаров берётся из профиля: арматура сопоставляется, а не «не определено»."""
    decision = AnalysisService._apply_business_rules(_service(), REQUEST, COMPANY, _llm_result())
    assert decision.deterministic_score == 1.0
    assert decision.result.recommendation is Recommendation.APPLY
    assert decision.result.draft_reply


def test_intake_order_below_minimum_is_skipped_before_model():
    """Минимум заказа в профиле — правило ядра, а не просьба к модели."""
    small = Order(
        id=3,
        title="Уголок 50×50×5 — 500 кг",
        description="Нужен уголок 50х50х5, 500 килограмм, самовывоз в Барнауле. Бюджет 32 000 рублей.",
        budget_min=30000,
        budget_max=32000,
    )
    decision = AnalysisService._apply_business_rules(_service(), small, COMPANY, _llm_result())
    assert decision.result.recommendation is Recommendation.SKIP
    assert "budget_below_profile_minimum" in decision.applied_rules
    assert decision.result.draft_reply is None


def test_intake_without_lexicon_is_honestly_undetermined():
    """Профиль компании без лексикона не получает IT-навыки и уходит человеку, а не «применяется»."""
    без_лексикона = Profile(
        id=11,
        name="Компания без лексикона",
        skills=["Арматура"],
        preferences={"domain": "intake", "require_budget": False},
    )
    decision = AnalysisService._apply_business_rules(
        _service(), REQUEST, без_лексикона, _llm_result()
    )
    assert decision.result.recommendation is Recommendation.REVIEW
    assert "matching_undetermined" in decision.applied_rules
    assert decision.result.match_score is None


# --- Факты заявки считает система, а не модель (живой прогон 28.11.2026) ---


def test_deferment_days_are_parsed():
    assert parse_deferment_days("Просим отсрочку платежа 60 дней") == 60
    assert parse_deferment_days("отсрочка 21 день") == 21
    assert parse_deferment_days("оплата по счёту, отсрочка 14 дн.") == 14
    assert parse_deferment_days("60 дней отсрочки") == 60
    assert parse_deferment_days("оплата сразу, по счёту") is None


def test_region_detection_prefers_own_region():
    assert (
        detect_region(
            "Объект в Барнауле, юрлицо в Москве", regions=["Барнаул"], out_of_area=["Москва"]
        )[0]
        == "served"
    )
    assert (
        detect_region(
            "Доставка в Астану, Казахстан", regions=["Барнаул"], out_of_area=["Астана"]
        )[0]
        == "outside"
    )
    assert detect_region("Доставка на объект", regions=["Барнаул"])[0] == "unknown"


def _арматура(description_suffix: str, total: float, city: str = "Томск") -> Order:
    return Order(
        id=21,
        title="Арматура А500С Ø12",
        description=(
            f"Нужна арматура А500С 12, {description_suffix}, доставка в {city}. "
            f"Бюджет {total:.0f} рублей."
        ),
        budget_min=total,
        budget_max=total,
    )


def test_deferment_over_limit_goes_to_human():
    order = _арматура("2 тонны, просим отсрочку 60 дней", 140000)
    decision = AnalysisService._apply_business_rules(
        _service(), order, COMPANY, _llm_result()
    )
    assert "deferment_over_limit" in decision.applied_rules
    assert decision.result.needs_review is True
    assert "60" in (decision.result.review_reason or "")


def test_deferment_within_limit_is_not_blocked():
    """21 день при лимите 30 — не повод для проверки: модель ошиблась в этом на прогоне."""
    order = _арматура("2 тонны, отсрочка 21 день", 140000)
    decision = AnalysisService._apply_business_rules(
        _service(), order, COMPANY, _llm_result()
    )
    assert "deferment_over_limit" not in decision.applied_rules
    assert decision.result.recommendation is Recommendation.APPLY


def test_large_order_goes_to_human():
    order = _арматура("20 тонн", 1200000, city="Барнаул")
    decision = AnalysisService._apply_business_rules(
        _service(), order, COMPANY, _llm_result()
    )
    assert "large_order_needs_human" in decision.applied_rules
    assert decision.result.recommendation is Recommendation.REVIEW
    assert "Крупная" in decision.result.reason


def test_region_outside_goes_to_human():
    order = _арматура("4 тонны", 190000, city="Астану, Казахстан")
    decision = AnalysisService._apply_business_rules(
        _service(), order, COMPANY, _llm_result()
    )
    assert "region_out_of_service_area" in decision.applied_rules
    assert decision.result.recommendation is Recommendation.REVIEW


def test_prompt_passes_computed_intake_facts():
    prompt = build_order_prompt(REQUEST, COMPANY)
    assert "intake_facts" in prompt.user
    assert "deferment_limit_days" in prompt.user
    assert "region_status" in prompt.user
