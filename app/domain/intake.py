"""Домен входящих заявок: факты, которые система считает сама.

Зачем отдельный модуль. В разборе заявок есть поля, которые модель читает
нестабильно: отсрочка платежа, регион поставки, крупная сумма. На живом прогоне
28.11.2026 модель написала «отсрочка 21 день превышает допустимые 30» — арифметика
неверная, решение всё равно ушло человеку, но по ложной причине.

Принцип тот же, что в ядре: LLM говорит, что система считает; правила решают,
что разрешено. Поэтому числа (дни отсрочки, попадание в регион, порог крупной
заявки) считаются здесь детерминированно и кладутся в промпт как факты,
а не как просьба «посчитай сам».
"""

from __future__ import annotations

import re

# Регионы вне зоны по умолчанию: если профиль не задал свой список, ищем эти маркеры.
DEFAULT_OUT_OF_AREA = (
    "казахстан",
    "астана",
    "алматы",
    "беларусь",
    "минск",
    "москва",
    "санкт-петербург",
    "спб",
)

_DEFERMENT = re.compile(
    r"отсрочк\w*[^\d]{0,40}?(\d{1,3})\s*(?:календарн\w+\s+)?(?:дн|день|дня|дней)",
    re.IGNORECASE,
)
# Обратный порядок: «60 дней отсрочки».
_DEFERMENT_REVERSED = re.compile(
    r"(\d{1,3})\s*(?:календарн\w+\s+)?(?:дн|день|дня|дней)\s+отсрочк",
    re.IGNORECASE,
)


def parse_deferment_days(text: str) -> int | None:
    """Сколько дней отсрочки просит клиент. None — в тексте отсрочки нет.

    Понимает «отсрочка 60 дней», «отсрочку платежа 14 дней», «отсрочка 21 день»,
    «60 дней отсрочки». Дробные и «месяц» не угадывает: неизвестно — это None.
    """
    haystack = text or ""
    for pattern in (_DEFERMENT, _DEFERMENT_REVERSED):
        match = pattern.search(haystack)
        if match:
            return int(match.group(1))
    return None


def _normalize(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def _name_stem(marker: str) -> str:
    """Основа названия без падежного окончания: «Астана» -> «астан», «Томск» -> «томск».

    Без этого «доставка в Астану» не ловится маркером «Астана», и регион уходит
    в «неизвестно» вместо «вне зоны». Режем только очевидные окончания, а не
    первые N символов: «красн» поймал бы Краснодар.
    """
    stem = _normalize(marker).strip()
    for ending in ("ами", "ах", "ой", "ая", "ый", "ий", "а", "я", "ы", "й", "е", "у"):
        if len(stem) > len(ending) + 3 and stem.endswith(ending):
            return stem[: -len(ending)]
    return stem


def detect_region(
    text: str, *, regions: list[str] | tuple[str, ...] | None, out_of_area=None
) -> tuple[str, str | None]:
    """Вернуть (статус, найденный маркер): served | outside | unknown.

    Сначала ищем свой регион: если он назван, заявка в зоне, даже когда рядом
    упомянут другой город (объект в Барнауле, юрлицо в Москве).
    """
    haystack = _normalize(text)
    for region in regions or ():
        if _name_stem(str(region)) in haystack:
            return "served", str(region)
    for marker in out_of_area or DEFAULT_OUT_OF_AREA:
        if _name_stem(marker) in haystack:
            return "outside", marker
    return "unknown", None


def intake_facts(order, profile) -> dict:
    """Факты заявки, посчитанные до модели (уходят в промпт и в правила ядра)."""
    preferences = getattr(profile, "preferences", None) or {}
    text = f"{order.title}\n{order.description}"
    region_status, region_found = detect_region(
        text,
        regions=preferences.get("regions"),
        out_of_area=preferences.get("out_of_area"),
    )
    order_total = order.budget_max if order.budget_max is not None else order.budget_min
    limit = preferences.get("max_deferment_days")
    days = parse_deferment_days(text)
    return {
        "deferment_days": days,
        "deferment_limit_days": int(limit) if limit is not None else None,
        "region_status": region_status,
        "region_found": region_found,
        "order_total_rub": order_total,
        "large_order_rub": preferences.get("large_order_review_rub"),
        "min_order_rub": preferences.get("min_budget_rub"),
    }
