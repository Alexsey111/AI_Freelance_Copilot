"""Общие элементы интерфейса: подписи статусов, форматирование, безопасный вызов API."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from api_client import ApiClient, ApiError

ORDER_STATUS_LABELS = {
    "new": "новый",
    "analyzing": "в работе",
    "analyzed": "проанализирован",
    "needs_review": "требует проверки",
    "approved": "подтверждён",
    "rejected": "отклонён",
    "error": "ошибка",
}

RECOMMENDATION_LABELS = {"apply": "откликаться", "skip": "пропустить", "review": "на проверку"}

AUDIT_STATUS_LABELS = {"success": "успех", "review": "на проверке", "error": "ошибка"}

REVIEW_STATUS_LABELS = {"pending": "ожидает решения", "approved": "подтверждён", "rejected": "отклонён"}


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient()


def api_guard(callable_, *args, **kwargs):
    """Вызвать API и показать понятную ошибку вместо трейсбека Streamlit."""
    try:
        return callable_(*args, **kwargs)
    except ApiError as exc:
        st.error(str(exc))
        return None


def money(value: float | None, currency: str = "RUB") -> str:
    if value is None:
        return "—"
    symbol = {"RUB": "₽", "USD": "$", "EUR": "€"}.get(currency, currency)
    return f"{value:,.0f} {symbol}".replace(",", " ")


def budget_range(order: dict) -> str:
    low, high = order.get("budget_min"), order.get("budget_max")
    if low is None and high is None:
        return "не указан"
    if low is not None and high is not None:
        if low == high:
            return money(low, order.get("currency", "RUB"))
        return f"{money(low, order.get('currency', 'RUB'))} — {money(high, order.get('currency', 'RUB'))}"
    return money(low if low is not None else high, order.get("currency", "RUB"))


def score(value: float | None) -> str:
    """Процент соответствия. None печатается как «—»: это "нет данных", а не 0%."""
    return "—" if value is None else f"{value * 100:.0f}%"


def status_label(value: str) -> str:
    return ORDER_STATUS_LABELS.get(value, value)


def review_label(value: str | None) -> str:
    return "—" if not value else REVIEW_STATUS_LABELS.get(value, value)


def orders_table(items: list[dict]) -> pd.DataFrame:
    """Таблица витрины (ТЗ §23)."""
    rows = []
    for order in items:
        analysis = order.get("latest_analysis") or {}
        rows.append(
            {
                "ID": order["id"],
                "Заказ": order["title"][:70],
                "Источник": order.get("source", ""),
                "Бюджет": budget_range(order),
                "Статус": status_label(order.get("status", "")),
                "Match": score(analysis.get("match_score")),
                "Рекомендация": RECOMMENDATION_LABELS.get(
                    analysis.get("recommendation", ""), "—"
                ),
                "Проверка": "⚠" if order.get("needs_review") else "—",
            }
        )
    return pd.DataFrame(rows)


def render_result(result: dict) -> None:
    """Блок ИИ-анализа в карточке заказа (ТЗ §24)."""
    col1, col2, col3 = st.columns(3)
    col1.metric("Соответствие", score(result.get("match_score")))
    col2.metric(
        "Рекомендация", RECOMMENDATION_LABELS.get(result.get("recommendation", ""), "—")
    )
    col3.metric("Ручная проверка", "да" if result.get("needs_review") else "нет")

    st.markdown("**Причина:**")
    st.write(result.get("reason") or "—")

    if result.get("needs_review"):
        st.warning(f"⚠ Требуется проверка человеком: {result.get('review_reason')}")

    skills_col, missing_col = st.columns(2)
    with skills_col:
        st.markdown("**Совпавшие навыки:**")
        st.write(", ".join(result.get("matched_skills") or []) or "—")
    with missing_col:
        st.markdown("**Недостающие навыки:**")
        st.write(", ".join(result.get("missing_skills") or []) or "—")

    st.markdown("**Черновик отклика:**")
    draft = result.get("draft_reply")
    if draft:
        st.text_area("Черновик", value=draft, height=220, key=f"draft_{id(result)}")
    else:
        st.info("Черновик не сформирован: система не придумывает отклик без достаточных данных.")
