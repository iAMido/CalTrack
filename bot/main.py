import asyncio
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from bot.utils.config import config
from bot.services.nutrition import load_usda_cache
from bot.handlers.photo import handle_photo
from bot.handlers.commands import (
    handle_weight,
    handle_water,
    handle_run,
    handle_summary,
    handle_status,
    handle_undo,
    handle_history,
    handle_help,
    handle_week,
    handle_add,
)
from bot.handlers.label import handle_label
from bot.handlers.callbacks import handle_callback, handle_text_input
from bot.handlers.admin import handle_calibrate, handle_stats

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Called once after the bot starts — load caches, etc."""
    logger.info("Loading USDA nutrition cache...")
    await load_usda_cache()
    logger.info("CalTrack bot ready.")


def main() -> None:
    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    # Auth filter — only allow the registered chat ID
    auth = filters.Chat(chat_id=config.telegram_allowed_chat_id)

    # Commands
    app.add_handler(CommandHandler("weight", handle_weight, filters=auth))
    app.add_handler(CommandHandler("water", handle_water, filters=auth))
    app.add_handler(CommandHandler("run", handle_run, filters=auth))
    app.add_handler(CommandHandler("summary", handle_summary, filters=auth))
    app.add_handler(CommandHandler("s", handle_summary, filters=auth))
    app.add_handler(CommandHandler("week", handle_week, filters=auth))
    app.add_handler(CommandHandler("w", handle_week, filters=auth))
    app.add_handler(CommandHandler("status", handle_status, filters=auth))
    app.add_handler(CommandHandler("undo", handle_undo, filters=auth))
    app.add_handler(CommandHandler("history", handle_history, filters=auth))
    app.add_handler(CommandHandler("label", handle_label, filters=auth))
    app.add_handler(CommandHandler("add", handle_add, filters=auth))
    app.add_handler(CommandHandler("calibrate", handle_calibrate, filters=auth))
    app.add_handler(CommandHandler("stats", handle_stats, filters=auth))
    app.add_handler(CommandHandler("help", handle_help, filters=auth))

    # Photo handler
    app.add_handler(MessageHandler(filters.PHOTO & auth, handle_photo))

    # Plain text — manual weight entry and add-item flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & auth, handle_text_input))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info(f"Starting CalTrack bot (chat_id: {config.telegram_allowed_chat_id})")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
