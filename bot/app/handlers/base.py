import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.user_service import get_or_create_user_in_session

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def start_handler(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user_in_session(session, message.from_user)
    logger.info("User %s started the bot (db_id=%s, premium=%s)", user.telegram_id, user.id, user.is_premium)

    if user.is_premium:
        welcome = (
            "Welcome to Marketplace Sniffer!\n\n"
            "Your subscription is active. Use /help to manage search alerts."
        )
    else:
        welcome = (
            "Welcome to Marketplace Sniffer!\n\n"
            "Subscribe to receive real-time marketplace alerts. "
            "Use /help to see available commands."
        )

    await message.answer(welcome)
