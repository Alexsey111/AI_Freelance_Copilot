"""Экран «Аудит и ошибки»: журнал запусков, включая упавшие (ТЗ §26)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import AUDIT_STATUS_LABELS, get_client  # noqa: E402

client = get_client()
st.title("Аудит и ошибки")
st.caption(
    "Любой запуск системы пишется в журнал audit_runs: действие, вход, выход, статус, ошибка, "
    "длительность. Даже если запуск закончился ошибкой (ТЗ §29.4)."
)

try:
    summary = client.audit_actions()
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Всего записей", summary["total"])
col2.metric("Успешных", summary["statuses"].get("success", 0))
col3.metric("Ошибок", summary["statuses"].get("error", 0))

actions = ["все", *sorted(summary["actions"].keys())]
statuses = ["все", "success", "review", "error"]
filter_col1, filter_col2, filter_col3 = st.columns(3)
action_filter = filter_col1.selectbox("Действие", actions)
status_filter = filter_col2.selectbox(
    "Статус", statuses, format_func=lambda v: "все" if v == "все" else AUDIT_STATUS_LABELS[v]
)
page_size = filter_col3.selectbox("На странице", [25, 50, 100], index=1)

params = {"page": 1, "page_size": page_size}
if action_filter != "все":
    params["action"] = action_filter
if status_filter != "все":
    params["status"] = status_filter

try:
    audit = client.audit(**params)
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))
    st.stop()

if not audit["items"]:
    st.info("Записей по фильтру нет.")
    st.stop()

rows = []
for run in audit["items"]:
    rows.append(
        {
            "ID": run["id"],
            "Время": run["created_at"],
            "Действие": run["action"],
            "Заказ": run["order_id"] or "—",
            "Статус": AUDIT_STATUS_LABELS.get(run["status"], run["status"]),
            "Длительность, мс": run["duration_ms"],
            "Ошибка": (run["error"] or "")[:60],
        }
    )
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Детали записи")
labels = {
    f"#{r['id']} · {r['created_at']} · {r['action']} · {AUDIT_STATUS_LABELS.get(r['status'], r['status'])}": r
    for r in audit["items"]
}
chosen = st.selectbox("Запись", list(labels.keys()))
record = labels[chosen]

st.write(f"**Action:** {record['action']}")
st.write(f"**Status:** {AUDIT_STATUS_LABELS.get(record['status'], record['status'])}")
st.write(f"**Длительность:** {record['duration_ms']} мс")
if record.get("error"):
    st.error(f"**Error:** {record['error']}")
for title, key in (("Input", "input"), ("Output", "output")):
    st.markdown(f"**{title}:**")
    value = record.get(key)
    if not value:
        st.write("—")
        continue
    try:
        st.json(json.loads(value), expanded=False)
    except json.JSONDecodeError:
        st.code(value)
