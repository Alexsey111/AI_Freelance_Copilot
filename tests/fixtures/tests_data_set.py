"""Загрузка набора тестовых данных из tests_data/*.jsonl.

Один источник правды для тестов и для отчёта: файлы в tests_data/ читают и pytest,
и скрипт прогона. Поэтому «тестовые данные» и «тесты» не могут разойтись.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TESTS_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "tests_data"


def load_jsonl(name: str) -> list[dict]:
    """Прочитать JSONL-файл набора (по одной JSON-записи на строку)."""
    path = TESTS_DATA_DIR / name
    if not path.exists():  # pragma: no cover - защита от неполной поставки
        raise FileNotFoundError(f"Нет файла набора тестовых данных: {path}")
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise ValueError(f"{name}:{line_number}: невалидный JSON: {exc}") from exc
    return rows


@lru_cache(maxsize=1)
def inputs() -> list[dict]:
    return load_jsonl("inputs.jsonl")


@lru_cache(maxsize=1)
def specs() -> list[dict]:
    return load_jsonl("specs.jsonl")


@lru_cache(maxsize=1)
def events() -> list[dict]:
    return load_jsonl("events.jsonl")


@lru_cache(maxsize=1)
def queries() -> list[dict]:
    return load_jsonl("queries.jsonl")


@lru_cache(maxsize=1)
def cases() -> list[dict]:
    """Вход + ожидаемый результат по одному сценарию (склейка inputs и specs)."""
    spec_by_id = {row["id"]: row for row in specs()}
    merged = []
    for row in inputs():
        spec = spec_by_id.get(row["id"])
        if spec is None:  # pragma: no cover - ловит рассинхрон файлов
            raise ValueError(f"Для сценария {row['id']} нет спецификации в specs.jsonl")
        merged.append({"id": row["id"], "payload": row["payload"], "spec": spec})
    return merged


@dataclass(slots=True)
class ScenarioOutcome:
    """Фактический результат прогона одного сценария."""

    id: str
    order_id: int | None = None
    http_status: int | None = None
    needs_review: bool | None = None
    recommendation: str | None = None
    match_score: float | None = None
    review_reason: str | None = None
    draft_reply: str | None = None
    audit_status: str | None = None
    order_status: str | None = None
    error: str | None = None

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "http_status": self.http_status,
            "needs_review": self.needs_review,
            "recommendation": self.recommendation,
            "match_score": self.match_score,
            "review_reason": self.review_reason,
            "has_draft_reply": bool(self.draft_reply),
            "audit_status": self.audit_status,
            "order_status": self.order_status,
            "error": self.error,
        }


def check_spec(row: ScenarioOutcome, spec: dict) -> list[str]:
    """Сверить фактический результат с ожиданием из specs.jsonl. Возвращает список расхождений."""
    problems: list[str] = []
    if spec.get("needs_review") is not None and row.needs_review != spec["needs_review"]:
        problems.append(f"needs_review: ожидалось {spec['needs_review']}, получено {row.needs_review}")
    if spec.get("recommendation") and row.recommendation != spec["recommendation"]:
        problems.append(f"recommendation: ожидалось {spec['recommendation']}, получено {row.recommendation}")
    if spec.get("match_score") is None and "match_score" in spec and row.match_score is not None:
        problems.append(f"match_score: ожидалось null, получено {row.match_score}")
    if spec.get("match_score_min") is not None and (
        row.match_score is None or row.match_score < spec["match_score_min"]
    ):
        problems.append(f"match_score: ожидалось >= {spec['match_score_min']}, получено {row.match_score}")
    if spec.get("match_score_max") is not None and (
        row.match_score is None or row.match_score > spec["match_score_max"]
    ):
        problems.append(f"match_score: ожидалось <= {spec['match_score_max']}, получено {row.match_score}")
    if spec.get("draft_reply") is not None and bool(row.draft_reply) != spec["draft_reply"]:
        problems.append(f"draft_reply: ожидалось {spec['draft_reply']}, получено {bool(row.draft_reply)}")
    if spec.get("review_reason_contains"):
        reason = (row.review_reason or "").lower()
        if spec["review_reason_contains"].lower() not in reason:
            problems.append(
                f"review_reason: ожидалось вхождение {spec['review_reason_contains']!r}, получено {row.review_reason!r}"
            )
    if spec.get("audit_status") and row.audit_status != spec["audit_status"]:
        problems.append(f"audit_status: ожидалось {spec['audit_status']}, получено {row.audit_status}")
    if spec.get("order_status") and row.order_status != spec["order_status"]:
        problems.append(f"order_status: ожидалось {spec['order_status']}, получено {row.order_status}")
    return problems


def run_suite(client) -> tuple[list[ScenarioOutcome], list[str]]:
    """Прогнать весь набор через HTTP API: создать заказ -> проанализировать -> собрать результат.

    Возвращает (результаты по сценариям, список проблем).
    """
    outcomes: list[ScenarioOutcome] = []
    problems: list[str] = []
    for case in cases():
        payload = dict(case["payload"])
        outcome = ScenarioOutcome(id=case["id"])
        created = client.post("/api/v1/orders", json=payload)
        outcome.http_status = created.status_code
        if created.status_code != 201:
            outcome.error = f"создание заказа: HTTP {created.status_code} {created.text[:200]}"
            problems.append(f"{case['id']}: {outcome.error}")
            outcomes.append(outcome)
            continue
        created_body = created.json()
        outcome.order_id = created_body["id"]

        analyzed = client.post(f"/api/v1/orders/{outcome.order_id}/analyze", json={})
        if analyzed.status_code != 200:
            outcome.error = f"анализ: HTTP {analyzed.status_code} {analyzed.text[:200]}"
            problems.append(f"{case['id']}: {outcome.error}")
            outcomes.append(outcome)
            continue
        body = analyzed.json()
        result = body["result"]
        outcome.needs_review = result["needs_review"]
        outcome.recommendation = result["recommendation"]
        outcome.match_score = result["match_score"]
        outcome.review_reason = result["review_reason"]
        outcome.draft_reply = result["draft_reply"]
        outcome.audit_status = body["audit_status"]
        outcome.order_status = body["order_status"]

        problems.extend(f"{case['id']}: {text}" for text in check_spec(outcome, case["spec"]))
        outcomes.append(outcome)
    return outcomes, problems
