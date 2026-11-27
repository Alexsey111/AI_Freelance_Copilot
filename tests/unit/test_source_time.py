"""Время площадок: зона, относительный возраст и то, что «нет числа» — не ноль.

Проверка появилась после живой ошибки: Freelance.ru показывает время по Москве, а парсер
читал его как UTC. Свежий заказ выглядел опубликованным на три часа в будущем, а пороги
свежести 6/12/24 ч считались по сдвинутым числам.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.infrastructure.sources.parsing import (
    parse_at_least_view,
    parse_exact_datetime,
    parse_relative_time,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def test_московское_время_переводится_в_utc() -> None:
    """«27.11.2026 09:45» на площадке — это 06:45 UTC, а не 09:45 UTC."""
    moment = parse_exact_datetime("27.11.2026 09:45")
    assert moment == datetime(2026, 11, 27, 6, 45, tzinfo=UTC)
    assert moment.tzinfo == UTC


def test_свежий_заказ_не_оказывается_из_будущего() -> None:
    published = parse_exact_datetime("27.11.2026 14:50")  # 11:50 UTC, за 10 минут до NOW
    assert published is not None
    assert published < NOW
    assert (NOW - published) == timedelta(minutes=10)


def test_относительный_возраст_считается_от_момента() -> None:
    assert parse_relative_time("20 минут назад", now=NOW) == NOW - timedelta(minutes=20)
    assert parse_relative_time("3 часа назад", now=NOW) == NOW - timedelta(hours=3)


def test_битая_дата_не_превращается_в_сегодня() -> None:
    assert parse_exact_datetime("32.13.2026 99:99") is None
    assert parse_exact_datetime("без даты") is None
    assert parse_relative_time("давно", now=NOW) is None


def test_больше_трёхсот_это_не_триста_ровно() -> None:
    """FL.ru пишет «больше 300» — храним 300, но помечаем, что это нижняя граница."""
    views, kind = parse_at_least_view("больше 300")
    assert (views, kind) == (300, "at_least")
    exact, exact_kind = parse_at_least_view("994")
    assert (exact, exact_kind) == (994, "exact")
