"""Endpoint №3: ИИ-обработка заказа (ТЗ §11, §12).

Ответ содержит строго структурированный result, а также служебные поля
(analysis_id, duration_ms, provider, audit_status), чтобы UI показывал не только
"что сказала модель", но и "что система с этим сделала".
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_analysis_service
from app.api.schemas.analysis import (
    AnalysisOut,
    AnalysisResultOut,
    AnalyzeRequest,
    AnalyzeResponse,
)
from app.domain.services.analysis_service import AnalysisService

router = APIRouter(prefix="/orders", tags=["analysis"])


@router.post(
    "/{order_id}/analyze",
    response_model=AnalyzeResponse,
    summary="Точка 3: ИИ-обработка заказа",
    description=(
        "Запускает анализ заказа относительно профиля исполнителя. Ответ строго по схеме "
        "AnalysisResult. При нехватке данных, невалидном ответе модели или её ошибке "
        "возвращается безопасный результат с needs_review=true и причиной."
    ),
)
async def analyze_order(
    order_id: int,
    payload: AnalyzeRequest | None = None,
    service: AnalysisService = Depends(get_analysis_service),
):
    request_payload = payload or AnalyzeRequest()
    try:
        outcome = await service.analyze_order(order_id, request_payload.profile_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnalyzeResponse(
        order_id=order_id,
        order_status=outcome.order.status,
        analysis_id=outcome.analysis.id,
        duration_ms=outcome.duration_ms,
        provider=outcome.provider,
        model=outcome.model,
        audit_status=outcome.audit_status,
        result=AnalysisResultOut.from_domain(outcome.result),
    )


@router.get(
    "/{order_id}/analysis",
    response_model=AnalysisOut | None,
    summary="Последний анализ заказа",
    description="Последний результат анализа: match score, рекомендация, черновик отклика, review, сырой вывод модели.",
)
def latest_analysis(order_id: int, service: AnalysisService = Depends(get_analysis_service)):
    analysis = service.analyses.latest_for_order(order_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"По заказу #{order_id} анализов ещё не было",
        )
    return AnalysisOut(**asdict(analysis))
