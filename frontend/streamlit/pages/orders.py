"""Экран «Заказы»: витрина + создание заказа (ТЗ §9, §10, §23)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import (  # noqa: E402
    ORDER_STATUS_LABELS,
    get_client,
    orders_table,
    score,
)

client = get_client()
st.title("Заказы")

with st.expander("➕ Создать заказ (Endpoint №1: POST /api/v1/orders)", expanded=False):
    with st.form("create_order"):
        title = st.text_input("Название*", value="Разработка Telegram-бота на Python с ИИ")
        description = st.text_area(
            "Описание",
            value=(
                "Нужен Telegram-бот на Python с интеграцией LLM. Требуется опыт FastAPI, "
                "REST API, Docker, работа с PostgreSQL. Бюджет фиксированный, срок 3 недели."
            ),
            height=140,
        )
        col1, col2, col3 = st.columns(3)
        budget_min = col1.number_input("Бюджет от", min_value=0, value=30000, step=1000)
        budget_max = col2.number_input("Бюджет до", min_value=0, value=50000, step=1000)
        currency = col3.selectbox("Валюта", ["RUB", "USD", "EUR"])
        url = st.text_input("Ссылка на заказ", value="")
        source = st.selectbox(
            "Источник",
            ["manual", "flru", "kwork", "freelance_ru", "telegram", "rss", "api", "webhook"],
            help="В MVP заказ создаётся вручную (manual). Остальные значения — задел на будущие адаптеры.",
        )
        submitted = st.form_submit_button("Создать", type="primary")

    if submitted:
        payload = {
            "title": title,
            "description": description,
            "budget_min": budget_min or None,
            "budget_max": budget_max or None,
            "currency": currency,
            "url": url or None,
            "source": source,
        }
        try:
            created = client.create_order(payload)
            st.success(f"Заказ #{created['id']} создан, статус: {created['status']}")
            if created.get("needs_review"):
                st.warning(
                    "Данных не хватает (нет бюджета или слишком короткое описание) — "
                    "заказ сразу помечен как требующий проверки."
                )
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

st.divider()
st.subheader("Фильтры")
col1, col2, col3, col4 = st.columns(4)
status_filter = col1.selectbox(
    "Статус", ["все", *ORDER_STATUS_LABELS.keys()], format_func=lambda v: "все" if v == "все" else ORDER_STATUS_LABELS[v]
)
review_filter = col2.selectbox("Ручная проверка", ["все", "требуют проверки", "без проверки"])
recommendation_filter = col3.selectbox("Рекомендация", ["все", "apply", "skip", "review"])
page_size = col4.selectbox("На странице", [10, 20, 50], index=1)

params = {"page": 1, "page_size": page_size}
if status_filter != "все":
    params["status"] = status_filter
if review_filter == "требуют проверки":
    params["needs_review"] = True
elif review_filter == "без проверки":
    params["needs_review"] = False
if recommendation_filter != "все":
    params["recommendation"] = recommendation_filter

try:
    listing = client.list_orders(**params)
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))
    st.stop()

st.caption(f"Всего заказов: {listing['total']}")
if not listing["items"]:
    st.info("Под фильтры ничего не попало.")
else:
    st.dataframe(orders_table(listing["items"]), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Быстрые действия")
    for order in listing["items"][:10]:
        analysis = order.get("latest_analysis") or {}
        with st.container(border=True):
            cols = st.columns([6, 2, 2, 2])
            cols[0].markdown(f"**#{order['id']} {order['title'][:80]}**")
            cols[1].write(f"Match: {score(analysis.get('match_score'))}")
            cols[2].write(f"Проверка: {'⚠ да' if order.get('needs_review') else '—'}")
            if cols[3].button("Проанализировать", key=f"analyze_{order['id']}"):
                with st.spinner("ИИ анализирует заказ..."):
                    try:
                        outcome = client.analyze(order["id"])
                        result = outcome["result"]
                        if result["needs_review"]:
                            st.warning(f"#{order['id']}: на проверку — {result['review_reason']}")
                        else:
                            st.success(
                                f"#{order['id']}: {result['recommendation']} "
                                f"(match {score(result['match_score'])}), "
                                f"{outcome['duration_ms']} мс"
                            )
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))
            cols[3].caption("Открыть карточку: раздел «Карточка заказа»")
