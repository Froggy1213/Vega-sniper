import logging

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

logger = logging.getLogger(__name__)


async def get_or_create_user(tg_user: TgUser) -> User:
    from app.db.session import get_session

    async with get_session() as session:
        return await get_or_create_user_in_session(session, tg_user)


async def get_or_create_user_in_session(session: AsyncSession, tg_user: TgUser) -> User:
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language_code=tg_user.language_code,
        )
        session.add(user)
        await session.flush()
        logger.info("Registered new user telegram_id=%s", tg_user.id)
        return user

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    user.language_code = tg_user.language_code
    user.is_active = True
    await session.flush()
    return user


async def sync_premium_status(session: AsyncSession, user: User) -> None:
    """Keep users.is_premium aligned with active subscriptions."""
    user.is_premium = any(subscription.is_active for subscription in user.subscriptions)
