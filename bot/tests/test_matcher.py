from __future__ import annotations

import uuid

import pytest

from app.db.enums import Platform
from app.db.models import Search, User
from app.services.matcher import MarketplaceItem, MatchResult, find_matches_in_memory


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def mercari_user() -> User:
    return User(telegram_id=111111, id=uuid.uuid4())


@pytest.fixture
def another_user() -> User:
    return User(telegram_id=222222, id=uuid.uuid4())


@pytest.fixture
def iphone_item() -> MarketplaceItem:
    return MarketplaceItem(
        platform="mercari",
        name="iPhone 15 Pro 256GB Black",
        price=120000,
        url="https://jp.mercari.com/item/m123",
    )


def _make_search(
    user: User,
    keyword: str = "iPhone",
    platform: Platform = Platform.MERCARI,
    price_min: int | None = None,
    price_max: int | None = None,
) -> Search:
    return Search(
        id=uuid.uuid4(),
        platform=platform,
        keyword=keyword,
        price_min=price_min,
        price_max=price_max,
        user=user,
    )


# ── Platform matching ──────────────────────────────────────────────────

def test_no_searches_returns_empty(iphone_item: MarketplaceItem) -> None:
    assert find_matches_in_memory(iphone_item, []) == []


def test_platform_mismatch_no_match(iphone_item: MarketplaceItem, mercari_user: User) -> None:
    """Товар с mercari не должен матчиться на поиск с platform=paypay."""
    # Нет других платформ в enum, но Platform это str-Enum — функция
    # сравнивает search.platform.value с item.platform (строка).
    # Создаём поиск, у которого platform.value != item.platform.
    search = _make_search(mercari_user, platform=Platform.MERCARI, keyword="iPhone")
    search.platform = Platform.MERCARI  # mercari == mercari → match

    iphone_item.platform = "paypay"  # другая платформа
    assert find_matches_in_memory(iphone_item, [search]) == []


def test_platform_match(iphone_item: MarketplaceItem, mercari_user: User) -> None:
    search = _make_search(mercari_user)
    result = find_matches_in_memory(iphone_item, [search])
    assert len(result) == 1
    assert result[0] == MatchResult(user_id=mercari_user.telegram_id, keyword="iPhone")


# ── Keyword matching ────────────────────────────────────────────────────

def test_exact_keyword_case_insensitive(iphone_item: MarketplaceItem, mercari_user: User) -> None:
    """Ключевое слово 'iphone' (нижний регистр) находит 'iPhone 15 Pro'."""
    search = _make_search(mercari_user, keyword="iphone")
    result = find_matches_in_memory(iphone_item, [search])
    assert len(result) == 1


def test_keyword_uppercase_finds_lowercase(mercari_user: User) -> None:
    """Ключевое слово 'IPHONE' (верхний регистр) находит 'iphone' в названии."""
    item = MarketplaceItem(
        platform="mercari",
        name="iphone 15 pro",
        price=120000,
        url="https://jp.mercari.com/item/m123",
    )
    search = _make_search(mercari_user, keyword="IPHONE")
    assert len(find_matches_in_memory(item, [search])) == 1


def test_keyword_substring_match(mercari_user: User) -> None:
    """Ключевое слово — часть названия товара."""
    item = MarketplaceItem(
        platform="mercari",
        name="Nintendo Switch OLED (New)",
        price=38000,
        url="https://jp.mercari.com/item/m456",
    )
    search = _make_search(mercari_user, keyword="Switch")
    assert len(find_matches_in_memory(item, [search])) == 1


def test_keyword_not_found(iphone_item: MarketplaceItem, mercari_user: User) -> None:
    """Ключевое слово отсутствует в названии."""
    search = _make_search(mercari_user, keyword="Samsung")
    assert find_matches_in_memory(iphone_item, [search]) == []


def test_keyword_is_longer_than_item_name(mercari_user: User) -> None:
    """Если ключевое слово длиннее названия — нет матча."""
    item = MarketplaceItem(
        platform="mercari",
        name="短い",  # Короткое японское название
        price=500,
        url="https://jp.mercari.com/item/m789",
    )
    search = _make_search(mercari_user, keyword="長いキーワード")
    assert find_matches_in_memory(item, [search]) == []


def test_japanese_keyword(mercari_user: User) -> None:
    """Японские ключевые слова работают корректно."""
    item = MarketplaceItem(
        platform="mercari",
        name="ポケモンカード リザードン PSA10",
        price=50000,
        url="https://jp.mercari.com/item/m999",
    )
    search = _make_search(mercari_user, keyword="ポケモン")
    assert len(find_matches_in_memory(item, [search])) == 1


# ── Price bounds ───────────────────────────────────────────────────────

def test_price_min_matches(mercari_user: User) -> None:
    """price_min=100000, товар 120000 → матч."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=120000, url="http://x.com/1")
    search = _make_search(mercari_user, price_min=100000)
    assert len(find_matches_in_memory(item, [search])) == 1


def test_price_min_exact_boundary(mercari_user: User) -> None:
    """price_min=120000, товар 120000 → матч (граничное значение)."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=120000, url="http://x.com/1")
    search = _make_search(mercari_user, price_min=120000)
    assert len(find_matches_in_memory(item, [search])) == 1


def test_price_min_too_low(mercari_user: User) -> None:
    """price_min=200000, товар 120000 → нет матча."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=120000, url="http://x.com/1")
    search = _make_search(mercari_user, price_min=200000)
    assert find_matches_in_memory(item, [search]) == []


def test_price_max_matches(mercari_user: User) -> None:
    """price_max=150000, товар 120000 → матч."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=120000, url="http://x.com/1")
    search = _make_search(mercari_user, price_max=150000)
    assert len(find_matches_in_memory(item, [search])) == 1


def test_price_max_too_high(mercari_user: User) -> None:
    """price_max=50000, товар 120000 → нет матча."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=120000, url="http://x.com/1")
    search = _make_search(mercari_user, price_max=50000)
    assert find_matches_in_memory(item, [search]) == []


def test_price_range_inside(mercari_user: User) -> None:
    """price_min=100000, price_max=150000, товар 120000 → матч."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=120000, url="http://x.com/1")
    search = _make_search(mercari_user, price_min=100000, price_max=150000)
    assert len(find_matches_in_memory(item, [search])) == 1


def test_no_price_bounds(mercari_user: User) -> None:
    """Без ограничений по цене любой товар матчится."""
    item = MarketplaceItem(platform="mercari", name="iPhone", price=999999, url="http://x.com/1")
    search = _make_search(mercari_user, price_min=None, price_max=None)
    assert len(find_matches_in_memory(item, [search])) == 1


# ── Regression: price_min=0 ────────────────────────────────────────────

def test_price_min_zero_allows_any_positive_price(mercari_user: User) -> None:
    """price_min=0 — это реальное ограничение, пропускает товары с ценой >= 0."""
    item = MarketplaceItem(platform="mercari", name="Cheap item", price=500, url="http://x.com/1")
    search = _make_search(mercari_user, keyword="Cheap", price_min=0)
    assert len(find_matches_in_memory(item, [search])) == 1


# ── Multiple matches ────────────────────────────────────────────────────

def test_one_item_matches_multiple_searches(mercari_user: User, another_user: User) -> None:
    """Один товар может подходить под несколько поисков разных пользователей."""
    item = MarketplaceItem(
        platform="mercari",
        name="iPhone 15 Pro 256GB Black",
        price=120000,
        url="https://jp.mercari.com/item/m123",
    )
    searches = [
        _make_search(mercari_user, keyword="iPhone"),
        _make_search(mercari_user, keyword="Pro"),
        _make_search(another_user, keyword="iPhone"),
    ]
    result = find_matches_in_memory(item, searches)
    assert len(result) == 3
    user_ids = {m.user_id for m in result}
    assert mercari_user.telegram_id in user_ids
    assert another_user.telegram_id in user_ids


def test_multiple_searches_only_one_matches(mercari_user: User) -> None:
    """Из трёх поисков только один релевантен."""
    item = MarketplaceItem(
        platform="mercari",
        name="PlayStation 5 Digital Edition",
        price=60000,
        url="https://jp.mercari.com/item/ps5",
    )
    searches = [
        _make_search(mercari_user, keyword="PlayStation"),
        _make_search(mercari_user, keyword="Xbox"),
        _make_search(mercari_user, keyword="Nintendo"),
    ]
    result = find_matches_in_memory(item, searches)
    assert len(result) == 1
    assert result[0].keyword == "PlayStation"


# ── Edge cases ─────────────────────────────────────────────────────────

def test_empty_item_name(mercari_user: User) -> None:
    """Товар с пустым названием не матчится ни на что."""
    item = MarketplaceItem(
        platform="mercari",
        name="",
        price=1000,
        url="https://jp.mercari.com/item/empty",
    )
    search = _make_search(mercari_user, keyword="anything")
    assert find_matches_in_memory(item, [search]) == []


def test_empty_keyword(mercari_user: User) -> None:
    """Пустое ключевое слово матчит любой товар (как in '' в любой строке)."""
    item = MarketplaceItem(
        platform="mercari",
        name="Some item",
        price=1000,
        url="https://jp.mercari.com/item/1",
    )
    search = _make_search(mercari_user, keyword="")
    # ''.lower() in 'some item' → True (пустая строка есть в любой строке)
    result = find_matches_in_memory(item, [search])
    assert len(result) == 1


def test_item_with_zero_price(mercari_user: User) -> None:
    """Товар с ценой 0 JPY (бесплатно)."""
    item = MarketplaceItem(
        platform="mercari",
        name="Free item",
        price=0,
        url="https://jp.mercari.com/item/free",
    )
    # Без ограничений по цене — матч
    search_no_bounds = _make_search(mercari_user, keyword="Free")
    assert len(find_matches_in_memory(item, [search_no_bounds])) == 1

    # С price_min=0 — тоже матч (0 >= 0)
    search_min_zero = _make_search(mercari_user, keyword="Free", price_min=0)
    assert len(find_matches_in_memory(item, [search_min_zero])) == 1

    # С price_min=1 — нет матча (0 < 1)
    search_min_one = _make_search(mercari_user, keyword="Free", price_min=1)
    assert find_matches_in_memory(item, [search_min_one]) == []


def test_very_long_keyword(mercari_user: User) -> None:
    """Очень длинное ключевое слово — граничный тест производительности."""
    item = MarketplaceItem(
        platform="mercari",
        name="Short name",
        price=1000,
        url="https://jp.mercari.com/item/1",
    )
    search = _make_search(mercari_user, keyword="x" * 10000)
    # Не должно упасть или зависнуть
    result = find_matches_in_memory(item, [search])
    assert result == []


# ── MatchResult ────────────────────────────────────────────────────────

def test_match_result_is_hashable() -> None:
    """MatchResult должен быть хэшируемым (dataclass frozen + slots)."""
    m = MatchResult(user_id=123, keyword="test")
    assert {m}  # Не должно упасть
    assert m == MatchResult(user_id=123, keyword="test")
    assert m != MatchResult(user_id=456, keyword="test")


# ── MarketplaceItem ────────────────────────────────────────────────────

def test_marketplace_item_extra_fields_ignored() -> None:
    """Лишние поля в JSON не должны ломать валидацию."""
    item = MarketplaceItem.model_validate_json(
        '{"platform":"mercari","name":"test","price":100,"url":"http://x","extra":"ignored"}'
    )
    assert item.name == "test"
    assert item.price == 100


def test_marketplace_item_optional_fields_default_none() -> None:
    """item_id и photo_url по умолчанию None."""
    item = MarketplaceItem(platform="mercari", name="test", price=100, url="http://x")
    assert item.item_id is None
    assert item.photo_url is None
