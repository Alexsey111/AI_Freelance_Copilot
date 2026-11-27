"""Загрузка страниц площадок: один HTTP-клиент и честные ошибки.

Правила, которые здесь зашиты:

- один запрос — одна страница, не «весь сайт»: площадки считают частоту и отдают капчу;
- User-Agent как у обычного браузера, без него часть страниц приходит заглушкой;
- если страница пришла без данных (заглушка, капча, «войдите»), это не «нет заказов»,
  а недоступность источника — разные вещи, и вторую нельзя молча превращать в первую.
"""

from __future__ import annotations

import time

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Пауза между страницами одной площадки: вежливость дешевле, чем блокировка по IP.
DEFAULT_DELAY_SECONDS = 1.5


class SourceUnavailable(RuntimeError):
    """Источник недоступен: капча, заглушка, требуется вход. Это не «заказов нет»."""


def fetch_html(
    url: str,
    *,
    timeout: float = 20.0,
    user_agent: str = DEFAULT_UA,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Скачивает страницу и отдаёт HTML. Сетевые ошибки — SourceUnavailable."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    try:
        with httpx.Client(
            headers=headers, timeout=timeout, follow_redirects=True, transport=transport
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as error:
        raise SourceUnavailable(f"{url}: сеть недоступна ({error.__class__.__name__})") from error
    if response.status_code >= 400:
        raise SourceUnavailable(f"{url}: HTTP {response.status_code}")
    return response.text


def polite_pause(seconds: float = DEFAULT_DELAY_SECONDS) -> None:
    """Пауза между запросами к одной площадке."""
    if seconds > 0:
        time.sleep(seconds)
