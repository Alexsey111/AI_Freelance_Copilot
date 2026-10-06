"""Состояние системы и активный профиль (нужны UI и приёмке)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_app_settings, get_llm_provider, get_session
from app.api.schemas.audit import HealthOut, ProviderOut
from app.api.schemas.profiles import ProfileOut, ProfileSkillsUpdate
from app.config import Settings
from app.infrastructure.database.repositories import ProfileRepository
from app.infrastructure.llm.base import PROMPT_VERSION

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut, summary="Проверка живости")
def health(
    request: Request,
    session=Depends(get_session),
    settings: Settings = Depends(get_app_settings),
):
    provider = get_llm_provider(request)
    name = getattr(provider, "name", "unknown")
    is_live = name != "mock"
    return HealthOut(
        status="ok",
        app_env=settings.app_env,
        database="sqlite" if settings.database_url.startswith("sqlite") else "external",
        api_version="v1",
        provider=ProviderOut(
            name=name,
            model=getattr(provider, "model", "unknown"),
            prompt_version=getattr(provider, "prompt_version", PROMPT_VERSION),
            is_live=is_live,
            warning=(
                "Активен реальный LLM-провайдер: запуск анализа тратит деньги."
                if is_live
                else "Активен mock-провайдер: сеть и деньги не используются."
            ),
        ),
    )


@router.get("/profiles", response_model=list[ProfileOut], summary="Профили исполнителя")
def list_profiles(session=Depends(get_session)):
    repository = ProfileRepository(session)
    repository.ensure_default()
    return [ProfileOut(**asdict(profile)) for profile in repository.list()]


@router.get("/profiles/active", response_model=ProfileOut, summary="Активный профиль")
def active_profile(session=Depends(get_session)):
    repository = ProfileRepository(session)
    profile = repository.get_active() or repository.ensure_default()
    return ProfileOut(**asdict(profile))


@router.post(
    "/profiles/{profile_id}/skills",
    response_model=ProfileOut,
    summary="Обновить навыки профиля",
    description="Нужно, чтобы показать на защите, как меняется match score при смене профиля.",
)
def update_skills(profile_id: int, payload: ProfileSkillsUpdate, session=Depends(get_session)):
    repository = ProfileRepository(session)
    profile = repository.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Профиль #{profile_id} не найден")
    updated = repository.update_skills(profile_id, payload.skills)
    return ProfileOut(**asdict(updated))
