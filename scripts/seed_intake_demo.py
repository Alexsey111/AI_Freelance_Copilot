#!/usr/bin/env python3
"""Залить демо-профиль компании и 20 входящих заявок в отдельную базу.

Зачем: ядро умеет два домена. Фриланс — профиль исполнителя и заказы с биржи.
Заявки — профиль компании (что продаёт, регионы, минимум, чего не делает) и
входящие письма, по которым нужно решение «в работу / отказ / человеку».

Домен включается профилем: `preferences.domain = "intake"`. Тогда ядро берёт
промпт `prompts/request_triage.txt`, лексикон товаров из `preferences.skill_lexicon`
и не требует бюджет в каждой заявке (`preferences.require_budget = false`).

Запуск (база отдельная, рабочие данные не трогаются):

    DATABASE_URL="sqlite:///./data/intake-demo.db" \\
        ./.venv/Scripts/python.exe scripts/seed_intake_demo.py

Повторный запуск дублей не делает: заявка ищется по (source, external_id).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIELDS = ("name", "summary", "skills", "experience", "preferences")


def main() -> int:
    parser = argparse.ArgumentParser(description="Демо-база: заявки компании")
    parser.add_argument("--db", help="sqlite URL или путь к файлу; иначе DATABASE_URL/.env")
    parser.add_argument("--profile", default=str(ROOT / "data" / "company-profile.json"))
    parser.add_argument("--requests", default=str(ROOT / "tests_data" / "business_requests.json"))
    args = parser.parse_args()

    if args.db:
        url = args.db if args.db.startswith("sqlite") else f"sqlite:///{Path(args.db).as_posix()}"
        os.environ["DATABASE_URL"] = url

    from app.config import get_settings  # noqa: E402  (после подмены DATABASE_URL)
    from app.domain.models.order import Order  # noqa: E402
    from app.infrastructure.database.database import Database  # noqa: E402
    from app.infrastructure.database.models import ProfileModel  # noqa: E402
    from app.infrastructure.database.repositories import (  # noqa: E402
        OrderRepository,
        ProfileRepository,
    )

    profile_payload = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    requests_payload = json.loads(Path(args.requests).read_text(encoding="utf-8"))

    settings = get_settings()
    database = Database(settings.database_url)
    database.create_all()

    added = skipped = 0
    with database.session() as session:
        profile = ProfileRepository(session).ensure_default()
        model = session.get(ProfileModel, profile.id)
        if model is None:  # pragma: no cover - ensure_default создаёт профиль
            raise SystemExit("Профиль не создан")
        for field in FIELDS:
            if field in profile_payload:
                setattr(model, field, profile_payload[field])
        session.flush()

        orders = OrderRepository(session)
        for item in requests_payload:
            source = item.get("source", "email")
            external_id = item["external_id"]
            if orders.find_by_external(source, external_id) is not None:
                skipped += 1
                continue
            orders.add(
                Order(
                    external_id=external_id,
                    source=source,
                    title=item["title"],
                    description=item["description"],
                    budget_min=item.get("budget_min"),
                    budget_max=item.get("budget_max"),
                    client_name=item.get("client_name"),
                )
            )
            added += 1

        print(f"База: {settings.database_url}")
        print(f"Профиль #{model.id}: {model.name}")
        print(f"  домен: {(model.preferences or {}).get('domain', 'freelance')}")
        print(f"  товаров/навыков: {len(model.skills or [])}")
        print(f"  минимум заказа: {(model.preferences or {}).get('min_budget_rub')} ₽")
        print(f"Заявок добавлено: {added}, уже было: {skipped}, всего в базе: {orders.count_all()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
