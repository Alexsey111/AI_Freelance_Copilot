"""Точка входа FastAPI-приложения (модульный монолит, ТЗ §3.1).

Собирается фабрикой create_app(), поэтому тесты поднимают приложение с in-memory БД
и mock-провайдером, не трогая рабочую базу и не тратя деньги.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_v1
from app.api.schemas.common import ErrorResponse
from app.config import Settings, get_settings
from app.domain.models.analysis import AnalysisResult
from app.infrastructure.database.database import Database
from app.infrastructure.database.repositories import ProfileRepository
from app.infrastructure.llm.factory import build_llm_provider


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(settings: Settings | None = None, llm_provider=None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings.log_level)

    database = Database(settings.database_url, echo=settings.db_echo)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_all()
        with database.session() as session:
            ProfileRepository(session).ensure_default()
        yield
        database.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title=settings.app_name,
        version="0.1.0 (MVP)",
        description=(
            "MVP ядра системы автоматизации фриланса: заказы, ИИ-анализ соответствия профилю, "
            "ручная проверка сомнительных результатов, аудит. Реальные площадки и автоматическая "
            "отправка откликов в MVP не подключены (ТЗ §22), но интерфейсы OrderSource / LLMProvider "
            "/ ActionExecutor заложены под будущие этапы."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Схемы создаём сразу: SQLite-файл нужен и без запуска сервера (CLI-проверки, скрипты).
    database.create_all()
    app.state.database = database
    app.state.settings = settings
    app.state.llm_provider = llm_provider or build_llm_provider(settings)

    app.include_router(api_v1)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "app": settings.app_name,
            "docs": "/docs",
            "api": "/api/v1",
            "provider": getattr(app.state.llm_provider, "name", "unknown"),
        }

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):  # pragma: no cover
        logging.getLogger(__name__).exception("Необработанная ошибка: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(detail=f"Внутренняя ошибка: {type(exc).__name__}", code="internal_error").model_dump(),
        )

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


__all__ = ["app", "create_app", "AnalysisResult"]
