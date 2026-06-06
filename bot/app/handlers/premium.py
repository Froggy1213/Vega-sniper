import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import SubscriptionStatus
from app.db.models import User
from app.keyboards.menu import BTN_PREMIUM, main_menu_keyboard
from app.services.premium_service import (
    handle_pre_checkout,
    handle_successful_payment,
    send_premium_invoice,
)

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("premium"))
@router.message(F.text == BTN_PREMIUM)
async def cmd_premium(message: Message, session: AsyncSession, user: User) -> None:
    if user.is_premium:
        # Ищем подписку в уже загруженных данных без лишних запросов к БД
        active_sub = next(
            (sub for sub in user.subscriptions if sub.status == SubscriptionStatus.ACTIVE and sub.expires_at is not None),
            None
        )
        
        active_until = active_sub.expires_at.strftime("%Y-%m-%d") if active_sub else "unknown"
        await message.answer(
            f"✨ You already have <b>Premium</b>.\n"
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
async def successful_payment_handler(message: Message, session: AsyncSession, user: User) -> None:
    await handle_successful_payment(message, session, user)