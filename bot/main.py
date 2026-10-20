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
from bot.services.coach import run_weekly_coach, split_for_telegram
from bot.services.nudge import nudge_breakfast, nudge_lunch, nudge_dinner
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
from bot.handlers.admin import handle_calibrate, handle_stats
from bot.whatsapp import gateway as wa
from bot.whatsapp import server as wa_server

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

# httpx logs every request URL at INFO. Telegram puts the bot token *in* the
# URL path (api.telegram.org/bot<TOKEN>/getUpdates), so leaving this at INFO
# writes the token to disk in cleartext roughly every 10 seconds — anyone who
# can read the logs can take over the bot. WARNING still surfaces real
# transport failures. Supabase URLs go through the same client, so this also
# stops the service_role key's host from being logged on every query.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def weekly_calibration_job(context) -> None:
    """Runs every Sunday at 20:00 — recalibrates BMR/TDEE and notifies."""
    try:
        result = await recalibrate(trigger="weekly_auto")
        msg = format_calibration_message(result)
        await wa.notify(msg)
        if config.telegram_enabled:
            await context.bot.send_message(
                chat_id=config.telegram_allowed_chat_id,
                text=msg,
                parse_mode="Markdown",
            )
        logger.info("Weekly calibration completed.")
    except Exception as e:
        logger.error(f"Weekly calibration job failed: {e}")


async def weekly_coach_job(context) -> None:
    """Runs every Saturday at 22:00 — sends weekly AI Coach report in Hebrew."""
    try:
        from bot.db import queries as db_queries
        profile = await db_queries.get_user_profile()
        if not profile:
            logger.warning("Weekly coach: no user profile found.")
            return

        report = await run_weekly_coach(profile["id"])
        await wa.notify(report)
        chunks = split_for_telegram(report) if config.telegram_enabled else []
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

    # Storage health check — fail loud, not silent. If the bucket is
    # missing, every photo upload will silently fail (the symptom that
    # left every meal with photo_path = NULL).
    from bot.db.supabase_client import storage_health_check
    ok, msg = await storage_health_check()
    if ok:
        logger.info(msg)
    else:
        logger.error(f"STORAGE WARNING: {msg}")

    tz = pytz.timezone(config.user_timezone)
    # Run every Sunday at 20:00 (days: 0=Sun in PTB's convention)
    application.job_queue.run_daily(
        weekly_calibration_job,
        time=dt_time(20, 0, tzinfo=tz),
        days=(0,),
        name="weekly_calibration",
    )

    # AI Coach: Saturday at 22:00 (days: 6=Sat in PTB's convention)
    application.job_queue.run_daily(
        weekly_coach_job,
        time=dt_time(22, 0, tzinfo=tz),
        days=(6,),
        name="weekly_coach",
    )

    # "Forgot to log?" nudges — fire only if the matching meal isn't logged yet.
    application.job_queue.run_daily(
        nudge_breakfast,
        time=dt_time(11, 0, tzinfo=tz),
        name="nudge_breakfast",
    )
    application.job_queue.run_daily(
        nudge_lunch,
        time=dt_time(14, 0, tzinfo=tz),
        name="nudge_lunch",
    )
    application.job_queue.run_daily(
        nudge_dinner,
        time=dt_time(19, 30, tzinfo=tz),
        name="nudge_dinner",
    )

    # WhatsApp group (via TARS's wa-gateway) — off unless WA_TOKEN is set.
    try:
        application.bot_data["wa_runner"] = await wa_server.start()
    except Exception as e:
        logger.error(f"WhatsApp listener failed to start: {type(e).__name__}: {e}")

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
    app.add_handler(CommandHandler("barcode", handle_barcode_command, filters=auth))
    app.add_handler(CommandHandler("template", handle_template, filters=auth))
    app.add_handler(CommandHandler("t", handle_template, filters=auth))

    # Photo handler
    app.add_handler(MessageHandler(filters.PHOTO & auth, handle_photo))

    # Plain text — manual weight entry and add-item flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & auth, handle_text_input))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    if not config.telegram_enabled:
        asyncio.run(run_without_telegram(app))
        return
    logger.info(f"Starting CalTrack bot (chat_id: {config.telegram_allowed_chat_id})")
    app.run_polling(drop_pending_updates=True)


async def run_without_telegram(app: Application) -> None:
    """WhatsApp only (TELEGRAM_ENABLED=false): the same post_init (caches, the
    job queue with nudges and weekly reports, the WhatsApp listener), but no
    Telegram polling — run_polling is what would start the updater."""
    import signal

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:      # Windows dev box
            pass
    await app.initialize()
    await post_init(app)
    await app.start()
    logger.info("CalTrack running WhatsApp-only (TELEGRAM_ENABLED=false): no Telegram polling.")
    try:
        await stop.wait()
    finally:
        runner = app.bot_data.get("wa_runner")
        if runner is not None:
            await runner.cleanup()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    main()
