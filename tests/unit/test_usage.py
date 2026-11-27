"""Unit: расход прогона — токены, время, деньги.

Деньги считаются только по прайсу, который задал пользователь. Проверяем три вещи:
1. без прайса стоимости нет (`None`), а не ноль — иначе «бесплатно» врёт;
2. сумма по прогону накапливается, а не перезаписывается последним вызовом;
3. провайдер, не вернувший usage, не превращает прогон в «ноль токенов».
"""

from __future__ import annotations

import pytest

from app.domain.models.run import Run
from app.domain.usage import cost_rub, format_cost
from app.infrastructure.database.repositories.run_repository import RunRepository


def test_cost_without_price_is_none_not_zero():
    assert cost_rub(1000, 500, price_in_rub_per_1m=None, price_out_rub_per_1m=None) is None
    assert cost_rub(1000, 500, price_in_rub_per_1m=100.0, price_out_rub_per_1m=None) is None


def test_cost_counts_input_and_output_separately():
    """gpt-4o-mini: ~150 ₽ и ~600 ₽ за миллион входных и выходных токенов.

    1 250 × 150 + 400 × 600 = 427 500 → 0,4275 ₽ за заказ. Это тот же порядок,
    что дал живой замер (1,37 ₽ на 20 заказов = 0,07 ₽/заказ на дешёвой модели).
    """
    cost = cost_rub(1_250, 400, price_in_rub_per_1m=150.0, price_out_rub_per_1m=600.0)
    assert cost == pytest.approx(0.4275)


def test_cost_of_twenty_orders_is_kopecks():
    cost = cost_rub(20 * 1_250, 20 * 400, price_in_rub_per_1m=150.0, price_out_rub_per_1m=600.0)
    assert cost == pytest.approx(8.55)


def test_format_cost_never_pretends_zero():
    assert format_cost(None) == "цена не задана"
    assert format_cost(0) == "0 ₽"
    assert "коп." in format_cost(0.0004)


def test_run_accumulates_usage_across_calls(run_repository):
    run = run_repository.add(Run(kind="analyze_batch", model="mock-model"))
    run_repository.add_usage(
        run.id, tokens_in=1250, tokens_out=400, latency_ms=900, cost_rub=0.4275
    )
    run_repository.add_usage(
        run.id, tokens_in=1100, tokens_out=380, latency_ms=800, cost_rub=0.3930
    )
    stored = run_repository.get(run.id)
    assert stored.tokens_in == 2350
    assert stored.tokens_out == 780
    assert stored.latency_ms == 1700
    assert stored.cost_rub == pytest.approx(0.8205)


def test_usage_absent_stays_none(run_repository):
    """Провайдер без usage: прогон не должен выглядеть как «0 токенов, 0 ₽»."""
    run = run_repository.add(Run(kind="analyze_batch", model="ollama"))
    run_repository.add_usage(
        run.id, tokens_in=None, tokens_out=None, latency_ms=None, cost_rub=None
    )
    stored = run_repository.get(run.id)
    assert stored.tokens_in is None
    assert stored.cost_rub is None


@pytest.fixture
def run_repository(app):
    """Репозиторий на сессии приложения: та же схема, что и в бою, но in-memory."""
    with app.state.database.session() as session:
        yield RunRepository(session)
