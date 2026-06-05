from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ADD_SEARCH = "➕ Add Search"
BTN_MY_SEARCHES = "📋 My Searches"
BTN_PREMIUM = "⭐ Go Premium"
BTN_HELP = "❓ Help"

MENU_BUTTONS = {BTN_ADD_SEARCH, BTN_MY_SEARCHES, BTN_PREMIUM, BTN_HELP}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_SEARCH), KeyboardButton(text=BTN_MY_SEARCHES)],
            [KeyboardButton(text=BTN_PREMIUM), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Choose an action or type a keyword…",
    )
