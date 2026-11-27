"""Контекст прогона: какой `run_id` сейчас активен.

Прогон начинается на границе запроса (или скрипта) и живёт до его конца. Прокидывать
`run_id` руками через сервис, репозиторий, аудит и правила — это правка в десяти местах
и десять мест, где его можно забыть. Поэтому он живёт в `ContextVar`, как транзакция
в SQLAlchemy: репозитории берут текущий прогон сами, а тесты — тоже (в тесте контекст
пустой, значит `run_id` останется NULL, и это проверяется явно).

Правило: прогон выставляется на входе (заголовок `X-Run-Id` или скрипт), а не в глубине
бизнес-логики. Бизнес-логика о существовании прогона не знает.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_current_run_id: ContextVar[int | None] = ContextVar("current_run_id", default=None)

# Заголовок, которым запуск сообщает, в каком прогоне он работает.
RUN_HEADER = "X-Run-Id"


def current_run_id() -> int | None:
    """ID активного прогона или None, если запись идёт вне прогона."""
    return _current_run_id.get()


@contextmanager
def run_scope(run_id: int | None) -> Iterator[int | None]:
    """Все записи внутри блока относятся к прогону `run_id`.

    Вложенный вызов восстанавливает предыдущее значение, а не обнуляет его.
    """
    token = _current_run_id.set(run_id)
    try:
        yield run_id
    finally:
        _current_run_id.reset(token)
