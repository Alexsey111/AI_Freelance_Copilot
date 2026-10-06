"""Схемы API заказов (ТЗ §9, §10)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.analysis import AnalysisSummaryOut


class OrderCreate(BaseModel):
    """Тело запроса POST /api/v1/orders (ТЗ §9)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=500, description="Название заказа")
    description: str = Field(default="", max_length=20000)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    currency: str = Field(default="RUB", max_length=8)
    url: str | None = Field(default=None, max_length=1000)
    client_name: str | None = Field(default=None, max_length=255)
    source: str = Field(default="manual", max_length=32)
    external_id: str | None = Field(default=None, max_length=128)
    raw_input: dict | None = None

    @field_validator("budget_max")
    @classmethod
    def _budget_order(cls, value: float | None, info) -> float | None:
        minimum = info.data.get("budget_min")
        if value is not None and minimum is not None and value < minimum:
            raise ValueError("budget_max не может быть меньше budget_min")
        return value


class OrderCreateResponse(BaseModel):
    """Ответ POST /api/v1/orders (ТЗ §9): id + status."""

    id: int
    status: str
    needs_review: bool = False
    created_at: datetime | None = None


class OrderOut(BaseModel):
    """Заказ в витрине (ТЗ §23)."""

    id: int
    external_id: str | None = None
    source: str
    title: str
    description: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "RUB"
    url: str | None = None
    client_name: str | None = None
    status: str
    needs_review: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    latest_analysis: AnalysisSummaryOut | None = None


class OrderDetailOut(OrderOut):
    """Карточка заказа: + сырой ввод (ТЗ §24)."""

    raw_input: dict | None = None


class OrderListResponse(BaseModel):
    """Ответ GET /api/v1/orders (ТЗ §10)."""

    items: list[OrderOut]
    total: int
    page: int
    page_size: int
