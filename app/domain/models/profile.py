"""Доменная модель профиля исполнителя (ТЗ §6)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Profile:
    """Профиль исполнителя. Нужен, чтобы отвечать на вопрос
    "подходит ли заказ КОНКРЕТНОМУ исполнителю", а не "хорош ли заказ вообще".
    """

    id: int | None = None
    name: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience: str = ""
    portfolio: list[dict] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)
    is_active: bool = True

    @property
    def normalized_skills(self) -> list[str]:
        return [skill.strip() for skill in self.skills if skill and skill.strip()]
