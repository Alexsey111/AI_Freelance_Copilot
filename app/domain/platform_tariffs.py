"""Тарифы площадок: сколько стоит одна попытка откликнуться.

Тариф не персональный — он общий для площадки, поэтому хранится как данные, а не как
настройка пользователя. Данные лежат в `app/data/platform_tariffs.json` с датой проверки
и ссылкой на источник: цена без источника через месяц превращается в выдумку.

Модели монетизации различаются, и от этого зависит экономика:

- пакеты откликов (FL.ru, Freelance.ru) — платишь вперёд, отклики сгорают по сроку;
- кредиты по уровню (Kwork) — бесплатная норма в месяц, сверх неё цена только в кабинете;
- подписка за доступ (Work-Zilla) — отклики не считаются, платишь за вход;
- норма + подписка (Freelancer.com, PeoplePerHour) — N бесплатных попыток, дальше пакет.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "platform_tariffs.json"

VERIFIED = "verified"
PARTIAL = "partial"
BLOCKED = "blocked"

STATUS_LABELS = {
    VERIFIED: "проверено на сайте площадки",
    PARTIAL: "частично: цена закрыта кабинетом",
    BLOCKED: "недоступно из России",
}


@dataclass(frozen=True, slots=True)
class Offer:
    """Один вариант покупки попыток: пакет, подписка или разовый отклик."""

    title: str
    quota: int | None
    price: float
    currency: str
    days: int | None = None
    note: str | None = None

    @property
    def per_response(self) -> float | None:
        """Цена одной попытки внутри варианта. None — когда попытки не считаются."""
        if not self.quota or self.quota <= 0:
            return None
        return round(self.price / self.quota, 2)


@dataclass(frozen=True, slots=True)
class Platform:
    key: str
    title: str
    country: str
    status: str
    model: str
    free_per_month: int | None
    free_note: str
    packages: tuple[Offer, ...]
    subscription: tuple[Offer, ...]
    single_response: float | None
    single_note: str | None
    extra: tuple[dict, ...]
    source: str
    caveat: str | None
    currency: str = "RUB"

    @property
    def best_per_response(self) -> Offer | None:
        """Самый дешёвый вариант по цене одной попытки."""
        candidates = [
            offer
            for offer in self.packages + self.subscription
            if offer.per_response is not None
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda offer: offer.per_response or 0.0)

    @property
    def best_price(self) -> float | None:
        """Сколько стоит одна попытка в лучшем варианте — число для настройки «цена отклика»."""
        best = self.best_per_response
        if best is not None:
            return best.per_response
        if self.single_response is not None:
            return self.single_response
        return None

    @property
    def best_kind(self) -> str | None:
        """Откуда взялась лучшая цена: пакет откликов или подписка. Это разные риски."""
        best = self.best_per_response
        if best is None:
            return None
        return "subscription" if best in self.subscription else "package"

    @property
    def best_currency(self) -> str:
        """Валюта лучшей цены: у зарубежных площадок это доллары, путать с рублями нельзя."""
        best = self.best_per_response
        return best.currency if best is not None else self.currency

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


def _offer(raw: dict, default_currency: str) -> Offer:
    return Offer(
        title=raw["title"],
        quota=raw.get("quota"),
        price=float(raw["price"]),
        currency=raw.get("currency", default_currency),
        days=raw.get("days"),
        note=raw.get("note"),
    )


@lru_cache(maxsize=1)
def _load() -> tuple[str, tuple[Platform, ...]]:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    platforms = []
    for raw in payload["platforms"]:
        currency = raw.get("currency", "RUB")
        platforms.append(
            Platform(
                key=raw["key"],
                title=raw["title"],
                country=raw["country"],
                status=raw["status"],
                model=raw["model"],
                free_per_month=raw.get("free_per_month"),
                free_note=raw.get("free_note", ""),
                packages=tuple(_offer(item, currency) for item in raw.get("packages") or []),
                subscription=tuple(_offer(item, currency) for item in raw.get("subscription") or []),
                single_response=raw.get("single_response"),
                single_note=raw.get("single_note"),
                extra=tuple(raw.get("extra", [])),
                source=raw["source"],
                caveat=raw.get("caveat"),
                currency=currency,
            )
        )
    return payload["checked_at"], tuple(platforms)


def checked_at() -> str:
    return _load()[0]


def platforms() -> tuple[Platform, ...]:
    return _load()[1]


def find(key: str) -> Platform | None:
    return next((item for item in platforms() if item.key == key), None)
