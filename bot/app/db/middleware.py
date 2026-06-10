from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.db.session import get_session_factory
from app.services.user_service import get_or_create_user_in_session

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session_factory = get_session_factory()
        async with session_factory() as session:
            data["session"] = session
            
            # 1. Достаем пользователя из словаря data, а не из event
            telegram_user = data.get("event_from_user")
            
            # 2. Проверяем, есть ли пользователь (некоторые апдейты бывают без него)
            if telegram_user:
                # 3. Передаем telegram_user в функцию
                user = await get_or_create_user_in_session(session, telegram_user)
                data["user"] = user
                
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise