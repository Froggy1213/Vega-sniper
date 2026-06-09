import logging

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User

logger = logging.getLogger(__name__)


async def get_or_create_user_in_session(session: AsyncSession, tg_user: TgUser | None) -> User:
    if tg_user is None:
        raise ValueError("Telegram user is missing from update")

    # Ищем пользователя, сразу подгружая его подписки
    result = await session.execute(
        select(User)
        .options(selectinload(User.subscriptions))
        .where(User.telegram_id == tg_user.id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # ИЗМЕНЕНИЕ ЗДЕСЬ: Явно указываем пустые списки для нового пользователя!
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language_code=tg_user.language_code,
            subscriptions=[],  # Защита от lazy="raise" для подписок
            searches=[],       # Защита от lazy="raise" для поисков
        )
        session.add(user)
        await session.flush()
        logger.info("Registered new user telegram_id=%s", tg_user.id)
    else:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        user.language_code = tg_user.language_code
        user.is_active = True
        await session.flush()

    from app.services.subscription_service import refresh_premium_status

    await refresh_premium_status(session, user)
    return user