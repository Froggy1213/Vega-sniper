import logging
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Search, User

logger = logging.getLogger(__name__)


class MarketplaceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    platform: str
    name: str
    price: int
    url: str
    item_id: str | None = None
    photo_url: str | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    user_id: int
    keyword: str


async def get_active_searches(session: AsyncSession) -> list[Search]:
    """Выгружает все активные поиски вместе с юзерами для кэша."""
    stmt = (
        select(Search)
        .options(joinedload(Search.user))
        .join(User)
        .where(User.is_active.is_(True), Search.is_active.is_(True))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def find_matches_in_memory(
    item: MarketplaceItem, 
    active_searches: list[Search]
) -> list[MatchResult]:
    """Быстрый матчинг на стороне Python без дерганья базы."""
    matches = []
    item_name_lower = item.name.lower()
    
    for search in active_searches:
        if search.platform.value != item.platform:
            continue
            
        if search.keyword.lower() not in item_name_lower:
            continue
            
        if search.price_min is not None and item.price < search.price_min:
            continue

        if search.price_max is not None and item.price > search.price_max:
            continue
            
        matches.append(MatchResult(user_id=search.user.telegram_id, keyword=search.keyword))
        
    return matches