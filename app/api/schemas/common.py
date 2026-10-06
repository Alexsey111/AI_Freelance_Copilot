"""Общие схемы ответов."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageMeta(BaseModel):
    total: int = Field(description="Всего записей, подходящих под фильтр")
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


class ErrorResponse(BaseModel):
    """Единый формат ошибки API."""

    detail: str
    code: str | None = None
