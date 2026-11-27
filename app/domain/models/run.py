"""Доменная модель прогона: условия, в которых получены решения.

Прогон нужен, чтобы у каждого решения был контекст: какая модель, какая версия промпта,
какой профиль, сколько заказов разобрано и сколько ушло человеку. Без этого нельзя
ответить ни «сколько стоил прогон», ни «что изменилось между прогонами».
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Run:
    kind: str
    status: str = "running"
    model: str | None = None
    prompt_version: str | None = None
    profile_id: int | None = None
    orders_total: int = 0
    orders_review: int = 0
    note: str | None = None
    id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def review_share(self) -> float | None:
        """Доля заказов, ушедших человеку. None, если в прогоне не было решений."""
        if not self.orders_total:
            return None
        return round(self.orders_review / self.orders_total, 4)
