import logging
from dataclasses import dataclass

from sqlalchemy import func, literal, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import Platform
from app.db.models import Search, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarketplaceItem:
    platform: str
    name: str
    price: int
    url: str
    item_id: str | None = None
    photo_url: str | None = None

    @classmethod
    def from_message(cls, data: dict[str, object]) -> "MarketplaceItem":
        return cls(
            platform=str(data["platform"]),
            name=str(data["name"]),
            price=int(data["price"]),
            url=str(data["url"]),
            item_id=str(data["item_id"]) if data.get("item_id") else None,
            photo_url=str(data["photo_url"]) if data.get("photo_url") else None,
        )


@dataclass(frozen=True, slots=True)
class MatchResult:
    user: User
    search: Search


async def find_matching_recipients(
    session: AsyncSession,
    item: MarketplaceItem,
) -> list[MatchResult]:
    try:
        platform = Platform(item.platform)
    except ValueError:
        logger.warning("Unknown platform in item payload: %s", item.platform)
        return []

    stmt = (
        select(User, Search)
        .join(Search, Search.user_id == User.id)
        .where(
            User.is_active.is_(True),
            Search.is_active.is_(True),
            Search.platform == platform,
            func.lower(literal(item.name)).like(
                func.concat("%", func.lower(Search.keyword), "%"),
            ),
        )
    )

    stmt = stmt.where(
        (Search.price_min.is_(None) | (Search.price_min <= item.price)),
        (Search.price_max.is_(None) | (Search.price_max >= item.price)),
    )

    result = await session.execute(stmt)
    matches = [MatchResult(user=row[0], search=row[1]) for row in result.all()]

    logger.info(
        "Item %r matched %d recipient(s) on %s",
        item.name,
        len(matches),
        platform.value,
    )
    return matches
