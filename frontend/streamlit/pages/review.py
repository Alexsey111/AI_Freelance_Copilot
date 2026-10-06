"""Экран «Требуют проверки»: сомнительные результаты и решение человека (ТЗ §25)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import get_client, review_label, score, status_label  # noqa: E402

client = get_client()
st.title("Требуют проверки")
st.caption(
    "Система не делает вид, что уверена. Сюда попадают результаты, где данных не хватает, "
    "ответ модели невалиден или уверенность ниже порога."
)

status_filter = st.radio(
    "Показать", ["ожидают решения", "подтверждённые", "отклонённые", "все"], horizontal=True
)
params = {}
if status_filter == "ожидают решения":
    params["review_status"] = "pending"
elif status_filter == "подтверждённые":
    params["review_status"] = "approved"
elif status_filter == "отклонённые":
    params["review_status"] = "rejected"

try:
    queue = client.review_queue(page=1, page_size=100, **params)
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))
    st.stop()

st.caption(f"Записей: {queue['total']}")
if not queue["items"]:
    st.success("Очередь пуста — сомнительных результатов нет.")
    st.stop()

for item in queue["items"]:
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"### ⚠ Заказ #{item['order_id']} — {item['order_title'][:70]}")
        col2.write(f"Статус заказа: **{status_label(item['order_status'])}**")
        col1.write(f"**Причина проверки:** {item['review_reason'] or '—'}")
        col1.write(f"Match: {score(item['match_score'])} · решение человека: {review_label(item['review_status'])}")

        comment = st.text_input("Комментарий (необязательно)", key=f"comment_{item['analysis_id']}")
        approve_col, reject_col, _ = st.columns([1, 1, 4])
        if approve_col.button("✅ Подтвердить", key=f"approve_{item['analysis_id']}"):
            try:
                client.decide_review(item["analysis_id"], "approved", comment or None)
                st.success("Подтверждено. Действия (отправка отклика) в MVP не выполняются — ТЗ §22.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        if reject_col.button("⛔ Отклонить", key=f"reject_{item['analysis_id']}"):
            try:
                client.decide_review(item["analysis_id"], "rejected", comment or None)
                st.warning("Отклонено. Решение записано в журнал аудита.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
