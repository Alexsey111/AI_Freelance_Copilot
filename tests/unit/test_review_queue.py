"""Unit: очередь проверки ведётся вместе с флагом `needs_review` (миграция 0002).

Смысл: «сколько заказ висит в проверке» должно считаться от момента постановки,
а не от момента создания записи. Поэтому `queued_at` появляется при `needs_review=True`
и исчезает, когда человек решение принял; без этого в отчёте считается не то время.
"""

from __future__ import annotations

from app.domain.models.order import OrderStatus


def _vague(payload: dict) -> dict:
    body = dict(payload)
    body["description"] = "Надо сделать сайт"  # короче min_description_chars -> проверка
    return body


def test_order_needing_review_gets_queue_timestamp(client, sample_payload):
    created = client.post("/api/v1/orders", json=_vague(sample_payload)).json()
    assert created["needs_review"] is True

    card = client.get(f"/api/v1/orders/{created['id']}").json()
    assert card["queued_at"] is not None


def test_clean_order_has_no_queue_timestamp(client, sample_payload):
    created = client.post("/api/v1/orders", json=sample_payload).json()
    card = client.get(f"/api/v1/orders/{created['id']}").json()
    assert card["needs_review"] is False
    assert card["queued_at"] is None


def test_review_decision_clears_queue(client, sample_payload):
    created = client.post("/api/v1/orders", json=_vague(sample_payload)).json()
    analyzed = client.post(f"/api/v1/orders/{created['id']}/analyze", json={}).json()
    analysis_id = analyzed["analysis_id"]

    decided = client.post(
        f"/api/v1/analyses/{analysis_id}/review",
        json={"decision": "approved", "comment": "проверено"},
    )
    assert decided.status_code == 200, decided.text

    card = client.get(f"/api/v1/orders/{created['id']}").json()
    assert card["status"] == OrderStatus.APPROVED.value
    assert card["needs_review"] is False
    assert card["queued_at"] is None


def test_published_at_roundtrip(client, sample_payload):
    body = dict(sample_payload)
    body["published_at"] = "2026-11-26T12:00:00+00:00"
    created = client.post("/api/v1/orders", json=body)
    assert created.status_code == 201, created.text

    card = client.get(f"/api/v1/orders/{created.json()['id']}").json()
    assert card["published_at"].startswith("2026-11-26T12:00:00")
