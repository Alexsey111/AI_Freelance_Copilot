"""Площадки в заказах: с какой площадки пришёл заказ и с какими площадками работать.

У заказа есть поле `source` — строка от парсера или из ручного ввода («fl.ru», «manual»).
Пользователь выбирает не строку, а площадку из справочника, поэтому строки сводятся к
ключам. Незнакомый источник — не ошибка: это «ручной ввод» или новый парсер, который ещё
не привязан к справочнику, и такой заказ нельзя терять.
"""

from __future__ import annotations

UNKNOWN_SOURCE = "manual"

# Ключ площадки → написания, которые могут прийти в orders.source от парсеров и людей.
SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "flru": ("fl.ru", "flru", "fl"),
    "freelance_ru": ("freelance.ru", "freelance_ru", "freelanceru"),
    "kwork": ("kwork", "kwork.ru"),
    "workzilla": ("work-zilla", "workzilla", "work-zilla.com"),
    "freelancer": ("freelancer.com", "freelancer", "flcom"),
    "peopleperhour": ("peopleperhour", "peopleperhour.com", "pph"),
    "upwork": ("upwork", "upwork.com"),
}


def normalize_source(source: str | None) -> str:
    """Приводит orders.source к ключу площадки; неизвестное — к «manual»."""
    raw = (source or "").strip().lower()
    if not raw:
        return UNKNOWN_SOURCE
    for key, aliases in SOURCE_ALIASES.items():
        if raw == key or raw in aliases:
            return key
    return UNKNOWN_SOURCE


def aliases_for(keys: list[str] | tuple[str, ...]) -> list[str]:
    """Обратное преобразование: ключи площадок → все написания для фильтра в SQL."""
    result: list[str] = []
    for key in keys:
        if key == UNKNOWN_SOURCE:
            result.append(UNKNOWN_SOURCE)
            continue
        result.extend(SOURCE_ALIASES.get(key, (key,)))
    return sorted(set(result))


def known_keys() -> tuple[str, ...]:
    return tuple(SOURCE_ALIASES)
