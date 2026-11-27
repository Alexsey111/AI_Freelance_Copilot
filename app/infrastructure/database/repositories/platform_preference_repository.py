"""Выбор площадок: какие включаем в работу, какие нет.

По умолчанию включены все площадки, кроме недоступных из страны (Upwork отдаёт
IP/Country Block). Пустая база — не «ничего не выбрано»: при первом обращении площадки
досеиваются, иначе новый пользователь увидел бы пустой список заказов и решил, что
программа сломана.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.infrastructure.database.models import PlatformPreferenceModel


class PlatformPreferenceRepository:
    def __init__(self, session) -> None:
        self.session = session

    def ensure_seeded(self, platforms) -> dict[str, bool]:
        """Добавляет отсутствующие площадки: включены все, кроме заблокированных."""
        existing = set(self.session.execute(select(PlatformPreferenceModel.platform_key)).scalars())
        changed = False
        for platform in platforms:
            if platform.key in existing:
                continue
            enabled = platform.status != "blocked"
            self.session.add(
                PlatformPreferenceModel(
                    platform_key=platform.key,
                    enabled=enabled,
                    updated_at=datetime.now(UTC),
                )
            )
            changed = True
        if changed:
            self.session.flush()
        return self.all()

    def all(self) -> dict[str, bool]:
        rows = self.session.execute(select(PlatformPreferenceModel)).scalars().all()
        return {row.platform_key: bool(row.enabled) for row in rows}

    def set(self, key: str, enabled: bool) -> bool:
        row = self.session.get(PlatformPreferenceModel, key)
        if row is None:
            row = PlatformPreferenceModel(
                platform_key=key, enabled=enabled, updated_at=datetime.now(UTC)
            )
            self.session.add(row)
        else:
            row.enabled = enabled
            row.updated_at = datetime.now(UTC)
        self.session.flush()
        return bool(row.enabled)

    def enabled_keys(self) -> list[str]:
        rows = self.session.execute(
            select(PlatformPreferenceModel.platform_key).where(
                PlatformPreferenceModel.enabled.is_(True)
            )
        ).scalars()
        return sorted(rows)
