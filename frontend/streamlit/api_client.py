"""HTTP-клиент к FastAPI. Единственное место, где frontend знает про REST."""

from __future__ import annotations

import os
from typing import Any

import requests

# ВАЖНО (Windows): именно 127.0.0.1, а не localhost. Имя localhost разрешается сначала
# в IPv6 (::1), а на ::1 порт 8000 может держать ретранслятор Docker (wslrelay.exe) от чужого
# контейнера --- тогда вместо нашего API отвечает он и возвращает 404 {"detail":"Not Found"}.
DEFAULT_BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


class ApiError(RuntimeError):
    """Ошибка обращения к backend с человекочитаемым текстом."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 120.0) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    # --- низкий уровень ---
    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ApiError(
                f"Backend недоступен по адресу {self.base_url}. "
                f"Запустите его командой: uvicorn app.main:app --port 8000. "
                f"Причина: {type(exc).__name__}: {exc}"
            ) from exc
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                detail = payload.get("detail") or payload
            except Exception:  # noqa: BLE001
                detail = response.text[:300]
            raise ApiError(f"HTTP {response.status_code}: {detail}", response.status_code)
        if not response.content:
            return None
        return response.json()

    # --- заказы ---
    def create_order(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/orders", json=payload)

    def list_orders(self, **params) -> dict:
        clean = {key: value for key, value in params.items() if value not in (None, "", [])}
        return self._request("GET", "/api/v1/orders", params=clean)

    def get_order(self, order_id: int) -> dict:
        return self._request("GET", f"/api/v1/orders/{order_id}")

    def order_analyses(self, order_id: int) -> list[dict]:
        return self._request("GET", f"/api/v1/orders/{order_id}/analyses")

    def latest_analysis(self, order_id: int) -> dict | None:
        try:
            return self._request("GET", f"/api/v1/orders/{order_id}/analysis")
        except ApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    # --- ИИ ---
    def analyze(self, order_id: int, profile_id: int | None = None) -> dict:
        payload = {"profile_id": profile_id} if profile_id else {}
        return self._request("POST", f"/api/v1/orders/{order_id}/analyze", json=payload)

    # --- ручная проверка ---
    def review_queue(self, **params) -> dict:
        clean = {key: value for key, value in params.items() if value not in (None, "", [])}
        return self._request("GET", "/api/v1/review-queue", params=clean)

    def decide_review(self, analysis_id: int, decision: str, comment: str | None = None) -> dict:
        return self._request(
            "POST",
            f"/api/v1/analyses/{analysis_id}/review",
            json={"decision": decision, "comment": comment},
        )

    # --- аудит и метрики ---
    def audit(self, **params) -> dict:
        clean = {key: value for key, value in params.items() if value not in (None, "", [])}
        return self._request("GET", "/api/v1/audit", params=clean)

    def audit_actions(self) -> dict:
        return self._request("GET", "/api/v1/audit/actions")

    def metrics(self, hourly_rate_rub: float | None = None) -> dict:
        params = {"hourly_rate_rub": hourly_rate_rub} if hourly_rate_rub else None
        return self._request("GET", "/api/v1/metrics", params=params)

    # --- система ---
    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")

    def active_profile(self) -> dict:
        return self._request("GET", "/api/v1/profiles/active")

    def update_skills(self, profile_id: int, skills: list[str]) -> dict:
        return self._request("POST", f"/api/v1/profiles/{profile_id}/skills", json={"skills": skills})
