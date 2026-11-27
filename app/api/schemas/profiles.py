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


class ProfileUpdate(BaseModel):
    """Правка профиля целиком: кто я, за что берусь и на каких условиях.

    Без этого окно программы не может собрать профиль, а без профиля непонятно,
    по какому признаку система отбирает заказы.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=4000)
    skills: list[str] | None = Field(default=None, max_length=100)
    experience: str | None = Field(default=None, max_length=8000)
    portfolio: list[dict] | None = Field(default=None, max_length=50)
    preferences: dict | None = None


class ProfileSkillsUpdate(BaseModel):
    """Правка навыков профиля (нужно, чтобы демонстрировать разные match score)."""

    skills: list[str] = Field(min_length=1, max_length=100)
