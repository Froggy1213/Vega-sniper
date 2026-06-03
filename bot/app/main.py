import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.core.config import settings
from app.db.middleware import DbSessionMiddleware
from app.db.session import close_db, init_db
from app.handlers.base import router
from app.services.rabbitmq import consume_rabbitmq

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    await init_db()
    logger.info("Database initialized")


async def on_shutdown() -> None:
    await close_db()
    logger.info("Database connections closed")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    asyncio.create_task(consume_rabbitmq(bot))

    logger.info("Telegram bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
