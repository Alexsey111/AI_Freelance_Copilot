#!/usr/bin/env python3
"""Записать профиль исполнителя в активный профиль ядра.

Зачем: в API есть правка только списка навыков, а порог бюджета, стек и список
«чего не беру» живут в `preferences` и в промпт попадают оттуда. Без них модель
не знает ограничений владельца и предлагает заказы ниже его минимума.

Запуск (база — та же, что у ядра, которое вы поднимаете):

    DATABASE_URL="sqlite:///./data/live.db" \
        ./.venv/Scripts/python.exe scripts/seed_profile.py --file data/profile.json

Скрипт правит только активный профиль (имя, описание, навыки, опыт, предпочтения),
заказы и анализы не трогает.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.infrastructure.database.database import Database  # noqa: E402
from app.infrastructure.database.models import ProfileModel  # noqa: E402
from app.infrastructure.database.repositories import ProfileRepository  # noqa: E402

FIELDS = ("name", "summary", "skills", "experience", "preferences")


def main() -> int:
    parser = argparse.ArgumentParser(description="Заполнить активный профиль из JSON")
    parser.add_argument("--file", default=str(ROOT / "data" / "profile.json"))
    args = parser.parse_args()

    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    unknown = set(payload) - set(FIELDS) - {"portfolio", "note", "role"}
    if unknown:
        print(f"В файле есть поля, которых скрипт не знает: {sorted(unknown)}", file=sys.stderr)

    settings = get_settings()
    database = Database(settings.database_url)
    database.create_all()

    with database.session() as session:
        profile = ProfileRepository(session).ensure_default()
        model = session.get(ProfileModel, profile.id)
        for field in FIELDS:
            if field in payload:
                setattr(model, field, payload[field])
        if "portfolio" in payload:
            model.portfolio = payload["portfolio"]
        session.flush()
        session.refresh(model)

        print(f"База: {settings.database_url}")
        print(f"Профиль #{model.id}: {model.name}")
        print(f"  навыков: {len(model.skills or [])}")
        preferences = model.preferences or {}
        floor = preferences.get("min_budget_rub", preferences.get("min_budget"))
        print(f"  минимальный бюджет: {floor}")
        print(f"  чего не беру: {', '.join(preferences.get('avoid', [])) or '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
