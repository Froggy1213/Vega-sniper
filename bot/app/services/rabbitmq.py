import asyncio
import logging

import aio_pika
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import URLInputFile
from pydantic import ValidationError

from app.core.config import settings
from app.db.session import get_session_factory
from app.services.matcher import (
    MarketplaceItem,
    MatchResult,
    find_matches_in_memory,
    get_active_searches,
)

logger = logging.getLogger(__name__)

RECONNECT_DELAY_SECONDS = 5
NOTIFY_CONCURRENCY = 10  # Максимум одновременных отправок уведомлений

_ACTIVE_SEARCHES_CACHE = []


def _build_notification_text(item: MarketplaceItem, keyword: str) -> str:
    return (
        f"🔥 <b>New find ({item.platform})!</b>\n\n"
        f"🔎 Search: <code>{keyword}</code>\n"
        f"📦 Item: <code>{item.name}</code>\n"
        f"💰 Price: <b>{item.price:,} JPY</b>\n"
        f"🔗 <a href='{item.url}'>Link to item</a>"
    )


async def _send_notification(bot: Bot, chat_id: int, item: MarketplaceItem, keyword: str) -> None:
    text = _build_notification_text(item, keyword)

    if item.photo_url:
        await bot.send_photo(
            chat_id=chat_id,
            photo=URLInputFile(item.photo_url),
            caption=text,
        )
    else:
        await bot.send_message(chat_id=chat_id, text=text)


async def _update_cache_loop(session_factory) -> None:
    """Фоновое обновление кэша поисков раз в минуту."""
    global _ACTIVE_SEARCHES_CACHE
    while True:
        try:
            async with session_factory() as session:
                _ACTIVE_SEARCHES_CACHE = await get_active_searches(session)
        except asyncio.CancelledError:
            break  # Выходим из цикла при штатной остановке
        except Exception as exc:
            logger.error("Cache update failed: %s", exc)
        await asyncio.sleep(60)


async def _consume_loop(bot: Bot) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=50)
        queue = await channel.declare_queue(
            "new_items_queue",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "dead_letter_exchange",
                "x-dead-letter-routing-key": "dead",
            },
        )
        
        logger.info("Connected to RabbitMQ, waiting for items...")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(ignore_processed=True):
                    try:
                        item = MarketplaceItem.model_validate_json(message.body)
                    except ValidationError as exc:
                        logger.error("Invalid RabbitMQ payload: %s", exc)
                        await message.reject(requeue=False)
                        continue

                    matches = find_matches_in_memory(item, _ACTIVE_SEARCHES_CACHE)

                    if not matches:
                        await message.ack()
                        continue

                    # Параллельная отправка уведомлений с семафором
                    sem = asyncio.Semaphore(NOTIFY_CONCURRENCY)

                    async def _notify_one(match: MatchResult) -> None:
                        async with sem:
                            try:
                                await _send_notification(bot, match.user_id, item, match.keyword)
                            except TelegramForbiddenError:
                                logger.info("User %s blocked bot", match.user_id)
                                # TODO: Деактивировать юзера в БД, чтобы не гонять вхолостую
                            except TelegramRetryAfter as exc:
                                logger.warning(
                                    "Flood control for user %s, retrying after %ss",
                                    match.user_id, exc.retry_after,
                                )
                                await asyncio.sleep(exc.retry_after)
                                try:
                                    await _send_notification(bot, match.user_id, item, match.keyword)
                                except Exception as retry_exc:
                                    logger.error(
                                        "Retry failed for user %s: %s",
                                        match.user_id, retry_exc,
                                    )

                    results = await asyncio.gather(
                        *[_notify_one(m) for m in matches],
                        return_exceptions=True,
                    )

                    # Логируем критические ошибки (не Telegram-специфичные)
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(
                                "Failed to notify user %s: %s",
                                matches[i].user_id, result,
                            )

                    await message.ack()


async def consume_rabbitmq(bot: Bot) -> None:
    session_factory = get_session_factory()

    # Запускаем апдейтер кэша один раз здесь
    cache_task = asyncio.create_task(_update_cache_loop(session_factory))

    try:
        while True:
            try:
                await _consume_loop(bot)
            except asyncio.CancelledError:
                logger.info("RabbitMQ consumer stopped")
                raise
            except Exception:
                logger.exception("RabbitMQ consumer error, reconnecting in %ss", RECONNECT_DELAY_SECONDS)
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
    finally:
        cache_task.cancel()
        try:
            await cache_task
        except asyncio.CancelledError:
            pass