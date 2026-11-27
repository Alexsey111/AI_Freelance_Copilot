"""Нормы времени по типам задач и распределение недели.

Зачем: без часов нельзя посчитать ни ставку ₽/час, ни загрузку недели, ни ответ
«куда уходит моё время». Человек знает свои нормы приблизительно — «бот восемь часов,
парсер шесть, интеграция десять» — и эти цифры должны правиться в окне программы,
а не жить в голове и не вводиться заново на каждом заказе.

Сопоставление заказа с нормой — по ключевым словам, без модели: результат объясним
(«тип определён по слову telegram-бот»), повторяем и не стоит токенов. Если тип
не определился, часов нет — и это честнее выдуманного среднего.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_NORMS: tuple[dict, ...] = (
    {
        "task_kind": "bot",
        "title": "Telegram-бот",
        "hours": 8.0,
        "keywords": ["telegram", "телеграм", "бот", "bot", "чат-бот"],
        "note": "Бот с меню и хранилищем; без сложной интеграции",
    },
    {
        "task_kind": "parser",
        "title": "Парсер / сбор данных",
        "hours": 6.0,
        "keywords": ["парсер", "парсинг", "scrap", "сбор данн", "выгрузк", "excel"],
        "note": "Парсер с выгрузкой в файл или таблицу",
    },
    {
        "task_kind": "integration",
        "title": "Интеграция с API / CRM",
        "hours": 10.0,
        "keywords": ["интеграц", "api", "crm", "webhook", "вебхук", "1с", "битрикс"],
        "note": "Два и более сервиса, обмен данными, обработка ошибок",
    },
    {
        "task_kind": "ai_agent",
        "title": "ИИ-агент / LLM",
        "hours": 12.0,
        "keywords": ["ии-агент", "агент", "llm", "gpt", "нейросет", "rag", "ассистент"],
        "note": "Промпты, вызов модели, обработка ответа, проверка качества",
    },
    {
        "task_kind": "automation",
        "title": "Автоматизация процесса",
        "hours": 16.0,
        "keywords": ["автоматизац", "процесс", "n8n", "сценарий", "воронк"],
        "note": "Несколько шагов, расписание, уведомления",
    },
    {
        "task_kind": "site",
        "title": "Сайт / лендинг",
        "hours": 20.0,
        "keywords": ["сайт", "лендинг", "landing", "вёрстк", "верстк"],
        "note": "Страница или небольшой сайт с формой",
    },
    {
        "task_kind": "analytics",
        "title": "Дашборд / аналитика",
        "hours": 10.0,
        "keywords": ["дашборд", "dashboard", "аналитик", "отчёт", "отчет", "метрик"],
        "note": "Сбор данных и наглядная сводка",
    },
    {
        "task_kind": "article",
        "title": "Статья / текст",
        "hours": 4.0,
        "keywords": ["статья", "текст на сайт", "копирайт", "рерайт", "контент"],
        "note": "8 000 знаков с редактурой и проверкой фактов",
    },
    {
        "task_kind": "description",
        "title": "Описание / карточка товара",
        "hours": 1.0,
        "keywords": ["описание товар", "карточк", "маркетплейс", "инфографик"],
        "note": "Одна карточка с ключевыми словами",
    },
    {
        "task_kind": "translation",
        "title": "Перевод",
        "hours": 2.0,
        "keywords": ["перевод", "локализац", "translation"],
        "note": "Одна страница текста с вычиткой",
    },
    {
        "task_kind": "logo",
        "title": "Логотип",
        "hours": 8.0,
        "keywords": ["логотип", "лого", "бренд", "фирменный стиль"],
        "note": "Два-три варианта, доработка выбранного, файлы в цветах",
    },
    {
        "task_kind": "banner",
        "title": "Баннер / креатив",
        "hours": 3.0,
        "keywords": ["баннер", "креатив", "обложк", "макет"],
        "note": "Один макет в нужных размерах",
    },
    {
        "task_kind": "presentation",
        "title": "Презентация",
        "hours": 6.0,
        "keywords": ["презентац", "слайд", "pitch", "deck"],
        "note": "10–15 слайдов с текстом и оформлением",
    },
    {
        "task_kind": "video_edit",
        "title": "Монтаж видео",
        "hours": 10.0,
        "keywords": ["монтаж", "видео", "ролик", "reels", "shorts"],
        "note": "Ролик до 5 минут: нарезка, титры, звук",
    },
    {
        "task_kind": "smm_post",
        "title": "Пост в соцсети / контент-план",
        "hours": 2.0,
        "keywords": ["пост", "smm", "контент-план", "соцсет"],
        "note": "Текст, визуал, публикация и ответы",
    },
    {
        "task_kind": "seo",
        "title": "SEO-работа",
        "hours": 5.0,
        "keywords": ["seo", "продвижен", "семантик", "выдач"],
        "note": "Семантика, оптимизация страницы, отчёт",
    },
    {
        "task_kind": "consult",
        "title": "Консультация / разбор",
        "hours": 2.0,
        "keywords": ["консультац", "разбор", "аудит", "совет"],
        "note": "Созвон с разбором и коротким письмом по итогам",
    },
    {
        "task_kind": "edit",
        "title": "Доработка / правки",
        "hours": 3.0,
        "keywords": ["доработ", "правк", "исправить", "доделать", "баг"],
        "note": "Мелкая правка в готовом проекте",
    },
)


@dataclass(slots=True)
class Norm:
    task_kind: str
    title: str
    hours: float
    keywords: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass(slots=True)
class Guess:
    norm: Norm | None
    matched: str | None

    @property
    def hours(self) -> float | None:
        return self.norm.hours if self.norm else None

    @property
    def reason(self) -> str:
        if self.norm is None:
            return "Тип задачи не определён: нет подходящих норм"
        return f"Норма «{self.norm.title}»: в тексте встретилось «{self.matched}»"


def guess_norm(title: str, description: str, norms: list[Norm]) -> Guess:
    """Тип задачи по ключевым словам. Больше совпадений — точнее норма."""
    haystack = f"{title}\n{description}".lower()
    best: tuple[int, Norm, str] | None = None
    for norm in norms:
        for keyword in norm.keywords:
            if keyword.lower() in haystack:
                score = sum(1 for k in norm.keywords if k.lower() in haystack)
                if best is None or score > best[0]:
                    best = (score, norm, keyword)
                break
    if best is None:
        return Guess(norm=None, matched=None)
    return Guess(norm=best[1], matched=best[2])


@dataclass(slots=True)
class WorkloadRow:
    task_kind: str
    title: str
    orders: int
    hours: float
    money: float


@dataclass(slots=True)
class Workload:
    capacity_hours: float
    booked_hours: float
    money: float
    orders: int
    rows: list[WorkloadRow]

    @property
    def free_hours(self) -> float:
        return max(self.capacity_hours - self.booked_hours, 0.0)

    @property
    def load_share(self) -> float:
        if self.capacity_hours <= 0:
            return 0.0
        return min(round(self.booked_hours / self.capacity_hours, 3), 1.0)


def workload(items: list[dict], *, capacity_hours: float = 45.0) -> Workload:
    """Распределение часов по типам задач.

    `items` — принятые заказы: `task_kind`, `title`, `hours`, `money`. Заказы без
    часов попадают в отдельную строку «не оценено»: их нельзя молча выбросить,
    иначе окно покажет загрузку меньше реальной.
    """
    buckets: dict[str, WorkloadRow] = {}
    for item in items:
        kind = item.get("task_kind") or "unknown"
        title = item.get("title") or ("Не оценено" if kind == "unknown" else kind)
        row = buckets.setdefault(kind, WorkloadRow(kind, title, 0, 0.0, 0.0))
        row.orders += 1
        row.hours += float(item.get("hours") or 0.0)
        row.money += float(item.get("money") or 0.0)
    rows = sorted(buckets.values(), key=lambda r: r.hours, reverse=True)
    return Workload(
        capacity_hours=capacity_hours,
        booked_hours=round(sum(r.hours for r in rows), 2),
        money=round(sum(r.money for r in rows), 2),
        orders=sum(r.orders for r in rows),
        rows=rows,
    )
