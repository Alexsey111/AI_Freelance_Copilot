"""Репозиторий настроек: чтение, запись с историей, сброс к значению по умолчанию.

Приоритет значений: база -> переменные окружения -> значение по умолчанию (из реестра
правил). База главнее, потому что её меняет владелец программы; окружение — это то,
что задал администратор при установке; реестр — заводские значения.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.domain.rules import RULES, format_value
from app.infrastructure.database.models import SettingAuditModel, SettingModel

SOURCE_DB = "настройка"
SOURCE_ENV = "окружение"
SOURCE_DEFAULT = "по умолчанию"


@dataclass(slots=True)
class ResolvedSetting:
    key: str
    raw: str | None
    source: str


class SettingsRepository:
    def __init__(self, session) -> None:
        self.session = session

    def raw_values(self) -> dict[str, str]:
        rows = self.session.execute(select(SettingModel)).scalars().all()
        return {row.key: row.value for row in rows}

    def resolve(self, env_values: dict[str, str] | None = None) -> dict[str, ResolvedSetting]:
        """Итоговое значение каждого правила и откуда оно взялось."""
        stored = self.raw_values()
        env = env_values or {}
        resolved: dict[str, ResolvedSetting] = {}
        for key, rule in RULES.items():
            if key in stored:
                resolved[key] = ResolvedSetting(key, stored[key], SOURCE_DB)
            elif key in env:
                resolved[key] = ResolvedSetting(key, env[key], SOURCE_ENV)
            else:
                default = rule.default
                raw = None if default is None else format_value(default)
                resolved[key] = ResolvedSetting(key, raw, SOURCE_DEFAULT)
        return resolved

    def set(self, key: str, raw: str, *, changed_by: str = "user") -> ResolvedSetting:
        """Записать значение и оставить след в истории. Проверку типа делает вызывающий."""
        model = self.session.get(SettingModel, key)
        old_raw = model.value if model else None
        if model is None:
            model = SettingModel(key=key, value=raw, updated_by=changed_by)
            self.session.add(model)
        else:
            model.value = raw
            model.updated_by = changed_by
            model.updated_at = datetime.now(UTC)
        self.session.add(
            SettingAuditModel(
                key=key,
                old_value=old_raw,
                new_value=raw,
                changed_at=datetime.now(UTC),
                changed_by=changed_by,
            )
        )
        self.session.flush()
        return ResolvedSetting(key, raw, SOURCE_DB)

    def reset(self, key: str, *, changed_by: str = "user") -> ResolvedSetting | None:
        """Вернуть значение по умолчанию: строку из базы удалить, историю сохранить."""
        rule = RULES.get(key)
        if rule is None:
            return None
        model = self.session.get(SettingModel, key)
        old_raw = model.value if model else None
        if model is not None:
            self.session.execute(delete(SettingModel).where(SettingModel.key == key))
        self.session.add(
            SettingAuditModel(
                key=key,
                old_value=old_raw,
                new_value=None,
                changed_at=datetime.now(UTC),
                changed_by=changed_by,
            )
        )
        self.session.flush()
        default = rule.default
        return ResolvedSetting(
            key, None if default is None else format_value(default), SOURCE_DEFAULT
        )

    def history(self, key: str | None = None, limit: int = 50) -> list[SettingAuditModel]:
        stmt = select(SettingAuditModel).order_by(SettingAuditModel.id.desc()).limit(limit)
        if key:
            stmt = stmt.where(SettingAuditModel.key == key)
        return list(self.session.execute(stmt).scalars().all())
