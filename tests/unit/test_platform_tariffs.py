"""Тарифы площадок: цифры с источником, а не «примерно столько».

Правило: цена попытки входит в экономику заказа, поэтому она должна быть либо проверена
на сайте площадки, либо честно помечена как закрытая кабинетом. Ноль вместо «неизвестно»
недопустим — он молча занижает стоимость отклика.
"""

from __future__ import annotations

import pytest

from app.domain.platform_tariffs import (
    BLOCKED,
    DATA_FILE,
    PARTIAL,
    VERIFIED,
    checked_at,
    find,
    platforms,
)


def test_catalog_has_date_and_sources():
    assert checked_at() == "2026-11-27"
    for platform in platforms():
        assert platform.source.startswith("https://"), platform.key
        assert platform.status in {VERIFIED, PARTIAL, BLOCKED}
        assert platform.free_note, f"{platform.key}: без пояснения про бесплатный лимит"


def test_fl_ru_package_prices_per_response():
    """FL.ru: 20 откликов за 1 000 ₽ — 50 ₽ за попытку; 30 и 60 откликов — по 80 ₽."""
    fl = find("flru")
    assert fl is not None
    by_quota = {offer.quota: offer.per_response for offer in fl.packages}
    assert by_quota == {20: 50.0, 30: 80.0, 60: 80.0}
    assert fl.single_response == 80.0
    assert fl.best_price == 50.0
    assert fl.best_currency == "RUB"


def test_freelance_ru_has_subscriptions_and_packages():
    ru = find("freelance_ru")
    assert ru is not None
    assert {offer.title: offer.price for offer in ru.packages}["10 откликов / 30 дней"] == 500
    premium = next(offer for offer in ru.subscription if offer.title == "Премиум")
    assert premium.price == 1500
    assert premium.per_response == 50.0
    assert ru.free_note.startswith("Обычный аккаунт бесплатный")


def test_kwork_counts_connections_as_free_quota():
    kwork = find("kwork")
    assert kwork is not None
    assert kwork.free_per_month == 20
    assert kwork.best_price is None  # цена докупки публично не заявлена
    assert kwork.status == PARTIAL


def test_foreign_platforms_keep_their_currency():
    freelancer = find("freelancer")
    assert freelancer is not None
    assert freelancer.best_currency == "USD"
    assert freelancer.free_per_month == 6
    assert freelancer.best_price == 0.1


def test_upwork_is_marked_as_unavailable():
    upwork = find("upwork")
    assert upwork is not None
    assert upwork.status == BLOCKED
    assert "IP/Country Block" in upwork.free_note


def test_unknown_platform_is_none():
    assert find("hh-ru") is None


def test_data_file_is_valid_json_with_platforms():
    import json

    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert payload["checked_at"]
    assert len(payload["platforms"]) >= 6


@pytest.mark.parametrize("key", ["flru", "freelance_ru", "kwork", "freelancer", "peopleperhour"])
def test_each_platform_explains_its_model(key):
    platform = find(key)
    assert platform is not None
    assert platform.model
    assert platform.status_label
