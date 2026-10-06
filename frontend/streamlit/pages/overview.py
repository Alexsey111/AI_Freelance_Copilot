"""Экран «Обзор»: состояние системы, последние заказы, что делать дальше."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import get_client, orders_table  # noqa: E402

st.title("AI Freelance Copilot")
st.caption(
    "MVP ядра системы автоматизации фриланса: заказ → ИИ-анализ соответствия профилю → "
    "черновик отклика → ручная проверка сомнительных результатов → аудит."
)

client = get_client()
metrics = None
try:
    metrics = client.metrics()
except Exception as exc:  # noqa: BLE001
    st.error(f"Не удалось получить метрики: {exc}")

if metrics:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Заказов", metrics["orders_total"])
    col2.metric("Анализов", metrics["analyses_total"])
    col3.metric("Ждут проверки", metrics["orders_needs_review"])
    col4.metric("Рекомендовано к отклику", metrics["orders_recommended"])

    col5, col6, col7 = st.columns(3)
    col5.metric(
        "Доля корректных JSON",
        "нет данных" if metrics["json_valid_rate"] is None else f"{metrics['json_valid_rate'] * 100:.0f}%",
    )
    col6.metric(
        "Ушло на проверку",
        "нет данных" if metrics["review_share"] is None else f"{metrics['review_share'] * 100:.0f}%",
    )
    col7.metric(
        "Среднее время анализа",
        "нет данных"
        if metrics["avg_analyze_duration_ms"] is None
        else f"{metrics['avg_analyze_duration_ms'] / 1000:.2f} c",
    )

st.divider()
st.subheader("Последние заказы")
try:
    listing = client.list_orders(page=1, page_size=10)
    if not listing["items"]:
        st.info(
            "Заказов пока нет. Откройте раздел «Заказы» и создайте первый заказ "
            "(вручную или скриптом scripts/seed_demo.py)."
        )
    else:
        st.dataframe(orders_table(listing["items"]), use_container_width=True, hide_index=True)
except Exception as exc:  # noqa: BLE001
    st.error(f"Не удалось получить список заказов: {exc}")

st.divider()
st.subheader("Что демонстрирует MVP")
st.markdown(
    """
    1. **Точка 1** — `POST /api/v1/orders`: заказ создаётся и нормализуется в единую доменную модель.
    2. **Точка 2** — `GET /api/v1/orders`: витрина с фильтрами и пагинацией.
    3. **Точка 3** — `POST /api/v1/orders/{id}/analyze`: ИИ-анализ, строгий JSON, черновик отклика.
    4. **Ручная проверка** — если данных не хватает, ответ модели невалиден или система не уверена,
       результат помечается `needs_review=true`, сохраняется причина и решение принимает человек.
    5. **Аудит** — каждый запуск (включая ошибки) пишется в `audit_runs` с длительностью.
    """
)
st.caption("Документация API: http://127.0.0.1:8000/docs")
