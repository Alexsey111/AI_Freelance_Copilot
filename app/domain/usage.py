"""Стоимость вызова модели: считаем только по прайсу, который задал пользователь.

Цены не зашиваются в код: провайдеров десятки, у каждого своя тарифная сетка, у локальной
модели её нет вообще. Пользователь вводит два числа — ₽ за миллион входных и ₽ за миллион
выходных токенов; если не ввёл, стоимость остаётся `None`, и это честнее нуля.

Причина, по которой `None` важен: ноль читается как «бесплатно» и усыпляет. Пустое поле
в интерфейсе читается как «неизвестно» — и человек идёт смотреть тариф.
"""

from __future__ import annotations

MILLION = 1_000_000


def cost_rub(
    tokens_in: int | None,
    tokens_out: int | None,
    *,
    price_in_rub_per_1m: float | None,
    price_out_rub_per_1m: float | None,
) -> float | None:
    """Стоимость вызова. Любая из цен не задана — стоимости нет, а не ноль."""
    if price_in_rub_per_1m is None or price_out_rub_per_1m is None:
        return None
    if tokens_in is None or tokens_out is None:
        return None
    total = tokens_in * price_in_rub_per_1m + tokens_out * price_out_rub_per_1m
    return round(total / MILLION, 6)


def format_cost(cost: float | None) -> str:
    """Человеческая подпись: копейки не теряются, а «не задано» не притворяется нулём."""
    if cost is None:
        return "цена не задана"
    if cost == 0:
        return "0 ₽"
    if cost < 0.01:
        return f"{cost * 100:.3f} коп."
    return f"{cost:.4f} ₽".replace(".", ",")
