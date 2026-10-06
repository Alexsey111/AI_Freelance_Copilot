"""Схемы профиля исполнителя (ТЗ §6)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    id: int
    name: str
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: str = ""
    portfolio: list[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    is_active: bool = True


class ProfileSkillsUpdate(BaseModel):
    """Правка навыков профиля (нужно, чтобы демонстрировать разные match score)."""

    skills: list[str] = Field(min_length=1, max_length=100)
