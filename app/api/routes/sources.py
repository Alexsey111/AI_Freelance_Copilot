"""Источники заказов через API: список площадок и сбор ленты по кнопке.

Нужно окну: пользователь не должен открывать терминал, чтобы обновить ленту. Ручной запуск
здесь обязателен намеренно — парсер ходит на чужой сайт, и делать это по расписанию без
ведома владельца невежливо.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_session
from app.infrastructure.database.repositories.order_repository import OrderRepository
from app.infrastructure.sources.fetch import SourceUnavailable
from app.infrastructure.sources.ingest import ingest_orders
from app.infrastructure.sources.parsing import parse_kwork
from app.infrastructure.sources.platform_sources import SOURCES, build_source

router = APIRouter(prefix="/sources", tags=["sources"])

TITLES = {"flru": "FL.ru", "freelance_ru": "Freelance.ru", "kwork": "Kwork"}


class SourceOut(BaseModel):
    key: str
    title: str
    hint: str


class RefreshIn(BaseModel):
    source: str = Field(default="all", description="flru | freelance_ru | kwork | all")
    pages: int = Field(default=1, ge=1, le=5)
    limit: int | None = Field(default=None, ge=1, le=300)


class RefreshItemOut(BaseModel):
    source: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    unchanged: int = 0
    available: bool = True
    reason: str | None = None


class IngestIn(BaseModel):
    source: str = Field(description="kwork: площадка отдаёт ленту только браузеру")
    cards: list[str] = Field(min_length=1, description="HTML карточек после отрисовки")


class RefreshOut(BaseModel):
    items: list[RefreshItemOut]

    @property
    def created(self) -> int:
        return sum(item.created for item in self.items)


RENDERED = {"kwork"}  # площадки, которые нельзя разобрать из ответа сервера


HINTS = {
    "flru": "открытая лента, есть просмотры и число ответов",
    "freelance_ru": "открытая лента, есть точное время публикации",
    "kwork": "ленту дорисовывает браузер: окно открывает её само, из ответа сервера проектов не видно",
}


@router.get("", response_model=list[SourceOut], summary="Доступные источники заказов")
def list_sources() -> list[SourceOut]:
    return [
        SourceOut(key=key, title=TITLES.get(key, key), hint=HINTS.get(key, "")) for key in SOURCES
    ]


@router.post("/refresh", response_model=RefreshOut, summary="Собрать ленту с площадок")
async def refresh(payload: RefreshIn, session=Depends(get_session)) -> RefreshOut:
    keys = (
        [key for key in SOURCES if key not in RENDERED]
        if payload.source == "all"
        else [payload.source]
    )
    if payload.source in RENDERED:
        raise HTTPException(
            status_code=409,
            detail="Kwork отдаёт ленту только браузеру: окно программы собирает карточки и присылает их сюда",
        )
    unknown = [key for key in keys if key not in SOURCES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Неизвестный источник: {', '.join(unknown)}")

    items: list[RefreshItemOut] = []
    for key in keys:
        source = build_source(key, pages=payload.pages, limit=payload.limit)
        try:
            orders = await source.fetch_orders()
        except SourceUnavailable as error:
            items.append(RefreshItemOut(source=key, available=False, reason=str(error)))
            continue
        stats = await asyncio.to_thread(ingest_orders, orders, OrderRepository(session))
        session.commit()
        items.append(
            RefreshItemOut(
                source=key,
                fetched=stats.fetched,
                created=stats.created,
                updated=stats.updated,
                skipped=stats.skipped,
                unchanged=stats.unchanged,
            )
        )
    return RefreshOut(items=items)


@router.post("/ingest", response_model=RefreshItemOut, summary="Принять карточки, снятые браузером")
async def ingest_rendered(payload: IngestIn, session=Depends(get_session)) -> RefreshItemOut:
    """Разбор остаётся на сервере: браузер только снимает разметку, решает здесь Python."""
    if payload.source not in RENDERED:
        raise HTTPException(
            status_code=422, detail=f"{payload.source} разбирается напрямую, без браузера"
        )
    orders = parse_kwork(payload.cards)
    if not orders:
        return RefreshItemOut(
            source=payload.source,
            available=False,
            reason="в присланных карточках нет ни одного заказа",
        )
    stats = await asyncio.to_thread(ingest_orders, orders, OrderRepository(session))
    session.commit()
    return RefreshItemOut(
        source=payload.source,
        fetched=stats.fetched,
        created=stats.created,
        updated=stats.updated,
        skipped=stats.skipped,
        unchanged=stats.unchanged,
    )
