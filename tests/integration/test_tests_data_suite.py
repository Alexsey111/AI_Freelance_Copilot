"""Integration: прогон всего набора tests_data/ через живое API (более 10 тестов).

Каждый сценарий из tests_data/inputs.jsonl проверяется против ожиданий из tests_data/specs.jsonl.
Кроме сценариев проверяются запросы витрины из tests_data/queries.jsonl и события аудита
из tests_data/events.jsonl.
"""

from __future__ import annotations

import pytest

from tests.fixtures.tests_data_set import (
    cases,
    events,
    load_jsonl,
    queries,
    run_suite,
    specs,
)
from tests.fixtures.tests_data_set import inputs as suite_inputs

SCENARIO_IDS = [case["id"] for case in cases()]
NEEDS_REVIEW_IDS = [spec["id"] for spec in specs() if spec["needs_review"]]
QUERY_IDS = [query["id"] for query in queries()]


def test_tests_data_files_are_complete():
    """Набор данных целостен: минимум 10 сценариев и хотя бы 1-2 случая ручной проверки."""
    assert len(suite_inputs()) >= 10, "нужно минимум 10 тестовых сценариев"
    assert len(NEEDS_REVIEW_IDS) >= 2, "нужно хотя бы 2 случая с needs_review=true"
    ids = [row["id"] for row in suite_inputs()]
    assert len(set(ids)) == len(ids), "идентификаторы сценариев должны быть уникальными"
    assert {row["id"] for row in specs()} == set(ids), "specs.jsonl должен покрывать все входы"


@pytest.mark.parametrize("case_id", SCENARIO_IDS)
def test_scenario_matches_spec(client, case_id):
    """Проверка одного сценария из набора: результат должен совпасть со спецификацией."""
    outcomes, _ = run_suite(client)
    by_id = {outcome.id: outcome for outcome in outcomes}
    case = next(item for item in cases() if item["id"] == case_id)
    outcome = by_id[case_id]
    assert outcome.error is None, outcome.error

    from tests.fixtures.tests_data_set import check_spec

    problems = check_spec(outcome, case["spec"])
    assert not problems, problems


def test_all_scenarios_pass_together(client):
    """Сквозной прогон: все 13 сценариев, включая ошибочные, дают ожидаемый результат."""
    outcomes, problems = run_suite(client)
    assert len(outcomes) == len(cases())
    assert problems == [], problems
    assert all(outcome.error is None for outcome in outcomes)


def test_cases_requiring_manual_review_are_flagged(client):
    """Обязательное требование сдачи: есть сценарии, приводящие к needs_review=true."""
    outcomes, _ = run_suite(client)
    by_id = {outcome.id: outcome for outcome in outcomes}

    flagged = [outcome for outcome in outcomes if outcome.needs_review]
    assert len(flagged) >= 2, "ожидались как минимум два случая ручной проверки"

    for case_id in NEEDS_REVIEW_IDS:
        outcome = by_id[case_id]
        assert outcome.needs_review is True, f"{case_id}: ожидалась ручная проверка"
        assert outcome.review_reason, f"{case_id}: у ручной проверки обязана быть причина"
        assert outcome.draft_reply is None or outcome.draft_reply == "", (
            f"{case_id}: на ручную проверку уходит результат без готового отклика"
        )


@pytest.mark.parametrize("query_id", QUERY_IDS)
def test_showcase_queries(client, query_id):
    """Запросы витрины из tests_data/queries.jsonl (включая проверку ошибки фильтра)."""
    run_suite(client)
    query = next(item for item in queries() if item["id"] == query_id)
    response = client.get("/api/v1/orders", params=query["params"])
    if query.get("expect_http"):
        assert response.status_code == query["expect_http"]
        return
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == query["expect_total"], (query_id, body["total"])
    if query.get("expect_items"):
        assert len(body["items"]) == query["expect_items"]
    if query.get("expect_page"):
        assert body["page"] == query["expect_page"]
    if query.get("expect_all_needs_review"):
        assert all(item["needs_review"] for item in body["items"])


def test_audit_events_match_expected_statuses(client):
    """Событие аудита на каждый ключевой сценарий (tests_data/events.jsonl)."""
    run_suite(client)
    audit = client.get("/api/v1/audit", params={"action": "analyze_order", "page_size": 200}).json()

    for event in events():
        assert event["audit_action"] == "analyze_order"
        matching = [row for row in audit["items"] if row["action"] == event["audit_action"]]
        assert matching, f"{event['id']}: нет записей аудита по действию {event['audit_action']}"
        statuses = {row["status"] for row in matching}
        assert event["audit_status"] in statuses, (
            f"{event['id']}: ожидался статус аудита {event['audit_status']}, есть {statuses}"
        )


def test_every_action_is_audited(client):
    """Доказательство работоспособности: аудит пишется на создание, анализ и решение человека."""
    run_suite(client)
    actions = client.get("/api/v1/audit/actions").json()["actions"]
    assert actions.get("create_order", 0) >= 10
    assert actions.get("analyze_order", 0) >= 10

    queue = client.get("/api/v1/review-queue").json()
    assert queue["total"] >= 2
    analysis_id = queue["items"][0]["analysis_id"]
    client.post(f"/api/v1/analyses/{analysis_id}/review", json={"decision": "approved"})
    actions = client.get("/api/v1/audit/actions").json()["actions"]
    assert actions.get("review_decision", 0) == 1


def test_jsonl_files_are_loadable():
    """Файлы набора читаются и не содержат пустых записей."""
    for name in ("inputs.jsonl", "specs.jsonl", "events.jsonl", "queries.jsonl"):
        rows = load_jsonl(name)
        assert rows, f"{name} пуст"
        assert all(isinstance(row, dict) and row.get("id") for row in rows)
