"""Экран «Карточка заказа»: входные данные, ИИ-анализ, черновик, сырой ввод/вывод (ТЗ §24)."""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import (  # noqa: E402
    budget_range,
    get_client,
    render_result,
    review_label,
    score,
    status_label,
)

client = get_client()
st.title("Карточка заказа")

listing = None
try:
    listing = client.list_orders(page=1, page_size=200)
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))

if not listing or not listing["items"]:
    st.info("Заказов нет. Создайте заказ в разделе «Заказы».")
    st.stop()

options = {f"#{o['id']} — {o['title'][:70]}": o["id"] for o in listing["items"]}
selected = st.selectbox("Выберите заказ", list(options.keys()))
order_id = options[selected]

try:
    order = client.get_order(order_id)
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))
    st.stop()

col1, col2, col3 = st.columns([3, 1, 1])
col1.subheader(f"#{order['id']} {order['title']}")
col2.metric("Статус", status_label(order["status"]))
col3.metric("Проверка", "⚠ да" if order["needs_review"] else "нет")

info_col1, info_col2 = st.columns(2)
with info_col1:
    st.markdown("**Входные данные**")
    st.write(f"**Бюджет:** {budget_range(order)}")
    st.write(f"**Источник:** {order['source']}")
    st.write(f"**Клиент:** {order.get('client_name') or '—'}")
with info_col2:
    st.write(f"**URL:** {order.get('url') or '—'}")
    st.write(f"**Создан:** {order.get('created_at')}")
    st.write(f"**Обновлён:** {order.get('updated_at')}")

st.markdown("**Описание**")
st.write(order.get("description") or "—")

with st.container(border=True):
    analysis_col1, analysis_col2 = st.columns([3, 1])
    analysis_col1.markdown("### ИИ-анализ (Endpoint №3)")
    profile = None
    with contextlib.suppress(Exception):
        # Профиль — вспомогательная информация: без него карточка обязана открыться.
        profile = client.active_profile()
    if profile:
        analysis_col2.caption(f"Профиль: {profile['name']} ({len(profile['skills'])} навыков)")
    if analysis_col1.button("Запустить анализ", type="primary", key=f"run_{order_id}"):
        with st.spinner("ИИ анализирует заказ..."):
            try:
                outcome = client.analyze(order_id, profile["id"] if profile else None)
                st.success(
                    f"Готово за {outcome['duration_ms']} мс · провайдер {outcome['provider']} · "
                    f"статус аудита: {outcome['audit_status']}"
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    latest = None
    try:
        latest = client.latest_analysis(order_id)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))

    if latest:
        render_result(
            {
                "match_score": latest["match_score"],
                "recommendation": latest["recommendation"],
                "reason": latest["reason"],
                "matched_skills": latest["matched_skills"],
                "missing_skills": latest["missing_skills"],
                "draft_reply": latest["draft_reply"],
                "needs_review": latest["needs_review"],
                "review_reason": latest["review_reason"],
            }
        )
        st.caption(
            f"Модель: {latest.get('model')} · версия промпта: {latest.get('prompt_version')} · "
            f"решение человека: {review_label(latest.get('review_status'))}"
        )
        if latest.get("error"):
            st.error(f"Ошибка при анализе: {latest['error']}")
    else:
        st.info("Анализ ещё не запускался.")

st.divider()
tab_raw_in, tab_raw_out, tab_history = st.tabs(
    ["Сырой ввод (raw_input)", "Сырой вывод модели (raw_output)", "История анализов"]
)
with tab_raw_in:
    st.json(order.get("raw_input") or {}, expanded=True)
with tab_raw_out:
    if latest and latest.get("raw_output"):
        try:
            st.json(json.loads(latest["raw_output"]), expanded=True)
        except json.JSONDecodeError:
            st.code(latest["raw_output"], language="json")
    else:
        st.info("Сырой вывод модели отсутствует.")
with tab_history:
    try:
        history = client.order_analyses(order_id)
    except Exception as exc:  # noqa: BLE001
        history = []
        st.error(str(exc))
    if not history:
        st.info("Запусков анализа по этому заказу не было.")
    for item in history:
        with st.expander(
            f"#{item['id']} · {item['recommendation']} · match {score(item['match_score'])} · "
            f"{item['created_at']}"
        ):
            st.write(f"**Причина:** {item['reason']}")
            st.write(f"**Проверка:** {'да — ' + (item.get('review_reason') or '') if item['needs_review'] else 'нет'}")
            st.write(f"**Модель:** {item.get('model')} · **промпт:** {item.get('prompt_version')}")
            if item.get("error"):
                st.error(item["error"])
            if item.get("draft_reply"):
                st.text(item["draft_reply"])
