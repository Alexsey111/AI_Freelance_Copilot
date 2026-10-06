"""Сборка всех роутов API в один v1-роутер."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import analysis, audit, health, orders, review

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(orders.router)
api_v1.include_router(analysis.router)
api_v1.include_router(review.router)
api_v1.include_router(audit.router)
api_v1.include_router(health.router)
