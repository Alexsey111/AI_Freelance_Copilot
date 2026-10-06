"""Integration: Endpoint №3 --- ИИ-обработка, аудит, ручная проверка (ТЗ §11, §12, §32)."""

from __future__ import annotations

REQUIRED_KEYS = {
    "match_score",
    "recommendation",
    "reason",
    "matched_skills",
    "missing_skills",
    "draft_reply",
    "needs_review",
    "review_reason",
}


def _create(client, payload):
    return client.post("/api/v1/orders", json=payload).json()["id"]


def test_analyze_returns_strict_schema(client, sample_payload):
    order_id = _create(client, sample_payload)
    response = client.post(f"/api/v1/orders/{order_id}/analyze", json={})
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body["result"].keys()) >= REQUIRED_KEYS
    assert body["provider"] == "mock"
    assert isinstance(body["duration_ms"], int) and body["duration_ms"] >= 0
    assert body["audit_status"] in {"success", "review", "error"}
    assert body["result"]["recommendation"] in {"apply", "skip", "review"}


def test_analyze_good_order_recommends_apply(client, sample_payload):
    order_id = _create(client, sample_payload)
    result = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()["result"]
    assert result["needs_review"] is False
    assert result["review_reason"] is None
    assert result["recommendation"] == "apply"
    assert result["match_score"] is not None and 0 <= result["match_score"] <= 1
    assert result["draft_reply"]

    order = client.get(f"/api/v1/orders/{order_id}").json()
    assert order["status"] == "analyzed"
    assert order["needs_review"] is False


def test_analyze_vague_order_is_safe_and_needs_review(client, vague_payload):
    """ТЗ §13: система не выдумывает данные и не готовит отклик из ничего."""
    order_id = _create(client, vague_payload)
    body = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()
    result = body["result"]

    assert body["audit_status"] == "review"
    assert result["needs_review"] is True
    assert result["recommendation"] == "review"
    assert result["match_score"] is None
    assert result["draft_reply"] is None
    assert "бюджет" in result["review_reason"]

    order = client.get(f"/api/v1/orders/{order_id}").json()
    assert order["status"] == "needs_review"
    assert order["needs_review"] is True


def test_analyze_writes_audit_record(client, sample_payload):
    order_id = _create(client, sample_payload)
    body = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()

    audit = client.get("/api/v1/audit", params={"action": "analyze_order"}).json()
    assert audit["total"] >= 1
    record = audit["items"][0]
    assert record["status"] in {"success", "review", "error"}
    assert record["duration_ms"] is not None
    assert record["input"] and str(order_id) in record["input"]
    assert record["output"]
    assert record["order_id"] == order_id
    assert body["analysis_id"] is not None


def test_every_creation_is_audited(client, sample_payload):
    _create(client, sample_payload)
    audit = client.get("/api/v1/audit", params={"action": "create_order"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["status"] in {"success", "review"}


def test_invalid_json_from_llm_is_handled(client):
    """Особый тест ТЗ §32: LLM вернула невалидный JSON --- система не падает."""
    order_id = _create(
        client,
        {
            "title": "MOCK_BAD_JSON заказ",
            "description": "Описание достаточной длины, чтобы не сработало правило нехватки данных. " * 2,
            "budget_min": 10000,
            "budget_max": 20000,
        },
    )
    body = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()
    result = body["result"]

    assert body["audit_status"] == "review"
    assert result["needs_review"] is True
    assert result["match_score"] is None
    assert result["draft_reply"] is None
    assert "JSON" in result["review_reason"] or "json" in result["review_reason"]

    # Ошибка тоже попала в аудит (ТЗ §29.4).
    audit = client.get("/api/v1/audit", params={"action": "analyze_order"}).json()
    assert audit["items"][0]["status"] == "review"
    assert audit["items"][0]["error"]


def test_llm_timeout_marks_order_as_error_but_records_everything(client):
    order_id = _create(
        client,
        {
            "title": "MOCK_TIMEOUT заказ",
            "description": "Описание достаточной длины, стек Python. " * 3,
            "budget_min": 10000,
        },
    )
    body = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()
    assert body["audit_status"] == "error"
    assert body["order_status"] == "error"
    assert body["result"]["needs_review"] is True

    audit = client.get("/api/v1/audit", params={"action": "analyze_order"}).json()
    assert audit["items"][0]["status"] == "error"
    assert "timeout" in (audit["items"][0]["error"] or "").lower()


def test_analyze_unknown_order_returns_404_and_audits_error(client):
    response = client.post("/api/v1/orders/4242/analyze", json={})
    assert response.status_code == 404
    audit = client.get("/api/v1/audit", params={"action": "analyze_order"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["status"] == "error"


def test_repeated_analysis_keeps_history(client, sample_payload):
    order_id = _create(client, sample_payload)
    client.post(f"/api/v1/orders/{order_id}/analyze", json={})
    client.post(f"/api/v1/orders/{order_id}/analyze", json={})

    history = client.get(f"/api/v1/orders/{order_id}/analyses").json()
    assert len(history) == 2
    assert history[0]["prompt_version"] == "v1.0"
    assert history[0]["model"]

    latest = client.get(f"/api/v1/orders/{order_id}/analysis")
    assert latest.status_code == 200
    assert latest.json()["order_id"] == order_id
