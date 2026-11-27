"""Нормы времени по типам задач и загрузка недели.

Два окна программы смотрят сюда: «Сколько я трачу на задачу» (нормы, правятся руками)
и «Распределение времени» (сколько часов недели уже занято и на что). Оценка часов
для конкретного заказа берётся из нормы по ключевым словам и всегда объясняется —
без «модель решила».
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import get_app_settings, get_session
from app.domain.skills_catalog import all_skills, catalog
from app.domain.time_norms import guess_norm, workload
from app.infrastructure.database.models import OrderModel
from app.infrastructure.database.repositories.settings_repository import SettingsRepository
from app.infrastructure.database.repositories.time_norm_repository import TimeNormRepository

router = APIRouter(prefix="/time-norms", tags=["time-norms"])


class TimeNormOut(BaseModel):
    task_kind: str
    title: str
    hours: float
    keywords: list[str] = Field(default_factory=list)
    note: str | None = None


class TimeNormUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    hours: float = Field(gt=0, le=1000, description="Часов на одну задачу этого типа")
    keywords: list[str] | None = Field(default=None, max_length=50)


class EstimateIn(BaseModel):
    title: str = Field(max_length=500)
    description: str = ""


class EstimateOut(BaseModel):
    task_kind: str | None = None
    title: str | None = None
    hours: float | None = None
    reason: str


class WorkloadRowOut(BaseModel):
    task_kind: str
    title: str
    orders: int
    hours: float
    money: float


class WorkloadOut(BaseModel):
    capacity_hours: float
    booked_hours: float
    free_hours: float
    load_share: float
    money: float
    orders: int
    rows: list[WorkloadRowOut]


def _to_out(norm) -> TimeNormOut:
    """Нормы — dataclass со slots: `__dict__` у них нет, поля перечисляем явно."""
    return TimeNormOut(
        task_kind=norm.task_kind,
        title=norm.title,
        hours=norm.hours,
        keywords=list(norm.keywords),
        note=norm.note,
    )


def _effective_capacity(session, settings) -> float:
    resolved = SettingsRepository(session).resolve({})
    raw = resolved["available_hours_per_week"].raw
    try:
        return float(raw) if raw else settings.available_hours_per_week
    except ValueError:
        return settings.available_hours_per_week


@router.get("/skills-catalog", summary="Справочник навыков по профессиям")
def skills_catalog(q: str | None = None) -> dict:
    """Подсказки для профиля: у копирайтера, дизайнера и переводчика свой набор.

    Справочник не ограничивает: свои навыки добавляются свободным текстом.
    """
    return {"professions": catalog(q), "total": len(all_skills())}


@router.get("", response_model=list[TimeNormOut], summary="Нормы времени по типам задач")
def list_norms(session=Depends(get_session)) -> list[TimeNormOut]:
    repository = TimeNormRepository(session)
    return [_to_out(norm) for norm in repository.ensure_seeded()]


@router.put("/{task_kind}", response_model=TimeNormOut, summary="Изменить норму времени")
def upsert_norm(
    task_kind: str, payload: TimeNormUpdate, session=Depends(get_session)
) -> TimeNormOut:
    repository = TimeNormRepository(session)
    existing = {norm.task_kind: norm for norm in repository.ensure_seeded()}.get(task_kind)
    title = payload.title or (existing.title if existing else task_kind)
    keywords = payload.keywords if payload.keywords is not None else (existing.keywords if existing else [])
    norm = repository.upsert(task_kind, title=title, hours=payload.hours, keywords=keywords)
    session.commit()
    return _to_out(norm)


@router.delete("/{task_kind}", summary="Удалить норму")
def delete_norm(task_kind: str, session=Depends(get_session)) -> dict:
    repository = TimeNormRepository(session)
    if not repository.delete(task_kind):
        raise HTTPException(status_code=404, detail=f"Норма «{task_kind}» не найдена")
    session.commit()
    return {"deleted": task_kind}


@router.post("/estimate", response_model=EstimateOut, summary="Сколько часов займёт заказ")
def estimate(payload: EstimateIn, session=Depends(get_session)) -> EstimateOut:
    norms = TimeNormRepository(session).ensure_seeded()
    guess = guess_norm(payload.title, payload.description, norms)
    return EstimateOut(
        task_kind=guess.norm.task_kind if guess.norm else None,
        title=guess.norm.title if guess.norm else None,
        hours=guess.hours,
        reason=guess.reason,
    )


@router.get("/workload", response_model=WorkloadOut, summary="Распределение времени недели")
def week_workload(
    session=Depends(get_session), settings=Depends(get_app_settings)
) -> WorkloadOut:
    """Часы по типам задач по заказам, взятым в работу (approved)."""
    norms = TimeNormRepository(session).ensure_seeded()
    rows = session.execute(
        select(OrderModel).where(OrderModel.status == "approved")
    ).scalars().all()

    items: list[dict] = []
    for row in rows:
        guess = guess_norm(row.title or "", row.description or "", norms)
        kind = guess.norm.task_kind if guess.norm else None
        title = guess.norm.title if guess.norm else "Не оценено"
        order = row.title or ""
        hours = row.estimated_hours
        if hours is None:
            hours = guess.hours
        items.append(
            {
                "task_kind": kind,
                "title": f"{title} · {order[:40]}",
                "hours": hours or 0.0,
                "money": float(row.budget_min or row.budget_max or 0.0),
            }
        )

    load = workload(items, capacity_hours=_effective_capacity(session, settings))
    return WorkloadOut(
        capacity_hours=load.capacity_hours,
        booked_hours=load.booked_hours,
        free_hours=load.free_hours,
        load_share=load.load_share,
        money=load.money,
        orders=load.orders,
        rows=[
            WorkloadRowOut(
                task_kind=row.task_kind,
                title=row.title,
                orders=row.orders,
                hours=row.hours,
                money=row.money,
            )
            for row in load.rows
        ],
    )
