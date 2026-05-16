import asyncio
import logging
from datetime import time as dt_time
import pytz
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from bot.utils.config import config
from bot.services.nutrition import load_usda_cache
from bot.services.calibration import recalibrate, format_calibration_message
from bot.services.strava import sync_strava_runs, format_run_message
from bot.services.coach import run_weekly_coach, split_for_telegram
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
from bot.handlers.barcode import handle_barcode_command
from bot.handlers.template import handle_template
from bot.handlers.callbacks import handle_callback, handle_text_input
from bot.handlers.admin import handle_calibrate, handle_stats, handle_syncstrava

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def weekly_calibration_job(context) -> None:
    """Runs every Sunday at 20:00 — recalibrates BMR/TDEE and notifies."""
    try:
        result = await recalibrate(trigger="weekly_auto")
        msg = format_calibration_message(result)
        await context.bot.send_message(
            chat_id=config.telegram_allowed_chat_id,
            text=msg,
            parse_mode="Markdown",
        )
        logger.info("Weekly calibration completed.")
    except Exception as e:
        logger.error(f"Weekly calibration job failed: {e}")


async def strava_sync_job(context) -> None:
    """Runs daily at 22:00 — imports new Strava runs and notifies."""
    try:
        imported = await sync_strava_runs()
        for run in imported:
            await context.bot.send_message(
                chat_id=config.telegram_allowed_chat_id,
                text=format_run_message(run),
                parse_mode="Markdown",
            )
        if not imported:
            logger.info("Strava sync: no new runs.")
    except Exception as e:
        logger.error(f"Strava sync job failed: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=config.telegram_allowed_chat_id,
                text=f"❌ Strava auto-sync failed:\n`{e}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def weekly_coach_job(context) -> None:
    """Runs every Saturday at 22:00 — sends weekly AI Coach report in Hebrew."""
    try:
        from bot.db import queries as db_queries
        profile = await db_queries.get_user_profile()
        if not profile:
            logger.warning("Weekly coach: no user profile found.")
            return

        report = await run_weekly_coach(profile["id"])
        chunks = split_for_telegram(report)
        for chunk in chunks:
            await context.bot.send_message(
                chat_id=config.telegram_allowed_chat_id,
                text=chunk,
            )
        logger.info("Weekly coach report sent.")
    except Exception as e:
        logger.error(f"Weekly coach job failed: {e}")


async def post_init(application: Application) -> None:
    """Called once after the bot starts — load caches and schedule jobs."""
    logger.info("Loading USDA nutrition cache...")
    await load_usda_cache()

    tz = pytz.timezone(config.user_timezone)
    # Run every Sunday at 20:00 (days: 0=Sun in PTB's convention)
    application.job_queue.run_daily(
        weekly_calibration_job,
        time=dt_time(20, 0, tzinfo=tz),
        days=(0,),
        name="weekly_calibration",
    )

    # Strava sync: daily at 22:00
    application.job_queue.run_daily(
        strava_sync_job,
        time=dt_time(22, 0, tzinfo=tz),
        name="strava_sync",
    )

    # AI Coach: Saturday at 22:00 (days: 6=Sat in PTB's convention)
    application.job_queue.run_daily(
        weekly_coach_job,
        time=dt_time(22, 0, tzinfo=tz),
        days=(6,),
        name="weekly_coach",
    )
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
    app.add_handler(CommandHandler("syncstrava", handle_syncstrava, filters=auth))
    app.add_handler(CommandHandler("help", handle_help, filters=auth))
    app.add_handler(CommandHandler("barcode", handle_barcode_command, filters=auth))
    app.add_handler(CommandHandler("template", handle_template, filters=auth))
    app.add_handler(CommandHandler("t", handle_template, filters=auth))

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
