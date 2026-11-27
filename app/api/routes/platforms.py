"""API тарифов площадок: сколько стоит попытка откликнуться и где это записано.

Тариф общий для площадки, поэтому он отдаётся как справочник: дата проверки, ссылка на
источник и оговорки там, где цена закрыта кабинетом. Экономика решения берёт отсюда
«цену отклика», а не догадку пользователя.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.domain.platform_tariffs import Offer, Platform, checked_at, find, platforms

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


class PlatformListOut(BaseModel):
    checked_at: str
    note: str
    platforms: list[PlatformOut]


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


def _to_out(platform: Platform) -> PlatformOut:
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
    )


@router.get("", response_model=PlatformListOut, summary="Тарифы площадок на отклики")
def list_platforms() -> PlatformListOut:
    payload = PlatformListOut(
        checked_at=checked_at(),
        note="Тариф одинаков для всех исполнителей площадки; цифры сверены на открытых страницах.",
        platforms=[_to_out(item) for item in platforms()],
    )
    return payload


@router.get("/{key}", response_model=PlatformOut, summary="Тариф одной площадки")
def get_platform(key: str) -> PlatformOut:
    platform = find(key)
    if platform is None:
        raise HTTPException(status_code=404, detail=f"Площадка «{key}» неизвестна")
    return _to_out(platform)
