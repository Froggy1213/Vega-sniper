import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.keyboards.menu import BTN_HELP, main_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "📖 <b>Marketplace Sniffer Help</b>\n\n"
    "<b>Free plan</b> — up to 2 active searches with real-time alerts.\n"
    "<b>Premium</b> — unlimited searches via Telegram Stars.\n\n"
    "<b>How to add a search:</b>\n"
    "1. Tap <b>➕ Add Search</b>\n"
    "2. Type a keyword (e.g. <code>Pokemon</code>)\n"
    "3. Pick min/max price from the buttons\n\n"
    "<b>Commands:</b>\n"
    "/start — Main menu\n"
    "/add — Add a search\n"
    "/list — View active searches\n"
    "/premium — Upgrade to Premium\n"
    "/cancel — Cancel current action\n"
    "/help — This message"
)


@router.message(CommandStart())
async def start_handler(message: Message, session: AsyncSession, user: User) -> None:
    logger.info("User %s started bot (premium=%s)", user.telegram_id, user.is_premium)

    if user.is_premium:
        welcome = (
            "👋 Welcome to <b>Marketplace Sniffer</b>!\n\n"
            "⭐ Premium is active — unlimited alerts enabled.\n"
            "Tap <b>➕ Add Search</b> to set up a new alert."
        )
    else:
        welcome = (
            "👋 Welcome to <b>Marketplace Sniffer</b>!\n\n"
            "Get instant Mercari alerts when new items match your criteria.\n\n"
            "🆓 Free trial: <b>2 searches</b> with live notifications.\n"
            "⭐ Upgrade anytime via <b>Go Premium</b> for unlimited searches."
        )

    await message.answer(welcome, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())