"""Воронка откликов: сколько стоит один найм.

Отклик на бирже — не бесплатное действие. FL.ru берёт деньги за предложение сверх лимита,
Kwork — за отклики и поднятие, Freelancer.com — за пакеты ставок, Upwork — за кредиты
(Connects). Значит экономика заказа — это не «бюджет ÷ часы», а «(бюджет − цена отклика ×
число откликов до найма) ÷ часы».

Поэтому в системе хранится журнал: сколько откликов отправлено, сколько стоили, сколько
дали ответ, сколько закончились наймом. Из него считается цена одного найма — цифра,
которая говорит правду о канале, а не о надеждах.
"""

from __future__ import annotations

from dataclasses import dataclass

SENT = "sent"
REPLIED = "replied"
HIRED = "hired"
DECLINED = "declined"
SILENT = "silent"

STATUSES = (SENT, REPLIED, HIRED, DECLINED, SILENT)

LABELS = {
    SENT: "отправлен",
    REPLIED: "клиент ответил",
    HIRED: "взял в работу",
    DECLINED: "отказ",
    SILENT: "тишина",
}

# Три режима работы с площадками. Разница не в коде, а в том, кто нажимает «отправить».
DRAFT_ONLY = "draft_only"  # система пишет текст, отправляет человек — всегда законно
SEMI_AUTO = "semi_auto"  # система заполняет форму в браузере, отправляет человек
FULL_AUTO = "full_auto"  # только там, где есть официальное разрешение/API

MODES = (DRAFT_ONLY, SEMI_AUTO, FULL_AUTO)

MODE_LABELS = {
    DRAFT_ONLY: "только черновик: отправляю сам",
    SEMI_AUTO: "полуавтомат: форма заполнена, кнопка за мной",
    FULL_AUTO: "автоотправка (только с разрешения площадки)",
}


@dataclass(slots=True)
class Funnel:
    sent: int = 0
    replied: int = 0
    hired: int = 0
    declined: int = 0
    silent: int = 0
    cost: float = 0.0
    hired_money: float = 0.0

    @property
    def reply_rate(self) -> float | None:
        return round(self.replied / self.sent, 3) if self.sent else None

    @property
    def hire_rate(self) -> float | None:
        return round(self.hired / self.sent, 3) if self.sent else None

    @property
    def cost_per_hire(self) -> float | None:
        """Сколько рублей откликов ушло на один найм. None — наймов ещё не было."""
        if not self.hired:
            return None
        return round(self.cost / self.hired, 2)

    @property
    def cost_per_sent(self) -> float | None:
        return round(self.cost / self.sent, 2) if self.sent else None


def funnel(items: list[dict]) -> Funnel:
    """`items` — строки журнала: status, cost_rub, а также budget найденного заказа."""
    result = Funnel()
    for item in items:
        result.sent += 1
        result.cost += float(item.get("cost_rub") or 0.0)
        status = item.get("status") or SENT
        if status == REPLIED:
            result.replied += 1
        elif status == HIRED:
            result.hired += 1
            result.hired_money += float(item.get("money") or 0.0)
        elif status == DECLINED:
            result.declined += 1
        elif status == SILENT:
            result.silent += 1
    return result


@dataclass(slots=True)
class NetRate:
    """Ставка с учётом платных откликов: сколько останется на час, если платить за попытки."""

    budget: float
    hours: float
    response_cost: float
    expected_responses: float = 1.0
    field_note: str = ""

    @property
    def spend(self) -> float:
        return round(self.response_cost * self.expected_responses, 2)

    @property
    def net_budget(self) -> float:
        return round(max(self.budget - self.spend, 0.0), 2)

    @property
    def net_rate(self) -> float | None:
        if self.hours <= 0:
            return None
        return round(self.net_budget / self.hours, 0)

    @property
    def worth_it(self) -> bool:
        """Отклик окупается, если после его цены ставка не падает ниже нуля."""
        return self.net_budget > 0
