"""Журнал откликов: запись факта, воронка и цена одного найма.

Здесь нет и не будет кнопки «разослать отклики по всем заказам»: на биржах автоматическая
отправка запрещена правилами, а плата за отклик делает массовую рассылку убыточной.
Задача этого модуля — считать, во что обходится каждая попытка, чтобы решение «откликаться
или нет» принималось по деньгам.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import get_session
from app.domain.models.order import OrderStatus
from app.domain.responses import LABELS, STATUSES, funnel
from app.infrastructure.database.models import OrderModel, ResponseModel

router = APIRouter(prefix="/responses", tags=["responses"])


class ResponseIn(BaseModel):
    order_id: int
    platform: str = Field(default="manual", max_length=32)
    cost_rub: float | None = Field(default=None, ge=0, description="Сколько стоил отклик")
    status: str = Field(default="sent", description="sent | replied | hired | declined | silent")
    note: str | None = Field(default=None, max_length=500)


class ResponseOut(BaseModel):
    id: int
    order_id: int
    order_title: str
    platform: str
    sent_at: datetime
    cost_rub: float | None = None
    status: str
    status_label: str
    note: str | None = None


class FunnelOut(BaseModel):
    sent: int
    replied: int
    hired: int
    declined: int
    silent: int
    cost: float
    hired_money: float
    reply_rate: float | None = None
    hire_rate: float | None = None
    cost_per_hire: float | None = None
    cost_per_sent: float | None = None


def _to_out(row: ResponseModel, title: str) -> ResponseOut:
    return ResponseOut(
        id=row.id,
        order_id=row.order_id,
        order_title=title,
        platform=row.platform,
        sent_at=row.sent_at,
        cost_rub=row.cost_rub,
        status=row.status,
        status_label=LABELS.get(row.status, row.status),
        note=row.note,
    )


@router.get("", response_model=list[ResponseOut], summary="Журнал откликов")
def list_responses(session=Depends(get_session), limit: int = 100) -> list[ResponseOut]:
    rows = (
        session.execute(select(ResponseModel).order_by(ResponseModel.id.desc()).limit(limit))
        .scalars()
        .all()
    )
    titles = (
        {
            row.id: row.title
            for row in session.execute(
                select(OrderModel).where(OrderModel.id.in_([r.order_id for r in rows]))
            ).scalars()
        }
        if rows
        else {}
    )
    return [_to_out(row, titles.get(row.order_id, "(заказ удалён)")) for row in rows]


@router.post("", response_model=ResponseOut, summary="Записать отправленный отклик")
def add_response(payload: ResponseIn, session=Depends(get_session)) -> ResponseOut:
    if payload.status not in STATUSES:
        raise HTTPException(
            status_code=422, detail=f"Недопустимый статус: допустимо {', '.join(STATUSES)}"
        )
    order = session.get(OrderModel, payload.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Заказ #{payload.order_id} не найден")
    row = ResponseModel(
        order_id=payload.order_id,
        platform=payload.platform,
        sent_at=datetime.now(UTC),
        cost_rub=payload.cost_rub,
        status=payload.status,
        note=payload.note,
    )
    session.add(row)
    if payload.status == "hired":
        order.status = OrderStatus.APPROVED.value
    session.commit()
    session.refresh(row)
    return _to_out(row, order.title)


@router.patch("/{response_id}", response_model=ResponseOut, summary="Обновить статус отклика")
def update_response(response_id: int, payload: dict, session=Depends(get_session)) -> ResponseOut:
    row = session.get(ResponseModel, response_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Отклик #{response_id} не найден")
    status = str(payload.get("status", row.status))
    if status not in STATUSES:
        raise HTTPException(
            status_code=422, detail=f"Недопустимый статус: допустимо {', '.join(STATUSES)}"
        )
    row.status = status
    if "cost_rub" in payload and payload["cost_rub"] is not None:
        row.cost_rub = float(payload["cost_rub"])
    session.commit()
    session.refresh(row)
    order = session.get(OrderModel, row.order_id)
    return _to_out(row, order.title if order else "(заказ удалён)")


@router.get("/funnel", response_model=FunnelOut, summary="Воронка: цена одного найма")
def responses_funnel(session=Depends(get_session)) -> FunnelOut:
    rows = session.execute(select(ResponseModel)).scalars().all()
    money = {
        order.id: float(order.budget_min or order.budget_max or 0.0)
        for order in session.execute(select(OrderModel)).scalars()
    }
    stats = funnel(
        [
            {"status": row.status, "cost_rub": row.cost_rub, "money": money.get(row.order_id, 0.0)}
            for row in rows
        ]
    )
    return FunnelOut(
        sent=stats.sent,
        replied=stats.replied,
        hired=stats.hired,
        declined=stats.declined,
        silent=stats.silent,
        cost=round(stats.cost, 2),
        hired_money=round(stats.hired_money, 2),
        reply_rate=stats.reply_rate,
        hire_rate=stats.hire_rate,
        cost_per_hire=stats.cost_per_hire,
        cost_per_sent=stats.cost_per_sent,
    )
