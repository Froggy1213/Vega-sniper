import json
import logging

import aio_pika
from aiogram import Bot
from aiogram.types import URLInputFile

from app.core.config import settings
from app.db.session import get_session_factory
from app.services.matcher import MarketplaceItem, find_matching_recipients

logger = logging.getLogger(__name__)


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


async def consume_rabbitmq(bot: Bot) -> None:
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)

        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue("new_items_queue", durable=True)
            logger.info("Connected to RabbitMQ, waiting for items on new_items_queue")

            session_factory = get_session_factory()

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            data = json.loads(message.body)
                            item = MarketplaceItem.from_message(data)
                        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                            logger.error("Invalid RabbitMQ payload: %s", exc)
                            continue

                        async with session_factory() as session:
                            matches = await find_matching_recipients(session, item)

                            for match in matches:
                                try:
                                    await _send_notification(
                                        bot,
                                        match.user.telegram_id,
                                        item,
                                        match.search.keyword,
                                    )
                                    logger.info(
                                        "Notification sent to telegram_id=%s for item=%r",
                                        match.user.telegram_id,
                                        item.name,
                                    )
                                except Exception as exc:
                                    logger.error(
                                        "Failed to notify telegram_id=%s: %s",
                                        match.user.telegram_id,
                                        exc,
                                    )

    except Exception as exc:
        logger.exception("RabbitMQ consumer error: %s", exc)
