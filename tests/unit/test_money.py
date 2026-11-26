"""Unit: деньги на входе в ядро (граница «источник → объект»).

Проверяется решение владельца от 26.11.2026: число приводим, прописью — не угадываем
и отдаём человеку, диапазон раскладываем на границы, «договорная» — это отсутствие
бюджета, а не мусор.
"""

from __future__ import annotations

from app.domain.money import normalize_budget, parse_amounts
from app.infrastructure.sources.base import ExternalOrder, normalize_external_order


def _order(budget_min=None, budget_max=None):
    return normalize_external_order(
        ExternalOrder(
            source="manual",
            title="Нужен парсер и выгрузка в Excel",
            description="Python, ежедневный сбор, выгрузка в CSV. Объём работ понятен.",
            budget_min=budget_min,
            budget_max=budget_max,
        )
    )


def test_numbers_pass_through():
    parsed = normalize_budget(30000, 50000)
    assert (parsed.low, parsed.high) == (30000.0, 50000.0)
    assert parsed.status == "parsed" and not parsed.needs_human


def test_numeric_strings_and_separators():
    for raw, expected in [
        ("60000", 60000),          # n8n/payload.json
        ("50 000", 50000),
        ("50\u00a0000", 50000),    # неразрывный пробел из HTML
        ("50\u202f000", 50000),    # тонкий пробел
        ("(50000)", 50000),
        ("60.000", 60000),
        ("50 000,50", 50000.5),
    ]:
        amounts, status = parse_amounts(raw)
        assert status == "parsed", raw
        assert amounts == [float(expected)], raw


def test_multipliers():
    assert parse_amounts("50к")[0] == [50000.0]
    assert parse_amounts("50 тыс. рублей")[0] == [50000.0]
    assert parse_amounts("1,5 млн")[0] == [1500000.0]
    # «к» и «м» как множитель — только отдельным словом, иначе «50 комнат» станет 50 000.
    assert parse_amounts("50 комнат")[0] == [50.0]


def test_range_goes_to_min_and_max():
    parsed = normalize_budget("от 15 000 до 20 000", None)  # n8n/payload-tilda.json
    assert (parsed.low, parsed.high) == (15000.0, 20000.0)
    assert parsed.status == "parsed"


def test_absent_budget_is_not_an_error():
    for raw in (None, "", "договорная", "по договорённости"):
        parsed = normalize_budget(raw, None)
        assert parsed.low is None and parsed.high is None, raw
        assert parsed.status == "absent", raw
        assert not parsed.needs_human, raw


def test_worded_budget_goes_to_human_not_guessed():
    parsed = normalize_budget("пятьдесят тысяч", None)
    assert parsed.low is None and parsed.high is None
    assert parsed.status == "worded"
    assert parsed.needs_human
    assert "человек" in (parsed.note or "")


def test_swapped_borders_are_put_in_order():
    parsed = normalize_budget("50 000", "20 000")
    assert (parsed.low, parsed.high) == (20000.0, 50000.0)
    assert "местами" in (parsed.note or "")


def test_order_boundary_gets_number_not_string():
    """Главная проверка границы: строка из HTML/парсера становится числом.

    На коде без нормализации здесь лежит "50 000", и сравнение с минимумом профиля
    падает с TypeError или идёт посимвольно.
    """
    order = _order(budget_min="50 000")

    assert order.budget_min == 50000.0
    assert order.budget_min is not None and order.budget_min < 60000  # сравнение работает


def test_order_with_worded_budget_is_flagged_for_human():
    order = _order(budget_min="пятьдесят тысяч")

    assert order.budget_min is None
    assert order.needs_review is True
    assert "не указан бюджет" in order.missing_data()


def test_payloads_from_n8n_are_understood():
    """Те же входы, что лежат в openclaw-orders-agent/n8n/payload*.json."""
    assert _order(budget_min="60000").budget_min == 60000.0
    tilda = _order(budget_min="от 15 000 до 20 000")
    assert (tilda.budget_min, tilda.budget_max) == (15000.0, 20000.0)
    assert _order().budget_min is None  # payload-no-budget.json
    assert _order(budget_min="70000").budget_min == 70000.0  # payload-model-garbage.json
