"""Integration: ручная проверка (ТЗ §25), аудит (ТЗ §26), метрики и экономика (ТЗ §33, §34)."""

from __future__ import annotations


def _create(client, payload):
    return client.post("/api/v1/orders", json=payload).json()["id"]


def _analyze(client, order_id):
    return client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()


def test_review_queue_contains_only_uncertain_results(client, sample_payload, vague_payload):
    good_id = _create(client, sample_payload)
    bad_id = _create(client, vague_payload)
    _analyze(client, good_id)
    _analyze(client, bad_id)

    queue = client.get("/api/v1/review-queue").json()
    assert queue["total"] == 1
    item = queue["items"][0]
    assert item["order_id"] == bad_id
    assert item["review_status"] == "pending"
    assert item["review_reason"]


def test_human_approval_updates_order_and_audits(client, vague_payload):
    order_id = _create(client, vague_payload)
    analysis_id = _analyze(client, order_id)["analysis_id"]

    decision = client.post(
        f"/api/v1/analyses/{analysis_id}/review",
        json={"decision": "approved", "comment": "Проверил: заказ берём"},
    )
    assert decision.status_code == 200, decision.text
    body = decision.json()
    assert body["review_status"] == "approved"
    assert body["order_status"] == "approved"

    order = client.get(f"/api/v1/orders/{order_id}").json()
    assert order["status"] == "approved"
    assert order["needs_review"] is False

    queue = client.get("/api/v1/review-queue", params={"review_status": "approved"}).json()
    assert queue["total"] == 1

    audit = client.get("/api/v1/audit", params={"action": "review_decision"}).json()
    assert audit["total"] == 1
    assert "не выполняются" in audit["items"][0]["output"]


def test_human_rejection(client, vague_payload):
    order_id = _create(client, vague_payload)
    analysis_id = _analyze(client, order_id)["analysis_id"]
    body = client.post(
        f"/api/v1/analyses/{analysis_id}/review", json={"decision": "rejected"}
    ).json()
    assert body["review_status"] == "rejected"
    assert body["order_status"] == "rejected"


def test_invalid_decision_is_rejected(client, vague_payload):
    order_id = _create(client, vague_payload)
    analysis_id = _analyze(client, order_id)["analysis_id"]
    response = client.post(
        f"/api/v1/analyses/{analysis_id}/review", json={"decision": "может быть"}
    )
    assert response.status_code == 422


def test_metrics_on_empty_database_report_no_data(client):
    """Ключевое: метрика на пустом входе --- 'нет данных' (null), а не ноль."""
    metrics = client.get("/api/v1/metrics").json()
    assert metrics["analyses_total"] == 0
    assert metrics["json_valid_rate"] is None
    assert metrics["review_share"] is None
    assert metrics["apply_share"] is None
    assert metrics["avg_match_score"] is None
    assert metrics["avg_analyze_duration_ms"] is None

    # Экономика --- оценка, поэтому считается и на пустой базе. Рабочее значение --- замер
    # владельца (8 мин вручную), а разбивка ТЗ §33 (13 мин) видна отдельно для сравнения.
    economy = metrics["economy"]
    assert economy["manual_order_minutes"] == 8
    assert economy["manual_order_minutes_spec"] == 13
    assert economy["saved_hours_per_100"] == 8.33
    assert economy["saved_hours_per_100"] < economy["saved_minutes_per_100_spec"] / 60


def test_metrics_after_work(client, sample_payload, vague_payload):
    good_id = _create(client, sample_payload)
    bad_id = _create(client, vague_payload)
    _analyze(client, good_id)
    _analyze(client, bad_id)

    metrics = client.get("/api/v1/metrics").json()
    assert metrics["orders_total"] == 2
    assert metrics["analyses_total"] == 2
    assert metrics["analyses_needs_review"] == 1
    assert metrics["analyses_errors"] == 0
    assert metrics["json_valid_rate"] == 1.0
    assert metrics["review_share"] == 0.5
    assert metrics["apply_share"] == 0.5
    assert metrics["audit_total"] >= 4
    assert metrics["avg_analyze_duration_ms"] is not None
    assert metrics["economy"]["saved_money_rub_per_100"] > 0


def test_audit_actions_summary(client, sample_payload):
    order_id = _create(client, sample_payload)
    _analyze(client, order_id)
    summary = client.get("/api/v1/audit/actions").json()
    assert summary["actions"]["create_order"] == 1
    assert summary["actions"]["analyze_order"] == 1
    assert summary["statuses"]["review"] >= 0
    assert summary["total"] == 2


def test_health_and_profile(client):
    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok"
    assert health["provider"]["name"] == "mock"
    assert health["provider"]["is_live"] is False
    assert health["provider"]["prompt_version"] == "v1.0"

    profile = client.get("/api/v1/profiles/active").json()
    assert profile["skills"]
    assert "Python" in profile["skills"]


def test_changing_profile_changes_match_score(client, sample_payload):
    order_id = _create(client, sample_payload)
    before = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()["result"]

    profile_id = client.get("/api/v1/profiles/active").json()["id"]
    client.post(f"/api/v1/profiles/{profile_id}/skills", json={"skills": ["1C", "Excel"]})

    after = client.post(f"/api/v1/orders/{order_id}/analyze", json={}).json()["result"]
    assert after["match_score"] is not None
    assert after["match_score"] < before["match_score"]
