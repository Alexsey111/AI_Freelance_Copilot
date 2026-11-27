"""Прогоны: точка старта и точка отчёта (урок 2, «что изменилось между прогонами»).

Зачем это в API: решения принимаются пачкой (20 заказов за прогон), и без номера прогона
нельзя ответить ни «сколько ушло человеку в этом прогоне», ни «поведение изменилось
после смены промпта или это другой профиль». Прогон создаётся один раз, дальше его номер
передаётся заголовком `X-Run-Id` --- бизнес-логика анализа о прогоне не знает.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_session
from app.api.schemas.runs import RunOut, RunStartRequest, RunStartResponse
from app.domain.models.run import Run
from app.domain.usage import format_cost
from app.infrastructure.database.repositories.run_repository import RunRepository

router = APIRouter(prefix="/runs", tags=["runs"])


def _to_out(run: Run, audit_records: int = 0) -> RunOut:
    return RunOut(
        id=run.id or 0,
        kind=run.kind,
        status=run.status,
        model=run.model,
        prompt_version=run.prompt_version,
        profile_id=run.profile_id,
        orders_total=run.orders_total,
        orders_review=run.orders_review,
        review_share=run.review_share,
        audit_records=audit_records,
        tokens_in=run.tokens_in,
        tokens_out=run.tokens_out,
        latency_ms=run.latency_ms,
        cost_rub=run.cost_rub,
        cost_rub_text=format_cost(run.cost_rub),
        note=run.note,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _get_run_or_404(repository: RunRepository, run_id: int) -> Run:
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Прогон {run_id} не найден")
    return run


@router.post(
    "",
    response_model=RunStartResponse,
    status_code=201,
    summary="Начать прогон",
    description=(
        "Создаёт прогон и возвращает его номер. Все запросы анализа с заголовком "
        "X-Run-Id попадут в этот прогон; без заголовка решения пишутся с run_id = NULL."
    ),
)
def start_run(payload: RunStartRequest, session=Depends(get_session)) -> RunStartResponse:
    run = RunRepository(session).add(
        Run(
            kind=payload.kind,
            model=payload.model,
            prompt_version=payload.prompt_version,
            profile_id=payload.profile_id,
            note=payload.note,
        )
    )
    return RunStartResponse(run_id=run.id or 0)


@router.post(
    "/{run_id}/finish",
    response_model=RunOut,
    summary="Закрыть прогон",
    description=(
        "Ставит статус и фиксирует итог по фактическим записям: сколько решений "
        "получено в прогоне и сколько из них ушло человеку. Числа берутся из базы, "
        "а не из того, что сказал скрипт."
    ),
)
def finish_run(run_id: int, status: str = "done", session=Depends(get_session)) -> RunOut:
    repository = RunRepository(session)
    _get_run_or_404(repository, run_id)
    run = repository.close(run_id, status)
    if run is None:  # pragma: no cover - защита от гонки
        raise HTTPException(status_code=404, detail=f"Прогон {run_id} не найден")
    return _to_out(run, repository.count_audit(run_id))


@router.get("/{run_id}", response_model=RunOut, summary="Прогон: состояние и итог")
def get_run(run_id: int, session=Depends(get_session)) -> RunOut:
    repository = RunRepository(session)
    run = _get_run_or_404(repository, run_id)
    return _to_out(run, repository.count_audit(run_id))


@router.get("", response_model=list[RunOut], summary="Последние прогоны")
def list_runs(limit: int = 20, session=Depends(get_session)) -> list[RunOut]:
    repository = RunRepository(session)
    return [_to_out(run, repository.count_audit(run.id or 0)) for run in repository.list(limit)]
