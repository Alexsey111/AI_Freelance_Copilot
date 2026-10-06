"""Matching Engine (ТЗ §20): детерминированное сопоставление заказа с профилем.

Зачем отдельный модуль:
  * даёт воспроизводимый match score, который можно протестировать юнит-тестами (ТЗ §32);
  * служит независимой проверкой ответа LLM (ТЗ §14 случай 3 --- "не удалось определить
    соответствие профилю");
  * не зависит ни от какой LLM, поэтому тесты бесплатны.

Важно: score и порог ручной проверки --- независимые механизмы. Порог живёт в
бизнес-правилах (analysis_service), а не внутри формулы score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Лексикон навыков: канонический навык -> синонимы/подстроки в тексте заказа.
SKILL_LEXICON: dict[str, tuple[str, ...]] = {
    "Python": ("python", "питон", "пайтон", "pyqt"),
    "FastAPI": ("fastapi", "фастапи"),
    "Django": ("django", "джанго"),
    "Flask": ("flask",),
    "SQLAlchemy": ("sqlalchemy",),
    "PostgreSQL": ("postgresql", "postgres", "постгрес"),
    "MySQL": ("mysql",),
    "SQLite": ("sqlite",),
    "Docker": ("docker", "докер", "docker-compose"),
    "Linux": ("linux", "ubuntu", "debian", "nginx"),
    "Git": ("git", "github", "gitlab"),
    "LLM": ("llm", "gpt", "openai", "нейросет", "языковая модель", "промпт", "prompt"),
    "REST API": ("rest", "api", "эндпоинт", "endpoint", "swagger", "openapi"),
    "Telegram": ("telegram", "телеграм", "aiogram", "тг-бот", "телеграм-бот"),
    "AI automation": ("автоматизац", "ai automation", "ии-агент", "ai-агент"),
    "Parsing": ("парсинг", "scraping", "скрапинг", "beautifulsoup", "selenium", "playwright"),
    "Data analysis": ("анализ данных", "pandas", "numpy", "дашборд", "dashboard"),
    "Machine learning": ("машинное обучение", "ml", "pytorch", "tensorflow", "scikit"),
    "JavaScript": ("javascript", "typescript", "js", "ts"),
    "React": ("react", "next.js", "nextjs"),
    "Vue": ("vue", "nuxt"),
    "PHP": ("php", "laravel", "симфони"),
    "WordPress": ("wordpress", "вордпресс", "tilda", "тильда"),
    "1C": ("1с", "1c", "битрикс24"),
    "Excel": ("excel", "гугл-таблиц", "google sheets", "таблиц"),
    "SEO": ("seo", "продвижение сайта", "семантик"),
    "QA": ("тестирование", "qa", "pytest", "автотест"),
    "Design": ("figma", "дизайн", "верстк", "photoshop"),
    "Mobile": ("android", "ios", "mobile", "flutter", "kotlin", "swift"),
    "Go": ("golang", "go-разработ"),
    "Java": ("java", "spring"),
    "C#": ("c#", "csharp", ".net"),
}

_LATIN_ALIAS = re.compile(r"[a-z0-9+#.\- ]+")


@dataclass(slots=True)
class MatchOutcome:
    """Результат детерминированного сопоставления."""

    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    score: float | None = None
    reason: str = ""

    @property
    def is_determined(self) -> bool:
        """Удалось ли вообще определить соответствие (ТЗ §14 случай 3)."""
        return self.score is not None


def _normalize(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def _alias_present(haystack: str, alias: str) -> bool:
    """Латинские сокращения ищутся по границам слова (чтобы "api" не ловилось в "capital"),
    кириллица и конструкции с дефисом --- по вхождению.
    """
    if _LATIN_ALIAS.fullmatch(alias):
        pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return alias in haystack


def extract_skills(text: str, lexicon: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """Вытащить навыки/технологии из текста заказа по лексикону."""
    lexicon = lexicon or SKILL_LEXICON
    haystack = _normalize(text)
    found = [
        skill
        for skill, aliases in lexicon.items()
        if any(_alias_present(haystack, _normalize(alias)) for alias in aliases)
    ]
    return sorted(found)


def compute_match_score(
    order_skills: list[str], profile_skills: list[str]
) -> float | None:
    """Чистая функция расчёта соответствия заказа профилю (ТЗ §32).

    Покрытие требований заказа: доля требуемых навыков, которые есть в профиле.
    Возвращает None (а не 0), если данных не хватает --- "нет данных" != "нулевое совпадение".
    """
    if not order_skills or not profile_skills:
        return None
    required = {skill.strip().lower() for skill in order_skills if skill and skill.strip()}
    available = {skill.strip().lower() for skill in profile_skills if skill and skill.strip()}
    if not required or not available:
        return None
    return round(len(required & available) / len(required), 4)


def match_order_to_profile(
    order_skills: list[str], profile_skills: list[str]
) -> MatchOutcome:
    """Полное сопоставление: совпавшие/недостающие навыки + score + объяснение."""
    if not order_skills:
        return MatchOutcome(
            matched_skills=[],
            missing_skills=[],
            score=None,
            reason="Не удалось определить требуемые навыки из текста заказа",
        )
    if not profile_skills:
        return MatchOutcome(
            matched_skills=[],
            missing_skills=list(order_skills),
            score=None,
            reason="В профиле исполнителя не заполнены навыки",
        )

    available = {skill.strip().lower(): skill for skill in profile_skills if skill.strip()}
    matched: list[str] = []
    missing: list[str] = []
    for skill in order_skills:
        key = skill.strip().lower()
        if key in available:
            matched.append(available[key])
        else:
            missing.append(skill)

    score = compute_match_score(order_skills, profile_skills)
    if score is None:
        return MatchOutcome(matched_skills=matched, missing_skills=missing, score=None,
                            reason="Недостаточно данных для расчёта соответствия")
    if missing:
        reason = (
            f"Совпало {len(matched)} из {len(order_skills)} требуемых навыков; "
            f"не хватает: {', '.join(missing)}"
        )
    else:
        reason = f"Полное совпадение по {len(matched)} требуемым навыкам"
    return MatchOutcome(matched_skills=matched, missing_skills=missing, score=score, reason=reason)
