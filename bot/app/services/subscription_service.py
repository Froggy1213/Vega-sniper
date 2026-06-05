from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.enums import SubscriptionProvider, SubscriptionStatus
from app.db.models import Subscription, User


async def refresh_premium_status(session: AsyncSession, user: User) -> bool:
    """Sync is_premium from active subscriptions. Returns current premium state."""
    now = datetime.now(timezone.utc)
    has_active = False

    # ЯВНЫЙ АСИНХРОННЫЙ ЗАПРОС вместо глючного user.subscriptions
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscriptions = result.scalars().all()

    for subscription in subscriptions:
        if subscription.status != SubscriptionStatus.ACTIVE:
            continue
        if subscription.expires_at is not None and subscription.expires_at <= now:
            subscription.status = SubscriptionStatus.EXPIRED
            continue
        has_active = True

    user.is_premium = has_active
    await session.flush()
    return has_active


async def activate_stars_subscription(
    session: AsyncSession,
    user: User,
    *,
    charge_id: str,
    stars_amount: int,
) -> Subscription:
    now = datetime.now(timezone.utc)
    duration = timedelta(days=settings.premium_duration_days)

    base_time = now
    
    # ЯВНЫЙ АСИНХРОННЫЙ ЗАПРОС вместо глючного user.subscriptions
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscriptions = result.scalars().all()

    for subscription in subscriptions:
        if (
            subscription.status == SubscriptionStatus.ACTIVE
            and subscription.expires_at is not None
            and subscription.expires_at > now
        ):
            base_time = subscription.expires_at
            break

    subscription = Subscription(
        user_id=user.id,
        provider=SubscriptionProvider.TELEGRAM_STARS,
        status=SubscriptionStatus.ACTIVE,
        external_id=charge_id,
        started_at=now,
        expires_at=base_time + duration,
    )
    session.add(subscription)
    user.is_premium = True
    await session.flush()
    return subscription