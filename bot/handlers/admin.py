import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.services.calibration import recalibrate, format_calibration_message
from bot.services.strava import sync_strava_runs, format_run_message, is_configured
from bot.db import queries as db_queries

logger = logging.getLogger(__name__)
ALLOWED_CHAT_IDS = config.allowed_chat_ids


async def handle_calibrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return

    await update.message.reply_text("🔧 Recalculating BMR/TDEE...")
    try:
        result = await recalibrate(trigger="manual")
        await update.message.reply_text(format_calibration_message(result), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Calibration error: {e}")
        await update.message.reply_text("❌ Calibration failed. Check logs for details.")


async def handle_syncstrava(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return

    if not is_configured():
        await update.message.reply_text(
            "⚠️ Strava credentials not configured.\n"
            "Add these to Railway Variables:\n"
            "`STRAVA_CLIENT_ID`\n`STRAVA_CLIENT_SECRET`\n`STRAVA_REFRESH_TOKEN`",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("🔄 Connecting to Strava...")
    try:
        imported = await sync_strava_runs()
        if not imported:
            await update.message.reply_text(
                "✅ Strava connected — no new runs in the last 48 hours.\n"
                "Runs will sync automatically every day at 22:00."
            )
        else:
            await update.message.reply_text(f"✅ Imported {len(imported)} run(s):")
            for run in imported:
                await update.message.reply_text(format_run_message(run), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Manual Strava sync error: {e}")
        await update.message.reply_text("❌ Strava sync failed. Check logs for details.")


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found.")
        return

    lines = [
        "🔧 *System Stats*\n",
        f"⚖️ Weight: {profile.get('current_weight_kg')} kg",
        f"🎯 Target: {profile.get('target_weight_kg')} kg",
        f"🔥 BMR: {profile.get('bmr')} kcal",
        f"📈 TDEE: {profile.get('tdee')} kcal",
        f"🍽 Daily target: {profile.get('target_daily_calories')} kcal",
        f"📅 Last calibration: {profile.get('last_calibration_date', 'Never')}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
