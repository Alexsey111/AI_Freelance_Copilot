"""Схемы API настроек: одно правило и его новое значение."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingOut(BaseModel):
    key: str
    label: str
    help: str
    kind: str
    value: str | None = None
    source: str
    default: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] = Field(default_factory=list)
    unit: str = ""


class SettingUpdate(BaseModel):
    value: str = Field(max_length=200, description="Новое значение в виде строки")
    changed_by: str = Field(default="user", max_length=64, description="Кто изменил")
