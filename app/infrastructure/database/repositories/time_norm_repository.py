"""Репозиторий норм времени по типам задач (миграция 0009)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.domain.time_norms import DEFAULT_NORMS, Norm
from app.infrastructure.database.models import TimeNormModel


def _to_domain(model: TimeNormModel) -> Norm:
    try:
        keywords = json.loads(model.keywords or "[]")
    except json.JSONDecodeError:
        keywords = []
    return Norm(
        task_kind=model.task_kind,
        title=model.title,
        hours=float(model.hours),
        keywords=[str(k) for k in keywords],
        note=model.note,
    )


class TimeNormRepository:
    def __init__(self, session) -> None:
        self.session = session

    def list(self) -> list[Norm]:
        stmt = select(TimeNormModel).order_by(TimeNormModel.hours)
        return [_to_domain(model) for model in self.session.execute(stmt).scalars().all()]

    def ensure_seeded(self) -> list[Norm]:
        """Досеивает недостающие заводские нормы, не трогая уже изменённые.

        Важно не «заполнить пустую таблицу», а «добавить то, чего нет»: иначе новая
        версия программы приносит нормы для копирайтера, а у пользователя с прежней
        установкой их не появится никогда — таблица уже не пустая.
        """
        existing = {norm.task_kind for norm in self.list()}
        added = False
        for item in DEFAULT_NORMS:
            if item["task_kind"] in existing:
                continue
            self.session.add(
                TimeNormModel(
                    task_kind=item["task_kind"],
                    title=item["title"],
                    hours=float(item["hours"]),
                    keywords=json.dumps(item["keywords"], ensure_ascii=False),
                    note=item.get("note"),
                )
            )
            added = True
        if added:
            self.session.flush()
        return self.list()

    def upsert(self, task_kind: str, *, title: str, hours: float, keywords=None) -> Norm:
        model = self.session.get(TimeNormModel, task_kind)
        if model is None:
            model = TimeNormModel(
                task_kind=task_kind,
                title=title,
                hours=hours,
                keywords=json.dumps(keywords or [], ensure_ascii=False),
            )
            self.session.add(model)
        else:
            model.title = title
            model.hours = hours
            if keywords is not None:
                model.keywords = json.dumps(keywords, ensure_ascii=False)
            model.updated_at = datetime.now(UTC)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def delete(self, task_kind: str) -> bool:
        result = self.session.execute(
            delete(TimeNormModel).where(TimeNormModel.task_kind == task_kind)
        )
        self.session.flush()
        return bool(result.rowcount)
