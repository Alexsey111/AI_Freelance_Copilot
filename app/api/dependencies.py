"""Сборка зависимостей FastAPI (Dependency Injection).

Роуты не создают сервисы сами --- они получают их отсюда. Поэтому подмена БД
(тестовая in-memory SQLite) или провайдера (mock вместо реального) делается в одном месте.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.domain.services.analysis_service import AnalysisService
from app.domain.services.audit_service import AuditService
from app.domain.services.metrics_service import MetricsService
from app.domain.services.order_service import OrderService
from app.domain.services.review_service import ReviewService
from app.infrastructure.database.database import Database
from app.infrastructure.database.repositories import (
    AnalysisRepository,
    AuditRepository,
    OrderRepository,
    ProfileRepository,
)


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_llm_provider(request: Request):
    return request.app.state.llm_provider


def get_app_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def get_session(request: Request) -> Iterator:
    """Сессия БД на один запрос. Сервисы ниже живут внутри неё.

    Важная деталь: при HTTPException (валидация, 404) сессия ФИКСИРУЕТСЯ, а не
    откатывается. Иначе запись аудита о неудачном запуске исчезала бы вместе с откатом,
    а ТЗ §29.4 требует обратного: даже упавший запуск должен остаться в журнале.
    Настоящие внутренние ошибки по-прежнему откатываются.
    """
    database: Database = request.app.state.database
    session = database.new_session()
    try:
        yield session
        session.commit()
    except HTTPException:
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_order_service(
    session=Depends(get_session), settings: Settings = Depends(get_app_settings)
) -> OrderService:
    return OrderService(
        OrderRepository(session),
        AuditService(AuditRepository(session)),
        settings,
        analysis_repository=AnalysisRepository(session),
    )


def get_analysis_service(
    request: Request,
    session=Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AnalysisService:
    return AnalysisService(
        order_repository=OrderRepository(session),
        profile_repository=ProfileRepository(session),
        analysis_repository=AnalysisRepository(session),
        audit_service=AuditService(AuditRepository(session)),
        llm_provider=request.app.state.llm_provider,
        settings=settings,
    )


def get_review_service(session=Depends(get_session)) -> ReviewService:
    return ReviewService(
        AnalysisRepository(session), OrderRepository(session), AuditService(AuditRepository(session))
    )


def get_metrics_service(session=Depends(get_session)) -> MetricsService:
    return MetricsService(OrderRepository(session), AnalysisRepository(session), AuditRepository(session))
