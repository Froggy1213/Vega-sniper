import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.config import settings
from app.db.middleware import DbSessionMiddleware
from app.db.session import close_db, init_db
from app.handlers.base import router as base_router
from app.handlers.errors import router as errors_router
from app.handlers.premium import router as premium_router
from app.handlers.search import router as search_router
from app.services.rabbitmq import consume_rabbitmq

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    await init_db()
    logger.info("Database initialized")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(errors_router)
    dp.include_router(base_router)
    dp.include_router(premium_router)
    dp.include_router(search_router)

    rabbitmq_task = asyncio.create_task(consume_rabbitmq(bot))

    async def shutdown_handler(_bot: Bot) -> None:
        rabbitmq_task.cancel()
        try:
            await rabbitmq_task
        except asyncio.CancelledError:
            pass
        await close_db()
        await bot.session.close()
        logger.info("Shutdown complete")

    dp.startup.register(on_startup)
    dp.shutdown.register(shutdown_handler)

    logger.info("Telegram bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
