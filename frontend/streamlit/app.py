"""AI Freelance Copilot --- веб-панель (Streamlit, ТЗ §4, §23---§26).

Запуск: streamlit run frontend/streamlit/app.py
Требует работающий backend: uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui import get_client  # noqa: E402  (импорт после правки sys.path)

st.set_page_config(
    page_title="AI Freelance Copilot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES_DIR = Path(__file__).resolve().parent / "pages"

navigation = st.navigation(
    [
        st.Page(PAGES_DIR / "overview.py", title="Обзор", icon=":material/dashboard:", default=True),
        st.Page(PAGES_DIR / "orders.py", title="Заказы", icon=":material/list:"),
        st.Page(PAGES_DIR / "order_detail.py", title="Карточка заказа", icon=":material/description:"),
        st.Page(PAGES_DIR / "review.py", title="Требуют проверки", icon=":material/warning:"),
        st.Page(PAGES_DIR / "audit.py", title="Аудит и ошибки", icon=":material/history:"),
        st.Page(PAGES_DIR / "metrics.py", title="Метрики и экономика", icon=":material/insights:"),
    ]
)

with st.sidebar:
    st.caption("AI Freelance Copilot · MVP")
    client = get_client()
    health = None
    try:
        health = client.health()
    except Exception as exc:  # noqa: BLE001 - панель обязана пережить недоступный backend
        st.error(f"Backend недоступен:\n{exc}")
    if health:
        provider = health.get("provider", {})
        st.success(f"Backend: {health.get('status')} · БД: {health.get('database')}")
        if provider.get("is_live"):
            st.warning(f"LLM: {provider.get('name')} / {provider.get('model')} (тратит деньги)")
        else:
            st.warning(f"LLM: {provider.get('name')} (офлайн, тестовый) — модель не вызывается")
            if provider.get("hint"):
                st.caption(provider["hint"])
        st.caption(f"Промпт: {provider.get('prompt_version')}")
    st.caption(
        "Реальные площадки и автоотправка откликов в MVP не подключены (ТЗ §22)."
    )

navigation.run()
