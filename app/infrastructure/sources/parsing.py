"""Разбор страниц площадок: текст страницы → ExternalOrder, без сети.

Сознательно без HTML-парсера и без зависимостей: разметку площадки меняют раз в полгода,
и тогда ломается один файл — тот, где лежит нужное выражение. Зато у разбора нет своего
мнения: если поля нет, остаётся None, а не ноль, и «возраст неизвестен» не превращается
в «свежий».

Общее правило для всех площадок: число берём только там, где оно написано числом.
«по договоренности», «больше 300», «обсуждается» — это не число, а факт другого рода,
поэтому бюджет остаётся None, а просмотры — 300 с пометкой «не меньше».
"""

from __future__ import annotations

import html as html_module
import re
from datetime import UTC, datetime, timedelta

from app.infrastructure.sources.base import ExternalOrder

NBSP = "\u00a0"


def _text(raw: str) -> str:
    """HTML-фрагмент → чистый текст без тегов и лишних пробелов."""
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    cleaned = html_module.unescape(cleaned).replace(NBSP, " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _number(raw: str) -> float | None:
    """Первое число из текста: «50 000 ₽» → 50000.0. Нет числа — None, не ноль."""
    digits = re.sub(r"[^\d]", "", raw.split(",")[0])
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


RELATIVE_UNITS = {
    "минут": "minutes",
    "минуту": "minutes",
    "час": "hours",
    "часа": "hours",
    "часов": "hours",
    "день": "days",
    "дня": "days",
    "дней": "days",
    "недел": "weeks",
    "месяц": "weeks",
}


def parse_relative_time(raw: str, *, now: datetime | None = None) -> datetime | None:
    """«20 минут назад», «2 часа назад», «вчера» → момент публикации.

    Площадка отдаёт возраст, а не дату, поэтому точность — до единицы: для отбора это
    не важно (порог 6 часов), но важно не выдать возраст за точную дату.
    """
    text = _text(raw).lower()
    if not text:
        return None
    moment = now or datetime.now(UTC)
    if "только что" in text or "минуту назад" in text:
        return moment - timedelta(minutes=1)
    if "вчера" in text:
        return moment - timedelta(days=1)
    match = re.search(r"(\d+)\s*([а-я]+)", text)
    if not match:
        return None
    amount = int(match.group(1))
    word = match.group(2)
    for stem, unit in RELATIVE_UNITS.items():
        if word.startswith(stem):
            return moment - timedelta(**{unit: amount})
    return None


def parse_exact_datetime(raw: str) -> datetime | None:
    """«27.11.2026 06:32» из подсказки к времени → datetime в UTC."""
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})", raw)
    if not match:
        return None
    day, month, year, hour, minute = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=UTC)
    except ValueError:
        return None


def parse_at_least_view(raw: str) -> tuple[int | None, str | None]:
    """«больше 300» → (300, 'at_least'); «994» → (994, 'exact')."""
    text = _text(raw)
    if not text:
        return None, None
    value = _number(text)
    if value is None:
        return None, None
    kind = "at_least" if re.search(r"больше|свыше|более", text, re.I) else "exact"
    return int(value), kind


# --- FL.ru -------------------------------------------------------------------------


FLRU_CARD = re.compile(r'id="project-item(\d+)"')


def parse_flru(html: str, *, base_url: str = "https://www.fl.ru", now: datetime | None = None):
    """Лента FL.ru → список заказов.

    Разметка карточки: `id="project-item<id>"`, ссылка `/projects/<id>/<slug>.html`,
    цена в `b-post__price`, описание в `b-post__txt text-5`, возраст и просмотры в подвале.
    """
    orders: list[ExternalOrder] = []
    starts = [match.start() for match in FLRU_CARD.finditer(html)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else start + 12_000
        card = html[start:end]
        card_id = FLRU_CARD.search(card)
        if card_id is None:
            continue
        external_id = card_id.group(1)

        link = re.search(rf'href="(/projects/{external_id}/[^"]+)"[^>]*>([^<]+)</a>', card)
        if link is None:
            continue
        url = base_url + link.group(1)
        title = _text(link.group(2))

        price_block = re.search(r"b-post__price[^>]*>([\s\S]{0,400}?)</div>", card)
        price_text = _text(price_block.group(1)) if price_block else ""
        budget = _number(price_text) if price_text and "договор" not in price_text.lower() else None

        desc_block = re.search(r'b-post__txt text-5\s*">([\s\S]{0,2000}?)</div>', card)
        description = _text(desc_block.group(1)) if desc_block else ""

        age_block = re.search(r'text-gray-opacity-4 text-7 mr-16">([^<]+)<', card)
        published_at = parse_relative_time(age_block.group(1), now=now) if age_block else None

        views_block = re.search(
            r'title="Количество просмотров"[\s\S]{0,600}?<span class="text-7">([^<]+)</span>',
            card,
        )
        views, views_kind = (
            parse_at_least_view(views_block.group(1)) if views_block else (None, None)
        )

        # Цифра обязательна: без неё первым совпадением оказывается подсказка
        # title="Количество ответов" у иконки, и число откликов молча теряется.
        responses_block = re.search(r"(\d[\d\s]*)\s*(ответ|отклик)", card, re.I)
        responses = _number(responses_block.group(1)) if responses_block else None

        orders.append(
            ExternalOrder(
                source="flru",
                external_id=external_id,
                title=title,
                description=description,
                budget_min=budget,
                budget_max=budget,
                url=url,
                published_at=published_at,
                views=views,
                responses=int(responses) if responses is not None else None,
                raw={
                    "price_text": price_text,
                    "views_text": _text(views_block.group(1)) if views_block else None,
                    "views_kind": views_kind,
                    "age_text": _text(age_block.group(1)) if age_block else None,
                    "list": "fl.ru/projects",
                },
            )
        )
    return orders


# --- Freelance.ru ------------------------------------------------------------------


def parse_freelance_ru(
    html: str, *, base_url: str = "https://freelance.ru", now: datetime | None = None
):
    """Лента Freelance.ru → список заказов.

    Карточка — `<article class="task-card">`, ссылка `/task/view/<id>`, точное время
    публикации лежит в подсказке к «2 часа назад», поэтому здесь дата настоящая.
    """
    orders: list[ExternalOrder] = []
    cards = html.split('<article class="task-card"')[1:]
    for card in cards:
        link = re.search(r'href="/task/view/(\d+)"[^>]*>([\s\S]{0,200}?)</a>', card)
        if link is None:
            continue
        external_id = link.group(1)
        title = _text(link.group(2))

        desc_block = re.search(r'class="task-card__desc">([\s\S]{0,3000}?)</p>', card)
        description = _text(desc_block.group(1)) if desc_block else ""

        exact = re.search(r'title="(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})"', card)
        published_at = parse_exact_datetime(exact.group(1)) if exact else None
        if published_at is None:
            age_block = re.search(r"fa-clock-o[^>]*></i>\s*([^<]+)<", card)
            published_at = parse_relative_time(age_block.group(1), now=now) if age_block else None

        responses_block = re.search(r"fa-comments[^>]*></i>\s*<strong>(\d+)</strong>", card)
        views_block = re.search(r"fa-eye[^>]*></i>\s*([\d\s\u00a0]+)", card)
        views = _number(views_block.group(1)) if views_block else None

        budget_block = re.search(r"task-card__budget[^>]*>([\s\S]{0,300}?)</div>", card)
        budget_text = _text(budget_block.group(1)) if budget_block else ""
        budget = _number(budget_text) if budget_text and re.search(r"\d", budget_text) else None

        orders.append(
            ExternalOrder(
                source="freelance_ru",
                external_id=external_id,
                title=title,
                description=description,
                budget_min=budget,
                budget_max=budget,
                url=f"{base_url}/task/view/{external_id}",
                published_at=published_at,
                views=int(views) if views is not None else None,
                responses=int(responses_block.group(1)) if responses_block else None,
                raw={
                    "budget_text": budget_text,
                    "views_text": _text(views_block.group(1)) if views_block else None,
                    "list": "freelance.ru/project/search",
                },
            )
        )
    return orders
