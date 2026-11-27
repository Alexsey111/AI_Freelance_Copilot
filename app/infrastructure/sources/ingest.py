"""Загрузка заказов с площадок в базу: дедупликация, обновление счётчиков, отчёт.

Ключ дедупликации — `source + external_id`. Второй прогон того же парсера не должен
создавать дубли, но должен обновлять то, что меняется на площадке: число откликов,
просмотры, иногда бюджет и заголовок (заказчик правит текст).

Заказ без `external_id` пропускается: без него нечем доказать, что это тот же заказ,
и повторный прогон создаст копию — лучше честно сказать «пропущено», чем плодить дубли.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.models.order import Order
from app.infrastructure.sources.base import ExternalOrder, normalize_external_order


@dataclass(slots=True)
class IngestStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    unchanged: int = 0
    touched_views: int = 0
    new_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "unchanged": self.unchanged,
            "touched_views": self.touched_views,
            "new_ids": self.new_ids,
            "errors": self.errors,
        }


# Поля, которые обновляются при повторной встрече с заказом. Статус и решение человека
# здесь намеренно отсутствуют: парсер не имеет права переписывать приёмку.
def _as_utc(moment: datetime) -> datetime:
    """В базе время лежит без зоны (SQLite), у источника — с зоной. Сравнивать можно только
    приведя оба к UTC: иначе вычитание падает на «naive and aware»."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


REFRESHABLE = ("title", "description", "budget_min", "budget_max", "url", "views", "responses")


def _changed(existing: Order, fresh: Order) -> list[str]:
    changed = []
    for name in REFRESHABLE:
        new_value = getattr(fresh, name)
        if new_value in (None, "") and getattr(existing, name) not in (None, ""):
            continue
        if getattr(existing, name) != new_value:
            changed.append(name)
    if existing.published_at is None and fresh.published_at is not None:
        changed.append("published_at")
    elif existing.published_at and fresh.published_at:
        # Площадка иногда называет время в другой зоне или правит его. Расхождение больше
        # десяти минут — повод переписать, иначе старый сдвиг останется навсегда.
        drift = abs(
            (_as_utc(fresh.published_at) - _as_utc(existing.published_at)).total_seconds()
        )
        if drift > 600:
            changed.append("published_at")
    return changed


def ingest_orders(
    external_orders: list[ExternalOrder],
    repository,
    *,
    min_description_chars: int = 40,
) -> IngestStats:
    """Сохраняет заказы в базу, не плодя дублей и не затирая решения человека."""
    stats = IngestStats(fetched=len(external_orders))
    for external in external_orders:
        if not external.external_id:
            stats.skipped += 1
            stats.errors.append(f"{external.source}: заказ без внешнего id — пропущен")
            continue
        try:
            fresh = normalize_external_order(external, min_description_chars=min_description_chars)
            existing = repository.find_by_external(fresh.source, fresh.external_id)
        except Exception as error:  # noqa: BLE001 — один битый заказ не должен рушить прогон
            stats.skipped += 1
            stats.errors.append(f"{external.source}/{external.external_id}: {error}")
            continue

        if existing is None:
            created = repository.add(fresh, raw_input=external.raw or None)
            stats.created += 1
            if created.id is not None:
                stats.new_ids.append(created.id)
            continue

        changed = _changed(existing, fresh)
        if not changed:
            # Заказ уже был и не изменился: это не «пропущено» и не «обновлено» —
            # третий счётчик, чтобы повторный прогон не выглядел как потеря данных.
            stats.unchanged += 1
            continue
        for name in changed:
            setattr(existing, name, getattr(fresh, name))
        existing.updated_at = datetime.now(UTC)
        repository.save(existing)
        stats.updated += 1
        if "views" in changed or "responses" in changed:
            stats.touched_views += 1
    return stats
