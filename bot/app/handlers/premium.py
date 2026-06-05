import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.menu import BTN_PREMIUM, main_menu_keyboard
from app.services.premium_service import (
    handle_pre_checkout,
    handle_successful_payment,
    send_premium_invoice,
)
from app.services.subscription_service import refresh_premium_status
from app.services.user_service import get_or_create_user_in_session

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("premium"))
@router.message(F.text == BTN_PREMIUM)
async def cmd_premium(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user_in_session(session, message.from_user)
    await refresh_premium_status(session, user)

    if user.is_premium:
        active_until = "unknown"
        for sub in user.subscriptions:
            if sub.is_active and sub.expires_at:
                active_until = sub.expires_at.strftime("%Y-%m-%d")
                break
        await message.answer(
            f"⭐ You already have <b>Premium</b>.\n"
            f"Active until: <b>{active_until}</b>\n\n"
            "Enjoy unlimited search alerts!",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "⭐ <b>Go Premium</b>\n\n"
        "Free plan: up to 2 active searches with live alerts.\n"
        "Premium: <b>unlimited</b> searches + priority delivery.\n\n"
        "Complete the payment below to upgrade:",
        reply_markup=main_menu_keyboard(),
    )
    await send_premium_invoice(message, user)


@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery) -> None:
    await handle_pre_checkout(query)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, session: AsyncSession) -> None:
    await handle_successful_payment(message, session)
