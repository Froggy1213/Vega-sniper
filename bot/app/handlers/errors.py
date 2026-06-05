import logging
from aiogram import Router, Bot
from aiogram.types import ErrorEvent

# Import settings so we know where to send alerts
from app.core.config import settings

# Create a router specifically for errors
router = Router()

@router.errors()
async def global_error_handler(event: ErrorEvent, bot: Bot):
    """
    Global handler for all uncaught exceptions in the bot.
    Any error that occurs while processing an update will be handled here.
    """
    # 1. Log the error to console/file with full traceback
    # logging.exception will automatically add exception details
    logging.exception(
        f"🚨 Critical error while processing update {event.update.update_id}: {event.exception}"
    )

    # 2. Notify the administrator in Telegram
    error_msg = (
        f"⚠️ <b>An error occurred in the bot!</b>\n\n"
        f"<b>Error type:</b> <code>{type(event.exception).__name__}</code>\n"
        f"<b>Description:</b> <code>{str(event.exception)}</code>\n\n"
        f"<i>See server logs for details.</i>"
    )
    
    try:
        await bot.send_message(chat_id=settings.admin_id, text=error_msg)
    except Exception as e:
        # If we can't even notify the admin (for example, blocked), just log it
        logging.error(f"Failed to send alert to admin: {e}")

    # If the error happened while replying to the user, try to apologize
    if event.update.message:
        try:
            await event.update.message.answer("Oops, something went wrong 🔧. We're fixing it now!")
        except Exception:
            pass # If it failed (e.g. chat deleted), ignore
