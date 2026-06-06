import logging
import uuid

from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.keyboards.menu import main_menu_keyboard
from app.services.subscription_service import activate_stars_subscription

logger = logging.getLogger(__name__)

PREMIUM_PAYLOAD_PREFIX = "premium:"


def build_premium_payload(user_id: uuid.UUID) -> str:
    return f"{PREMIUM_PAYLOAD_PREFIX}{user_id}"


def parse_premium_payload(payload: str) -> uuid.UUID | None:
    if not payload.startswith(PREMIUM_PAYLOAD_PREFIX):
        return None
    try:
        return uuid.UUID(payload.removeprefix(PREMIUM_PAYLOAD_PREFIX))
    except ValueError:
        return None


async def send_premium_invoice(message: Message, user: User) -> None:
    from aiogram.types import LabeledPrice

    if message.chat is None:
        return

    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="Marketplace Sniffer Premium",
        description=(
            f"Unlimited search alerts for {settings.premium_duration_days} days. "
            "Real-time Mercari notifications with photos and direct links."
        ),
        payload=build_premium_payload(user.id),
        currency="XTR",
        prices=[
            LabeledPrice(
                label=f"Premium ({settings.premium_duration_days} days)",
                amount=settings.premium_stars_price,
            )
        ],
        provider_token="",
    )


async def handle_pre_checkout(query: PreCheckoutQuery) -> None:
    if query.invoice_payload and parse_premium_payload(query.invoice_payload):
        await query.answer(ok=True)
        return
    await query.answer(ok=False, error_message="Invalid payment payload.")


async def handle_successful_payment(message: Message, session: AsyncSession, user: User) -> None:
    if message.successful_payment is None:
        return

    payment = message.successful_payment
    expected_user_id = parse_premium_payload(payment.invoice_payload)

    if expected_user_id is None:
        logger.error("Unknown payment payload: %s", payment.invoice_payload)
        await message.answer("Payment received, but we could not activate Premium. Contact support.")
        return

    if user.id != expected_user_id:
        logger.error("Payment user mismatch: expected %s, got %s", expected_user_id, user.id)
        await message.answer("Payment verification failed. Contact support.")
        return

    subscription = await activate_stars_subscription(
        session,
        user,
        charge_id=payment.telegram_payment_charge_id,
        stars_amount=payment.total_amount,
    )

    expires = subscription.expires_at.strftime("%Y-%m-%d") if subscription.expires_at else "unknown"
    await message.answer(
        f"🎉 <b>Premium activated!</b>\n\n"
        f"You now have unlimited search alerts.\n"
        f"Valid until: <b>{expires}</b>\n\n"
        f"Tap <b>➕ Add Search</b> to create a new alert.",
        reply_markup=main_menu_keyboard(),
    )
    logger.info(
        "Premium activated for telegram_id=%s until %s (stars=%s)",
        user.telegram_id,
        expires,
        payment.total_amount,
    )