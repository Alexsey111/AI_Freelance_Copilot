"""Источники заказов с площадок: FL.ru, Freelance.ru, Kwork.

Каждый источник умеет одно: отдать список ExternalOrder. Разбор лежит в parsing.py и
проверяется на сохранённых страницах, поэтому сломанная разметка видна в тестах, а не в
боевом прогоне.
"""

from __future__ import annotations

import asyncio

from app.infrastructure.sources.base import ExternalOrder
from app.infrastructure.sources.fetch import SourceUnavailable, fetch_html, polite_pause
from app.infrastructure.sources.parsing import parse_flru, parse_freelance_ru

FLRU_LIST = "https://www.fl.ru/projects/?page={page}"
FREELANCE_RU_LIST = "https://freelance.ru/project/search?page={page}"
KWORK_LIST = "https://kwork.ru/projects"


class FlruSource:
    """FL.ru: открытая лента, до 60 карточек на страницу, есть просмотры и число ответов."""

    name = "flru"
    title = "FL.ru"

    def __init__(self, *, pages: int = 1, delay: float = 1.5, limit: int | None = None) -> None:
        self.pages = max(1, pages)
        self.delay = delay
        self.limit = limit

    async def fetch_orders(self) -> list[ExternalOrder]:
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> list[ExternalOrder]:
        collected: list[ExternalOrder] = []
        for page in range(1, self.pages + 1):
            html = fetch_html(FLRU_LIST.format(page=page))
            orders = parse_flru(html)
            if not orders:
                raise SourceUnavailable(
                    "FL.ru: на странице не нашлось ни одной карточки заказа — "
                    "либо изменилась разметка, либо площадка отдала заглушку"
                )
            collected.extend(orders)
            if self.limit is not None and len(collected) >= self.limit:
                break
            if page < self.pages:
                polite_pause(self.delay)
        return collected[: self.limit] if self.limit else collected


class FreelanceRuSource:
    """Freelance.ru: открытая лента, точное время публикации в подсказке к возрасту."""

    name = "freelance_ru"
    title = "Freelance.ru"

    def __init__(self, *, pages: int = 1, delay: float = 1.5, limit: int | None = None) -> None:
        self.pages = max(1, pages)
        self.delay = delay
        self.limit = limit

    async def fetch_orders(self) -> list[ExternalOrder]:
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> list[ExternalOrder]:
        collected: list[ExternalOrder] = []
        for page in range(1, self.pages + 1):
            html = fetch_html(FREELANCE_RU_LIST.format(page=page))
            orders = parse_freelance_ru(html)
            if not orders:
                raise SourceUnavailable(
                    "Freelance.ru: на странице не нашлось ни одной карточки задания — "
                    "либо изменилась разметка, либо площадка отдала заглушку"
                )
            collected.extend(orders)
            if self.limit is not None and len(collected) >= self.limit:
                break
            if page < self.pages:
                polite_pause(self.delay)
        return collected[: self.limit] if self.limit else collected


class KworkSource:
    """Kwork: лента существует только в браузере.

    Проверено 27.11.2026: страница /projects приходит размером 280 КБ без единой карточки —
    проекты дорисовывает JS. Поэтому запрос за лентой смысла не имеет, а разбор делает окно
    программы: оно открывает страницу, снимает разметку карточек и отправляет её в
    `/api/v1/sources/ingest`. Здесь остаётся честный отказ вместо тихого нуля.
    """

    name = "kwork"
    title = "Kwork"

    def __init__(self, *, pages: int = 1, delay: float = 1.5, limit: int | None = None) -> None:
        self.pages = pages
        self.delay = delay
        self.limit = limit

    async def fetch_orders(self) -> list[ExternalOrder]:
        raise SourceUnavailable(
            "Kwork: ленту дорисовывает браузер — из ответа сервера проектов не видно. "
            "Окно программы снимает карточки и присылает их в /api/v1/sources/ingest."
        )


SOURCES = {
    FlruSource.name: FlruSource,
    FreelanceRuSource.name: FreelanceRuSource,
    KworkSource.name: KworkSource,
}


def build_source(key: str, *, pages: int = 1, limit: int | None = None, delay: float = 1.5):
    factory = SOURCES.get(key)
    if factory is None:
        raise KeyError(f"Неизвестный источник «{key}»: доступны {', '.join(SOURCES)}")
    return factory(pages=pages, limit=limit, delay=delay)
