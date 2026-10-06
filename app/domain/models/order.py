"""Доменная модель заказа (ТЗ §5.1) и его жизненный цикл (ТЗ §27, §28)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    """Фиксированный набор статусов заказа (ТЗ §27). Произвольные строки не используются."""

    NEW = "new"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class OrderSource(str, Enum):
    """Источник заказа. На MVP используется только MANUAL, остальное --- задел (ТЗ §5.1, §18)."""

    MANUAL = "manual"
    FLRU = "flru"
    KWORK = "kwork"
    FREELANCE_RU = "freelance_ru"
    TELEGRAM = "telegram"
    RSS = "rss"
    API = "api"
    WEBHOOK = "webhook"


@dataclass(slots=True)
class Order:
    """Заказ в едином доменном виде. Бизнес-логика не знает, откуда он пришёл."""

    id: int | None = None
    external_id: str | None = None
    source: str = OrderSource.MANUAL.value
    title: str = ""
    description: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "RUB"
    url: str | None = None
    client_name: str | None = None
    status: str = OrderStatus.NEW.value
    needs_review: bool = False
    raw_input: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def full_text(self) -> str:
        """Текст, который уходит в анализ: заголовок + описание."""
        return f"{self.title}\n{self.description}".strip()

    @property
    def has_budget(self) -> bool:
        return self.budget_min is not None or self.budget_max is not None

    def missing_data(self, min_description_chars: int = 40) -> list[str]:
        """Каких критически важных данных не хватает (ТЗ §13, §14 случай 1).

        Возвращает список человекочитаемых причин. Пустой список = данных достаточно.
        Отсутствующие данные НЕ додумываются (ТЗ §29.2).
        """
        missing: list[str] = []
        if not self.title.strip():
            missing.append("не указано название заказа")
        if len(self.description.strip()) < min_description_chars:
            missing.append("описание слишком короткое / не указан объём работ")
        if not self.has_budget:
            missing.append("не указан бюджет")
        return missing
