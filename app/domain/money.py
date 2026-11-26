"""Нормализация денежных значений на входе в ядро.

Зачем. Бюджет приходит из разных источников: API, парсеры бирж, HTML-формы вроде Tilda,
вебхук из n8n. В вёрстке и в тексте объявления деньги всегда строка, поэтому «50 000»,
«(50000)», «50к», «1,5 млн», «от 15 000 до 20 000» — это нормальные входы, а не мусор.
Дальше бюджет сравнивается с минимумом профиля, и если он остался строкой, сравнение
работает посимвольно («9000» > «50000») или падает с TypeError.

Политика (решение владельца 26.11.2026):

* однозначное число в любой обычной записи -> число;
* бюджета нет, «договорная», «по договорённости» -> ``None``: это не мусор, заказ уходит
  в правило «не указан бюджет» и на проверку человеку;
* цифры прописью («пятьдесят тысяч») -> ``None`` и пометка «нужен человек»: не угадываем;
* два числа в одном поле (диапазон) -> нижнее в ``budget_min``, верхнее в ``budget_max``;
* «минус наоборот» (min больше max) -> меняем местами: это явная опечатка, а не диапазон.

Почему не парсим прописью: покрытие такого парсера никогда не 100 %, а тихо неверный
бюджет дороже явной пометки «посмотреть человеком». Суммы из описания заказа тоже не
извлекаем: там встречаются чужие числа («аналог стоит 50 тысяч», «зарплата от 80к»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# Пробелы, которые приходят из HTML и из вставки из Word/Excel.
SPACES: Final = "\u00a0\u202f\u2009\u2007\u2060"

# Слова, которыми бюджет честно не назван. Это не ошибка данных, это отсутствие числа.
ABSENT_WORDS: Final = (
    "договорная",
    "договорной",
    "по договор",
    "договор",
    "торг",
    "обсужда",
    "не указан",
    "уточня",
)

_UNIT_FACTORS: Final[tuple[tuple[str, float], ...]] = (
    ("тысяч", 1e3),
    ("тыс", 1e3),
    ("млн", 1e6),
    ("миллион", 1e6),
    ("к", 1e3),
    ("k", 1e3),
    ("м", 1e6),
)

_NUMBER_TOKEN = re.compile(r"\d[\d\s.,]*\d|\d")
_THOUSANDS = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


@dataclass(slots=True)
class BudgetParse:
    """Результат разбора бюджета заказа."""

    low: float | None = None
    high: float | None = None
    status: str = "absent"  # parsed | absent | worded
    note: str | None = None
    raw_min: object = None
    raw_max: object = None

    @property
    def needs_human(self) -> bool:
        """Бюджет записан так, что машина его не поняла: решает человек."""
        return self.status == "worded"


def _clean_text(value: object) -> str:
    text = str(value)
    for space in SPACES:
        text = text.replace(space, " ")
    return " ".join(text.split())


def _number(token: str) -> float | None:
    """Собрать число из токена: «50 000», «60.000», «50 000,50», «1,5»."""
    text = token.replace(" ", "")
    if _THOUSANDS.match(text):
        text = text.replace(",", "").replace(".", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:  # pragma: no cover - токен уже отфильтрован регуляркой
        return None


def _unit_after(text: str, position: int) -> float:
    tail = text[position : position + 12].lower().lstrip()
    for unit, factor in _UNIT_FACTORS:
        if not tail.startswith(unit):
            continue
        rest = tail[len(unit) : len(unit) + 1]
        # «к» и «м» считаем множителем только как отдельное слово/символ в конце:
        # иначе «50 комнат» превратится в 50 000.
        if unit in {"к", "k", "м"} and rest and rest.isalpha():
            continue
        return factor
    return 1.0


def parse_amounts(value: object) -> tuple[list[float], str]:
    """Достать все числа из одного поля. Возвращает (числа, статус)."""
    if value is None:
        return [], "absent"
    if isinstance(value, bool):
        return [], "worded"
    if isinstance(value, int | float):
        number = float(value)
        return ([number] if number >= 0 else []), "parsed"

    text = _clean_text(value)
    if not text:
        return [], "absent"

    lowered = text.lower()
    matches = list(_NUMBER_TOKEN.finditer(text))
    if not matches:
        if any(word in lowered for word in ABSENT_WORDS):
            return [], "absent"
        if _CYRILLIC.search(lowered):
            # «пятьдесят тысяч», «полторы тысячи» — не угадываем, отдаём человеку.
            return [], "worded"
        return [], "absent"

    numbers: list[float] = []
    for match in matches:
        number = _number(match.group(0))
        if number is None:
            continue
        numbers.append(number * _unit_after(text, match.end()))
    return numbers, "parsed" if numbers else "absent"


def normalize_budget(budget_min: object, budget_max: object) -> BudgetParse:
    """Привести пару «min/max» к числам и объяснить, если не получилось."""
    low_numbers, low_status = parse_amounts(budget_min)
    high_numbers, high_status = parse_amounts(budget_max)

    result = BudgetParse(
        status="parsed",
        raw_min=budget_min,
        raw_max=budget_max,
    )

    if low_status == "worded" or high_status == "worded":
        result.status = "worded"
        result.note = "бюджет записан словами — распознать нельзя, нужен человек"
        # Числа, которые всё-таки распознали в другом поле, сохраняем.
    elif low_status == "absent" and high_status == "absent":
        result.status = "absent"
        return result

    everything = low_numbers + high_numbers
    if not everything:
        if result.status != "worded":
            result.status = "absent"
        return result

    # Диапазон внутри одного поля даёт и низ, и верх; одиночное число в budget_min
    # не выдумывает себе максимум.
    if low_numbers:
        result.low = min(low_numbers)
        if len(low_numbers) > 1:
            result.high = max(low_numbers)
    elif len(high_numbers) > 1:
        result.low = min(high_numbers)
    if high_numbers:
        result.high = max(high_numbers)

    if result.low is not None and result.high is not None and result.low > result.high:
        result.low, result.high = result.high, result.low
        note = "бюджет пришёл с перепутанными границами — значения поменяны местами"
        result.note = f"{result.note}; {note}" if result.note else note

    return result
