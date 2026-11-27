"""Настройки правил через API — то, что читает и пишет окно программы.

Смысл: владелец системы меняет ставку, часы, цель недели и пороги в окне, а не в файле.
Поэтому у каждой настройки есть человеческое название, пояснение, единица измерения,
границы и источник текущего значения («настройка» / «окружение» / «по умолчанию»).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_app_settings, get_session
from app.api.schemas.settings import SettingOut, SettingUpdate
from app.domain.rules import RULES, format_value, label_of, validate
from app.infrastructure.database.repositories.settings_repository import SettingsRepository

router = APIRouter(prefix="/settings", tags=["settings"])

# Какие правила администратор мог задать переменными окружения при установке.
ENV_KEYS = {
    "min_rate_rub_per_hour": "min_rate_rub_per_hour",
    "available_hours_per_week": "available_hours_per_week",
    "target_week_rub": "target_week_rub",
    "budget_mode": "budget_mode",
    "aging_fresh_hours": "aging_fresh_hours",
    "aging_stale_hours": "aging_stale_hours",
    "aging_dead_hours": "aging_dead_hours",
    "review_queue_overdue_hours": "review_queue_overdue_hours",
    "competition_max_responses": "competition_max_responses",
    "competition_hard_responses": "competition_hard_responses",
    "llm_price_in_rub_per_1m": "llm_price_in_rub_per_1m",
    "llm_price_out_rub_per_1m": "llm_price_out_rub_per_1m",
}


def _env_values(settings) -> dict[str, str]:
    """Только то, что реально задано переменной окружения.

    Значения из кода — это заводские настройки, а не «окружение»: иначе после сброса
    настройка показывала бы источником окружение, хотя её никто не задавал.
    """
    values: dict[str, str] = {}
    for key, attr in ENV_KEYS.items():
        if key.upper() in os.environ:
            value = getattr(settings, attr, None)
            if value is not None:
                values[key] = str(value)
    return values


def _to_out(repository: SettingsRepository, settings) -> list[SettingOut]:
    resolved = repository.resolve(_env_values(settings))
    items: list[SettingOut] = []
    for key, rule in RULES.items():
        item = resolved[key]
        items.append(
            SettingOut(
                key=key,
                label=rule.label,
                help=rule.help,
                kind=rule.kind,
                value=item.raw,
                source=item.source,
                default=None if rule.default is None else str(rule.default),
                minimum=rule.minimum,
                maximum=rule.maximum,
                choices=list(rule.choices),
                unit=rule.unit,
            )
        )
    return items


@router.get("", response_model=list[SettingOut], summary="Правила работы")
def list_settings(
    session=Depends(get_session), settings=Depends(get_app_settings)
) -> list[SettingOut]:
    return _to_out(SettingsRepository(session), settings)


@router.put("/{key}", response_model=SettingOut, summary="Изменить правило")
def update_setting(
    key: str,
    payload: SettingUpdate,
    session=Depends(get_session),
    settings=Depends(get_app_settings),
) -> SettingOut:
    if key not in RULES:
        raise HTTPException(status_code=404, detail=f"Неизвестная настройка: {key}")
    try:
        value = validate(key, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repository = SettingsRepository(session)
    repository.set(key, format_value(value), changed_by=payload.changed_by)
    session.commit()
    return next(item for item in _to_out(repository, settings) if item.key == key)


@router.delete("/{key}", response_model=SettingOut, summary="Вернуть значение по умолчанию")
def reset_setting(
    key: str,
    session=Depends(get_session),
    settings=Depends(get_app_settings),
) -> SettingOut:
    if key not in RULES:
        raise HTTPException(status_code=404, detail=f"Неизвестная настройка: {key}")
    repository = SettingsRepository(session)
    repository.reset(key)
    session.commit()
    return next(item for item in _to_out(repository, settings) if item.key == key)


@router.get("/history", summary="История изменений правил")
def settings_history(
    key: str | None = None,
    limit: int = 50,
    session=Depends(get_session),
) -> list[dict]:
    repository = SettingsRepository(session)
    return [
        {
            "key": row.key,
            "label": label_of(row.key),
            "old_value": row.old_value,
            "new_value": row.new_value,
            "changed_at": row.changed_at,
            "changed_by": row.changed_by,
        }
        for row in repository.history(key, limit)
    ]
