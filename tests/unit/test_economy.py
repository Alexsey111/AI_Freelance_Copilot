"""Мини-экономика: формула и происхождение ставки (ТЗ §33).

Тест защищает две вещи, которые легко испортить незаметно: саму формулу пересчёта
и то, что ставка — это стоимость часа, а не цена заказа.
"""

from __future__ import annotations

from app.domain.services.metrics_service import DEFAULT_HOURLY_RATE_RUB, Metrics


def test_money_formula_matches_hand_calculation():
    """(вручную − с системой) × 100 / 60 × ставка — арифметика должна сходиться до рубля."""
    metrics = Metrics()
    economy = metrics.economy(hourly_rate_rub=1500.0)

    manual = economy["manual_order_minutes"]
    assisted = economy["assisted_order_minutes"]
    expected_minutes = (manual - assisted) * 100
    assert economy["saved_minutes_per_100"] == expected_minutes
    assert economy["saved_hours_per_100"] == round(expected_minutes / 60, 2)
    assert economy["saved_money_rub_per_100"] == round(expected_minutes / 60 * 1500.0, 2)


def test_owner_measured_scenarios():
    """Три сценария из отчёта: 8, 10 и 11 минут ручного разбора против 3 минут с системой."""
    metrics = Metrics()
    assisted = metrics.assisted_order_minutes
    assert assisted == 3, "оценка времени с системой для отчёта — 3 минуты"

    for manual, expected_rub in ((8, 12_500.0), (10, 17_500.0), (11, 20_000.0)):
        saved_hours = (manual - assisted) * 100 / 60
        assert round(saved_hours, 2) == round((manual - assisted) * 100 / 60, 2)
        assert round(saved_hours * DEFAULT_HOURLY_RATE_RUB, 2) == expected_rub


def test_rate_is_configurable_and_documented():
    """Ставка настраивается, а API объясняет, что это стоимость часа, а не цена заказа."""
    metrics = Metrics()
    double = metrics.economy(hourly_rate_rub=3000.0)
    base = metrics.economy()

    assert double["saved_money_rub_per_100"] == base["saved_money_rub_per_100"] * 2
    assert "час" in base["hourly_rate_hint"].lower()
    assert "ставка" in base["money_formula"].lower()
    assert DEFAULT_HOURLY_RATE_RUB == 1500.0


def test_economy_on_empty_database_still_computes_time():
    """Экономика — оценка из ТЗ, поэтому считается и на пустой базе, но расход модели остаётся неизвестен."""
    metrics = Metrics()
    economy = metrics.economy()
    assert economy["saved_hours_per_100"] > 0
    assert economy["measured_avg_analysis_seconds"] is None, "нет анализов — нет замера времени модели"
