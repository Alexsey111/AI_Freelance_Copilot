"""API тарифов площадок: сколько стоит попытка откликнуться и где это записано.

Тариф общий для площадки, поэтому он отдаётся как справочник: дата проверки, ссылка на
источник и оговорки там, где цена закрыта кабинетом. Экономика решения берёт отсюда
«цену отклика», а не догадку пользователя.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.domain.platform_tariffs import Offer, Platform, checked_at, find, platforms
from app.infrastructure.database.repositories.platform_preference_repository import (
    PlatformPreferenceRepository,
)

router = APIRouter(prefix="/platforms", tags=["platforms"])


class OfferOut(BaseModel):
    title: str
    quota: int | None = None
    price: float
    currency: str
    days: int | None = None
    note: str | None = None
    per_response: float | None = None


class ExtraOut(BaseModel):
    title: str
    price: float | str
    unit: str
    currency: str = "RUB"


class PlatformOut(BaseModel):
    key: str
    title: str
    country: str
    status: str
    status_label: str
    model: str
    free_per_month: int | None = None
    free_note: str
    packages: list[OfferOut]
    subscription: list[OfferOut]
    single_response: float | None = None
    single_note: str | None = None
    extra: list[ExtraOut]
    best_price: float | None = None
    best_price_title: str | None = None
    best_price_currency: str = "RUB"
    source: str
    caveat: str | None = None
    currency: str = "RUB"
    enabled: bool = True
    paid_warning: str | None = None


class PlatformListOut(BaseModel):
    checked_at: str
    note: str
    platforms: list[PlatformOut]
    enabled_count: int
    paid_warning: str | None = None


class PlatformToggleIn(BaseModel):
    enabled: bool


def _offer(offer: Offer, currency: str) -> OfferOut:
    return OfferOut(
        title=offer.title,
        quota=offer.quota,
        price=offer.price,
        currency=offer.currency or currency,
        days=offer.days,
        note=offer.note,
        per_response=offer.per_response,
    )


def _money(value: float, currency: str) -> str:
    # Русская запись: 5,83 ₽, а не 5.83 ₽ — иначе цифра выглядит как машинный вывод.
    number = f"{value:g}".replace(".", ",")
    return f"{number} $" if currency == "USD" else f"{number} ₽"


def _warning(platform: Platform) -> str | None:
    """Предупреждение о платности отклика — словами, а не значком без объяснения."""
    if platform.status == "blocked":
        return f"{platform.title} недоступна из России — заказы оттуда не придут."
    if platform.best_price is None:
        return (
            f"{platform.title}: цена отклика не известна — она видна только в кабинете. "
            "Пока цифра не подтверждена, расходы считайте вручную."
        )
    money = _money(platform.best_price, platform.best_currency)
    if platform.best_kind == "subscription":
        best = platform.best_per_response
        plan = f"{best.title}, {_money(best.price, best.currency)}" if best else "подписка"
        return (
            f"{platform.title}: отклики по подписке — {plan}. "
            f"Это {money} за попытку, но платите вперёд за весь период."
        )
    return (
        f"{platform.title}: отклик платный — {money} за попытку. "
        "Деньги списываются при отправке, даже если заказчик не ответил."
    )


def _to_out(platform: Platform, enabled: bool) -> PlatformOut:
    best = platform.best_per_response
    return PlatformOut(
        key=platform.key,
        title=platform.title,
        country=platform.country,
        status=platform.status,
        status_label=platform.status_label,
        model=platform.model,
        free_per_month=platform.free_per_month,
        free_note=platform.free_note,
        packages=[_offer(item, platform.currency) for item in platform.packages],
        subscription=[_offer(item, platform.currency) for item in platform.subscription],
        single_response=platform.single_response,
        single_note=platform.single_note,
        extra=[
            ExtraOut(
                title=item["title"],
                price=item["price"],
                unit=item.get("unit", ""),
                currency=item.get("currency", platform.currency),
            )
            for item in platform.extra
        ],
        best_price=platform.best_price,
        best_price_title=best.title if best else platform.single_note,
        best_price_currency=platform.best_currency,
        source=platform.source,
        caveat=platform.caveat,
        currency=platform.currency,
        enabled=enabled,
        paid_warning=_warning(platform),
    )


@router.get("", response_model=PlatformListOut, summary="Тарифы площадок и выбор пользователя")
def list_platforms(session: Session = Depends(get_session)) -> PlatformListOut:
    repository = PlatformPreferenceRepository(session)
    chosen = repository.ensure_seeded(platforms())
    session.commit()
    items = [_to_out(item, chosen.get(item.key, True)) for item in platforms()]
    active = [item for item in items if item.enabled]
    paid = [item for item in active if item.best_price is not None]
    warning = None
    if paid:
        prices = ", ".join(
            f"{item.title} — {_money(item.best_price, item.best_price_currency)}" for item in paid
        )
        warning = (
            f"Выбрано площадок: {len(active)}. Отклики платные: {prices}. "
            "Каждая отправка — расход, а не бесплатное действие."
        )
    return PlatformListOut(
        checked_at=checked_at(),
        note="Тариф одинаков для всех исполнителей площадки; цифры сверены на открытых страницах.",
        platforms=items,
        enabled_count=len(active),
        paid_warning=warning,
    )


@router.put(
    "/{key}/enabled", response_model=PlatformOut, summary="Включить или отключить площадку"
)
def toggle_platform(
    key: str, payload: PlatformToggleIn, session: Session = Depends(get_session)
) -> PlatformOut:
    platform = find(key)
    if platform is None:
        raise HTTPException(status_code=404, detail=f"Площадка «{key}» неизвестна")
    repository = PlatformPreferenceRepository(session)
    repository.ensure_seeded(platforms())
    enabled = repository.set(key, payload.enabled)
    session.commit()
    return _to_out(platform, enabled)


@router.get("/{key}", response_model=PlatformOut, summary="Тариф одной площадки")
def get_platform(key: str, session: Session = Depends(get_session)) -> PlatformOut:
    platform = find(key)
    if platform is None:
        raise HTTPException(status_code=404, detail=f"Площадка «{key}» неизвестна")
    chosen = PlatformPreferenceRepository(session).ensure_seeded(platforms())
    session.commit()
    return _to_out(platform, chosen.get(key, True))
