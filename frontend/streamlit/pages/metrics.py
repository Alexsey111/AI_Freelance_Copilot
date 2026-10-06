"""Экран «Метрики и экономика»: KPI ТЗ §34 и мини-экономика ТЗ §33."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import get_client  # noqa: E402

client = get_client()
st.title("Метрики и экономика")

hourly_rate = st.number_input(
    "Стоимость часа работы, ₽",
    min_value=100.0,
    max_value=100000.0,
    value=1500.0,
    step=100.0,
    help=(
        "Сколько стоит один час ВАШЕГО времени — не цена заказа. "
        "Ориентир: доход в час в последних проектах. Расчёт пересчитывается сразу."
    ),
)

try:
    metrics = client.metrics(hourly_rate_rub=hourly_rate)
except Exception as exc:  # noqa: BLE001
    st.error(str(exc))
    st.stop()


def show(value, suffix: str = "") -> str:
    """null -> «нет данных». Ноль не подставляется: нет данных != нулевой результат."""
    return "нет данных" if value is None else f"{value}{suffix}"


st.subheader("Главная метрика")
st.markdown(
    "**Сколько времени человек экономит при обработке одного заказа.** "
    "Рабочее значение — фактический замер владельца; разбивка из ТЗ §33 показана рядом для сравнения."
)

economy = metrics["economy"]
col1, col2, col3 = st.columns(3)
col1.metric("Вручную, 1 заказ", f"{economy['manual_order_minutes']} мин", help=economy["manual_time_source"])
col2.metric("С системой, 1 заказ", f"{economy['assisted_order_minutes']} мин",
            help=economy["assisted_time_source"])
col3.metric("Экономия", f"{economy['manual_order_minutes'] - economy['assisted_order_minutes']} мин")

st.markdown("**На 100 заказов:**")
col4, col5, col6 = st.columns(3)
col4.metric("Вручную", f"{economy['manual_100_hours']} ч")
col5.metric("С системой", f"{economy['assisted_100_hours']} ч")
col6.metric("Экономия", f"{economy['saved_hours_per_100']} ч ≈ {economy['saved_money_rub_per_100']:,.0f} ₽",
            help=economy["money_formula"])

with st.expander("Откуда взяты цифры (что замерено, а что оценка)"):
    st.markdown(
        f"- **{economy['manual_order_minutes']} мин вручную** — {economy['manual_time_source']}\n"
        f"- **{economy['assisted_order_minutes']} мин с системой** — {economy['assisted_time_source']}\n"
        f"- **Ставка** — {economy['hourly_rate_hint']}\n"
        f"- **Формула денег** — `{economy['money_formula']}`"
    )
    st.markdown("**Сравнение с исходным требованием ТЗ §33** (оценочные 13 мин вместо замера):")
    cmp1, cmp2 = st.columns(2)
    cmp1.metric("Экономия по ТЗ, ч", f"{economy['saved_minutes_per_100_spec'] / 60:.1f}")
    cmp2.metric("По ТЗ, ₽", f"{economy['saved_money_rub_per_100_spec']:,.0f} ₽")
    st.caption(
        "Разница — это и есть цена честного замера: учебная разбивка (13 мин) давала более "
        "оптимистичную картину, чем фактическое время владельца (8 мин)."
    )

st.divider()
st.subheader("Дополнительные метрики")
rows = [
    ("Заказов всего", metrics["orders_total"], ""),
    ("Анализов всего", metrics["analyses_total"], ""),
    ("Ошибок анализа", metrics["analyses_errors"], ""),
    ("Доля корректных JSON", metrics["json_valid_rate"], ""),
    ("Доля заказов на ручной проверке", metrics["review_share"], ""),
    ("Доля рекомендаций «откликаться»", metrics["apply_share"], ""),
    ("Средний match score", metrics["avg_match_score"], ""),
    ("Среднее время ИИ-анализа, мс", metrics["avg_analyze_duration_ms"], ""),
    ("Максимальное время ИИ-анализа, мс", metrics["max_analyze_duration_ms"], ""),
    ("Записей в аудите", metrics["audit_total"], ""),
]
table = []
for name, value, suffix in rows:
    if name.startswith("Доля") and value is not None:
        rendered = f"{value * 100:.0f}%"
    elif name == "Средний match score" and value is not None:
        rendered = f"{value:.2f}"
    elif value is None:
        rendered = "нет данных"
    elif isinstance(value, float):
        rendered = f"{value:.2f}{suffix}"
    else:
        rendered = f"{value}{suffix}"
    table.append({"Метрика": name, "Значение": rendered})
st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

st.caption(
    "Значение «нет данных» означает, что метрика не может быть посчитана "
    "(например, доля корректных JSON при нуле анализов) — это не ноль."
)

st.divider()
st.subheader("Распределения")
col7, col8 = st.columns(2)
with col7:
    st.markdown("**Заказы по статусам**")
    by_status = metrics["orders_by_status"]
    st.dataframe(
        pd.DataFrame([{"Статус": k, "Количество": v} for k, v in by_status.items()])
        if by_status
        else pd.DataFrame([{"Статус": "нет данных", "Количество": 0}]),
        use_container_width=True,
        hide_index=True,
    )
with col8:
    st.markdown("**Анализы по рекомендациям**")
    by_rec = metrics["analyses_by_recommendation"]
    st.dataframe(
        pd.DataFrame([{"Рекомендация": k, "Количество": v} for k, v in by_rec.items()])
        if by_rec
        else pd.DataFrame([{"Рекомендация": "нет данных", "Количество": 0}]),
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    f"Фактическое среднее время ИИ-анализа: {show(economy['measured_avg_analysis_seconds'], ' c')}. "
    "В отчёте цифры «на салфетке» заменяются этими фактическими замерами."
)
