from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

NO_LIMIT = -1

PRICE_MIN_PRESETS: list[tuple[str, int]] = [
    ("No minimum", NO_LIMIT),
    ("¥1,000", 1_000),
    ("¥3,000", 3_000),
    ("¥5,000", 5_000),
    ("¥10,000", 10_000),
    ("¥30,000", 30_000),
]

PRICE_MAX_PRESETS: list[tuple[str, int]] = [
    ("No maximum", NO_LIMIT),
    ("¥5,000", 5_000),
    ("¥10,000", 10_000),
    ("¥30,000", 30_000),
    ("¥50,000", 50_000),
    ("¥100,000", 100_000),
]


class PriceMinCallback(CallbackData, prefix="pmin"):
    value: int


class PriceMaxCallback(CallbackData, prefix="pmax"):
    value: int


class CancelAddCallback(CallbackData, prefix="cancel_add"):
    pass


def cancel_add_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data=CancelAddCallback())
    return builder.as_markup()


def price_min_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, value in PRICE_MIN_PRESETS:
        builder.button(text=label, callback_data=PriceMinCallback(value=value))
    builder.button(text="✏️ Custom amount", callback_data=PriceMinCallback(value=0))
    builder.button(text="❌ Cancel", callback_data=CancelAddCallback())
    builder.adjust(2)
    return builder.as_markup()


def price_max_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, value in PRICE_MAX_PRESETS:
        builder.button(text=label, callback_data=PriceMaxCallback(value=value))
    builder.button(text="✏️ Custom amount", callback_data=PriceMaxCallback(value=0))
    builder.button(text="❌ Cancel", callback_data=CancelAddCallback())
    builder.adjust(2)
    return builder.as_markup()
