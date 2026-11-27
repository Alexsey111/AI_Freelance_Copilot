"""Реестр правил, которые пользователь меняет без разработчика.

Здесь одно место, где перечислены все настраиваемые числа и слова: ключ, человеческое
название, пояснение, тип, границы. Из этого реестра собирается и экран настроек
в программе, и валидация API — чтобы не было двух списков, которые расходятся.

Правило: ни одно число, которое влияет на решение по заказу, не должно требовать
правки `app/config.py`. Если такое число появилось — оно обязано попасть сюда.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["number", "integer", "text", "choice"]


@dataclass(frozen=True, slots=True)
class Rule:
    key: str
    label: str
    help: str
    kind: Kind
    default: object
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    unit: str = ""

    def coerce(self, raw: str) -> object:
        """Строка из базы/формы -> значение нужного типа. Ошибка -> ValueError с текстом."""
        text = (raw or "").strip()
        if self.kind == "choice":
            if text not in self.choices:
                raise ValueError(
                    f"«{self.label}»: допустимо {', '.join(self.choices)}, получено «{text}»"
                )
            return text
        if self.kind == "text":
            return text
        try:
            number = float(text.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"«{self.label}»: ожидается число, получено «{text}»") from exc
        if self.minimum is not None and number < self.minimum:
            raise ValueError(f"«{self.label}»: меньше допустимого ({self.minimum:g}{self.unit})")
        if self.maximum is not None and number > self.maximum:
            raise ValueError(f"«{self.label}»: больше допустимого ({self.maximum:g}{self.unit})")
        if self.kind == "integer":
            if number != int(number):
                raise ValueError(f"«{self.label}»: ожидается целое число")
            return int(number)
        return number


RULES: dict[str, Rule] = {
    rule.key: rule
    for rule in (
        Rule(
            key="min_rate_rub_per_hour",
            label="Ставка, ниже которой не берём",
            help="Сколько вы хотите получать за час работы. Заказ дешевле этой ставки "
            "пойдёт только «добивкой простоя», если неделя не набрана.",
            kind="number",
            default=1_500.0,
            minimum=0.0,
            maximum=100_000.0,
            unit=" ₽/ч",
        ),
        Rule(
            key="available_hours_per_week",
            label="Сколько часов в неделю готовы работать",
            help="Это ограничитель набора заказов: больше часов, чем есть, система не наберёт.",
            kind="number",
            default=45.0,
            minimum=1.0,
            maximum=168.0,
            unit=" ч",
        ),
        Rule(
            key="target_week_rub",
            label="Цель недели",
            help="Сумма, при которой неделя считается набранной. Мелкие заказы ниже ставки "
            "берутся только пока цель не достигнута.",
            kind="number",
            default=75_000.0,
            minimum=0.0,
            maximum=10_000_000.0,
            unit=" ₽",
        ),
        Rule(
            key="budget_mode",
            label="Как применять порог бюджета",
            help="«Только не ниже порога» — жёстко по сумме заказа. «Набор на неделю» — "
            "складывает заказы, пока хватает часов и неделя не набрана.",
            kind="choice",
            default="portfolio",
            choices=("hard", "portfolio"),
        ),
        Rule(
            key="aging_fresh_hours",
            label="Заказ считается свежим до",
            help="Свежие заказы смотрят первыми: конкуренция ещё не набежала.",
            kind="number",
            default=6.0,
            minimum=0.5,
            maximum=168.0,
            unit=" ч",
        ),
        Rule(
            key="aging_stale_hours",
            label="Заказ на грани после",
            help="После этого возраста отклик ещё имеет смысл, но шанс уже ниже.",
            kind="number",
            default=12.0,
            minimum=1.0,
            maximum=336.0,
            unit=" ч",
        ),
        Rule(
            key="aging_dead_hours",
            label="Заказ не рассматриваем после",
            help="Возраст, после которого заказ не берём в разбор.",
            kind="number",
            default=24.0,
            minimum=2.0,
            maximum=720.0,
            unit=" ч",
        ),
        Rule(
            key="review_queue_overdue_hours",
            label="Решение ждёт человека дольше",
            help="Долг на вашей стороне: сколько часов решение может висеть в очереди "
            "проверки, прежде чем это станет проблемой.",
            kind="number",
            default=12.0,
            minimum=1.0,
            maximum=336.0,
            unit=" ч",
        ),
        Rule(
            key="competition_max_responses",
            label="Откликов, после которых «тесно»",
            help="Число откликов на карточке, при котором шанс уже невелик.",
            kind="integer",
            default=10,
            minimum=1.0,
            maximum=1000.0,
        ),
        Rule(
            key="competition_hard_responses",
            label="Откликов, после которых не берём",
            help="Заказ, куда уже откликнулись столько людей, клиент не прочитает.",
            kind="integer",
            default=20,
            minimum=2.0,
            maximum=5000.0,
        ),
        Rule(
            key="llm_price_in_rub_per_1m",
            label="Цена входных токенов модели",
            help="Рубли за миллион входных токенов по тарифу вашего провайдера. "
            "Не задано — стоимость прогона не считается.",
            kind="number",
            default=None,
            minimum=0.0,
            maximum=100_000.0,
            unit=" ₽/1М",
        ),
        Rule(
            key="llm_price_out_rub_per_1m",
            label="Цена выходных токенов модели",
            help="Рубли за миллион выходных токенов. У локальной модели цены нет — "
            "оставьте пустым.",
            kind="number",
            default=None,
            minimum=0.0,
            maximum=100_000.0,
            unit=" ₽/1М",
        ),
    )
}


def format_value(value: object) -> str:
    """Число в человеческом виде: 1500, а не 1500.0 — в окне настроек это важно."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def validate(key: str, raw: str) -> object:
    """Проверка одного значения. Неизвестный ключ — ошибка, а не «молча примем»."""
    rule = RULES.get(key)
    if rule is None:
        raise ValueError(f"Неизвестная настройка: {key}")
    return rule.coerce(raw)


def label_of(key: str) -> str:
    rule = RULES.get(key)
    return rule.label if rule else key
