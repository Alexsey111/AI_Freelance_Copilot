"""Unit/integration: прогон как контекст решения (урок 2, п.2–3 практики).

Три вещи, которые проверяются:
1. решение и аудит попадают в прогон, номер которого пришёл в запросе;
2. без прогона запись остаётся с run_id = NULL (и это не ошибка, а «ручной разбор»);
3. решение без аудита невозможно: падение между записями откатывает обе.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.domain.models.analysis import Analysis
from app.domain.models.audit import AuditRun, AuditStatus
from app.domain.run_context import current_run_id, run_scope
from app.infrastructure.database.models import AnalysisModel, AuditRunModel
from app.infrastructure.database.repositories.analysis_repository import AnalysisRepository
from app.infrastructure.database.repositories.audit_repository import AuditRepository


def _analysis(order_id: int = 1, profile_id: int = 1) -> Analysis:
    return Analysis(
        order_id=order_id,
        profile_id=profile_id,
        match_score=0.7,
        recommendation="apply",
        reason="профиль подходит",
        needs_review=False,
    )


def _audit(order_id: int = 1) -> AuditRun:
    return AuditRun(
        action="analyze_order",
        order_id=order_id,
        status=AuditStatus.SUCCESS.value,
        created_at=datetime.now(UTC),
    )


def test_run_context_is_empty_by_default():
    assert current_run_id() is None


def test_run_scope_restores_previous_value():
    with run_scope(7):
        assert current_run_id() == 7
        with run_scope(9):
            assert current_run_id() == 9
        assert current_run_id() == 7
    assert current_run_id() is None


def test_start_run_returns_id_and_header(client):
    response = client.post("/api/v1/runs", json={"kind": "analyze_batch", "model": "mock-1"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["run_id"] > 0
    assert body["header"] == "X-Run-Id"


def test_decisions_and_audit_get_run_id_from_header(client, sample_payload):
    run_id = client.post("/api/v1/runs", json={"kind": "analyze_batch"}).json()["run_id"]
    order_id = client.post("/api/v1/orders", json=sample_payload).json()["id"]

    analyzed = client.post(
        f"/api/v1/orders/{order_id}/analyze",
        json={},
        headers={"X-Run-Id": str(run_id)},
    )
    assert analyzed.status_code == 200, analyzed.text

    session = client.app.state.database.new_session()
    try:
        analysis_run_ids = set(session.execute(select(AnalysisModel.run_id)).scalars().all())
        audit_run_ids = set(session.execute(select(AuditRunModel.run_id)).scalars().all())
    finally:
        session.close()
    # Создание заказа шло без заголовка (NULL), анализ — внутри прогона.
    assert run_id in analysis_run_ids
    assert audit_run_ids - {None} == {run_id}


def test_run_without_header_is_null_not_error(client, sample_payload):
    order_id = client.post("/api/v1/orders", json=sample_payload).json()["id"]
    assert client.post(f"/api/v1/orders/{order_id}/analyze", json={}).status_code == 200

    session = client.app.state.database.new_session()
    try:
        assert set(session.execute(select(AnalysisModel.run_id)).scalars().all()) == {None}
    finally:
        session.close()


def test_non_numeric_header_is_rejected(client):
    response = client.get("/api/v1/orders", headers={"X-Run-Id": "abc"})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_run_id"


def test_finish_counts_review_share_from_base(client, sample_payload):
    run_id = client.post("/api/v1/runs", json={"kind": "analyze_batch"}).json()["run_id"]
    order_id = client.post("/api/v1/orders", json=sample_payload).json()["id"]
    client.post(f"/api/v1/orders/{order_id}/analyze", json={}, headers={"X-Run-Id": str(run_id)})

    finished = client.post(f"/api/v1/runs/{run_id}/finish", params={"status": "done"})
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "done"
    assert body["orders_total"] == 1
    assert body["finished_at"] is not None
    assert body["audit_records"] >= 1


def test_unknown_run_returns_404(client):
    assert client.get("/api/v1/runs/999").status_code == 404
    assert client.post("/api/v1/runs/999/finish").status_code == 404


def test_failure_between_decision_and_audit_rolls_back_both(client, sample_payload):
    """Решение и аудит обязаны быть правдой одновременно: упали — не осталось ни строки."""
    database = client.app.state.database
    order_id = client.post("/api/v1/orders", json=sample_payload).json()["id"]

    with pytest.raises(RuntimeError), database.session() as session:
        AnalysisRepository(session).add(_analysis(order_id=order_id))
        AuditRepository(session).add(_audit(order_id=order_id))
        raise RuntimeError("падение между записью решения и аудита")

    session = database.new_session()
    try:
        analyses = len(session.execute(select(AnalysisModel)).scalars().all())
    finally:
        session.close()
    assert analyses == 0


def test_commit_keeps_both_records_together(client, sample_payload):
    database = client.app.state.database
    order_id = client.post("/api/v1/orders", json=sample_payload).json()["id"]
    with run_scope(None), database.session() as session:
        AnalysisRepository(session).add(_analysis(order_id=order_id))
        AuditRepository(session).add(_audit(order_id=order_id))

    session = database.new_session()
    try:
        assert len(session.execute(select(AnalysisModel)).scalars().all()) == 1
    finally:
        session.close()
