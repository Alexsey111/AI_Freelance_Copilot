"""Маскирование персональных данных на границе «код → модель».

Зачем отдельный модуль. Запрос уходит внешнему провайдеру (proxyapi → OpenAI, серверы за
пределами РФ), и всё, что попало в промпт, юридически считается переданным. Поэтому маска
ставится в одном месте — при сборке промпта, — чтобы ни один адаптер (OpenAI, mock, будущий
локальный) не мог её обойти: адаптер получает уже обезличенный заказ.

Границы честности:

- поля, которые известны по имени (``client_name``, ``url``), вырезаются целиком;
- в свободном тексте ловятся телефон, почта, ссылка, telegram-ник, ФИО по шаблону
  «Фамилия Имя Отчество» и «Фамилия И.О.», адрес по сокращениям (г., ул., д., кв.);
- НЕ ловится: адрес без сокращений, ФИО из двух слов, редкая комбинация признаков
  («единственный бухгалтер завода в Барнауле»). Это записано в правовом паспорте проекта:
  маска снижает объём передачи, но не делает данные обезличенными по ст. 3 152-ФЗ.
"""

from __future__ import annotations

import re

MASK_PHONE = "[телефон]"
MASK_EMAIL = "[почта]"
MASK_LINK = "[ссылка]"
MASK_NAME = "[имя]"
MASK_ADDRESS = "[адрес]"
MASK_CLIENT = "[клиент]"

# Ссылки и мессенджеры: в них бывает и ник, и номер, и профиль — проще убрать целиком.
_LINK = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|(?:t\.me|telegram\.me|vk\.com|wa\.me|instagram\.com|avito\.ru)/\S+",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
_TELEGRAM = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{4,31}\b")

# Телефон: +7/8 и ровно 10 цифр с любыми разделителями, плюс слитная запись из 11 цифр.
_PHONE = re.compile(r"(?<![\d+])(?:\+7|8)[\s\-()]*\d(?:[\s\-()]*\d){9}(?!\d)")
_PHONE_BARE = re.compile(r"(?<!\d)\d{11}(?!\d)")

# ФИО: три слова с заглавной (Фамилия Имя Отчество) и «Фамилия И.О.».
_FIO_FULL = re.compile(r"\b[А-ЯЁ][а-яё-]{2,}(?:\s+[А-ЯЁ][а-яё-]{2,}){2}\b")
_FIO_INITIALS = re.compile(r"\b[А-ЯЁ][а-яё-]{2,}\s+[А-ЯЁ]\.(?:\s?[А-ЯЁ]\.)?")

# Адрес: только по сокращениям. «Дом культуры» и «городской округ» не трогаем намеренно.
_ADDRESS = re.compile(r"\b(?:г\.|ул\.|пер\.|пр-т|д\.|кв\.)\s*[А-ЯЁ0-9][^,.;\n]{0,30}")


def mask_personal_data(text: str | None) -> str | None:
    """Заменить персональные данные в тексте на плейсхолдеры. ``None`` остаётся ``None``."""
    if not text:
        return text
    result = _LINK.sub(MASK_LINK, text)
    result = _EMAIL.sub(MASK_EMAIL, result)
    result = _TELEGRAM.sub(MASK_LINK, result)
    result = _PHONE.sub(MASK_PHONE, result)
    result = _PHONE_BARE.sub(MASK_PHONE, result)
    result = _FIO_FULL.sub(MASK_NAME, result)
    result = _FIO_INITIALS.sub(MASK_NAME, result)
    result = _ADDRESS.sub(MASK_ADDRESS, result)
    return result


def mask_order_payload(payload: dict) -> dict:
    """Обезличить поля заказа перед отправкой в модель.

    Числа (бюджет, id) не трогаем: они нужны для оценки, а сами по себе не идентифицируют
    человека. ``missing_data`` считается по исходному тексту — иначе маска съест длину
    описания и правило «не хватает данных» начнёт срабатывать ложно.
    """
    masked = dict(payload)
    if masked.get("client_name") is not None:
        masked["client_name"] = MASK_CLIENT
    if masked.get("url") is not None:
        masked["url"] = MASK_LINK
    for key in ("title", "description"):
        if isinstance(masked.get(key), str):
            masked[key] = mask_personal_data(masked[key])
    return masked
