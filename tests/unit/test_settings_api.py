"""API-тесты: правила работы и профиль исполнителя.

Проверяем то, ради чего это делалось: числа, влияющие на отбор заказов, меняются через API
(значит — из окна программы), проверяются на границах, оставляют след в истории и
возвращаются к значению по умолчанию. И что профиль (кто я и за что берусь) правится целиком.
"""

from __future__ import annotations


def test_settings_list_has_labels_and_defaults(client):
    items = client.get("/api/v1/settings").json()
    by_key = {item["key"]: item for item in items}
    assert "min_rate_rub_per_hour" in by_key
    assert by_key["min_rate_rub_per_hour"]["label"] == "Ставка, ниже которой не берём"
    assert by_key["budget_mode"]["choices"] == ["hard", "portfolio"]
    assert by_key["target_week_rub"]["unit"] == " ₽"


def test_setting_changes_from_api_and_source_becomes_db(client):
    response = client.put("/api/v1/settings/min_rate_rub_per_hour", json={"value": "2000"})
    assert response.status_code == 200
    assert response.json()["value"] == "2000"
    assert response.json()["source"] == "настройка"
    again = {item["key"]: item for item in client.get("/api/v1/settings").json()}
    assert again["min_rate_rub_per_hour"]["value"] == "2000"


def test_setting_rejects_out_of_bounds_and_bad_choice(client):
    too_many_hours = client.put("/api/v1/settings/available_hours_per_week", json={"value": "300"})
    assert too_many_hours.status_code == 422
    assert "больше допустимого" in too_many_hours.json()["detail"]

    bad_mode = client.put("/api/v1/settings/budget_mode", json={"value": "что-нибудь"})
    assert bad_mode.status_code == 422
    assert "допустимо" in bad_mode.json()["detail"]

    not_number = client.put("/api/v1/settings/target_week_rub", json={"value": "сто тысяч"})
    assert not_number.status_code == 422


def test_unknown_setting_is_404(client):
    assert client.put("/api/v1/settings/free_lunch", json={"value": "1"}).status_code == 404


def test_history_records_who_changed_what(client):
    client.put(
        "/api/v1/settings/min_rate_rub_per_hour",
        json={"value": "1800", "changed_by": "Алексей"},
    )
    history = client.get("/api/v1/settings/history?key=min_rate_rub_per_hour").json()
    assert history[0]["new_value"] == "1800"
    assert history[0]["changed_by"] == "Алексей"
    assert history[0]["label"] == "Ставка, ниже которой не берём"


def test_reset_returns_default_but_keeps_history(client):
    client.put("/api/v1/settings/min_rate_rub_per_hour", json={"value": "2000"})
    reset = client.delete("/api/v1/settings/min_rate_rub_per_hour")
    assert reset.status_code == 200
    assert reset.json()["source"] == "по умолчанию"
    assert reset.json()["value"] == "1500"
    assert len(client.get("/api/v1/settings/history?key=min_rate_rub_per_hour").json()) >= 2


def test_profile_can_be_edited_from_api(client):
    profile = client.get("/api/v1/profiles/active").json()
    updated = client.patch(
        f"/api/v1/profiles/{profile['id']}",
        json={
            "skills": ["Python", "FastAPI", "LLM"],
            "preferences": {"min_budget_rub": 50000, "rate_rub_per_hour": 2000},
            "summary": "Автоматизация на ИИ: боты, парсеры, интеграции",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["skills"] == ["Python", "FastAPI", "LLM"]
    assert body["preferences"]["rate_rub_per_hour"] == 2000


def test_profile_rejects_empty_skills_and_unknown_profile(client):
    profile = client.get("/api/v1/profiles/active").json()
    empty = client.patch(f"/api/v1/profiles/{profile['id']}", json={"skills": []})
    assert empty.status_code == 422
    missing = client.patch("/api/v1/profiles/9999", json={"skills": ["Python"]})
    assert missing.status_code == 404
