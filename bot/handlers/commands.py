import logging
import re
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.services.daily_summary import get_today_summary_text, get_status_text
from bot.utils.met_calculator import calculate_calories_burned, pace_to_sec_per_km, format_pace
from bot.db import supabase_client as db
from bot.db import queries as db_queries

logger = logging.getLogger(__name__)
ALLOWED_CHAT_IDS = config.allowed_chat_ids


def _check_auth(update: Update) -> bool:
    return update.effective_chat.id in ALLOWED_CHAT_IDS


async def handle_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/weight 87.3`", parse_mode="Markdown")
        return

    try:
        weight_kg = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid weight. Use: `/weight 87.3`", parse_mode="Markdown")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found. Run seed_profile.py first.")
        return

    await db.insert("weight_log", {"user_id": profile["id"], "weight_kg": weight_kg})
    await db.update("user_profile", {"id": profile["id"]}, {"current_weight_kg": weight_kg})

    await update.message.reply_text(f"⚖️ Weight logged: *{weight_kg} kg*", parse_mode="Markdown")


async def handle_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/water 500` (ml)", parse_mode="Markdown")
        return

    try:
        amount_ml = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Use: `/water 500`", parse_mode="Markdown")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found.")
        return

    await db.insert("water_log", {"user_id": profile["id"], "amount_ml": amount_ml})
    await update.message.reply_text(f"💧 Water logged: *{amount_ml} ml*", parse_mode="Markdown")


async def handle_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /run 5.2 28:30 [heart_rate]"""
    if not _check_auth(update):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/run <km> <mm:ss> [heart_rate]`\nExample: `/run 5.2 28:30 152`",
            parse_mode="Markdown",
        )
        return

    try:
        distance_km = float(args[0])
        duration_str = args[1]
        pace_sec = pace_to_sec_per_km(duration_str) if ":" in duration_str else None

        # If duration is total time (MM:SS format), calculate pace
        parts = duration_str.split(":")
        duration_min = int(parts[0]) + int(parts[1]) / 60

        avg_hr = int(args[2]) if len(args) >= 3 else None
        pace_sec = round((duration_min * 60) / distance_km) if distance_km > 0 else None

    except (ValueError, IndexError) as e:
        await update.message.reply_text(f"❌ Invalid format: {e}\nExample: `/run 5.2 28:30 152`", parse_mode="Markdown")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found.")
        return

    calories = calculate_calories_burned(distance_km, round(duration_min), profile.get("current_weight_kg", 80), pace_sec)

    tz = pytz.timezone(config.user_timezone)
    run_data = {
        "user_id": profile["id"],
        "distance_km": distance_km,
        "duration_minutes": round(duration_min),
        "avg_pace_sec_per_km": pace_sec,
        "avg_heart_rate": avg_hr,
        "calories_burned": calories,
        "source": "manual",
        "run_date": datetime.now(tz).isoformat(),
    }

    await db.insert("caltrack_runs", run_data)

    pace_str = format_pace(pace_sec) if pace_sec else "?"
    hr_str = f" | ❤️ {avg_hr}" if avg_hr else ""
    await update.message.reply_text(
        f"🏃 *Run logged!*\n"
        f"{distance_km} km | {duration_str} | {pace_str}/km{hr_str}\n"
        f"Burned: ~{calories} kcal",
        parse_mode="Markdown",
    )


async def handle_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return
    text = await get_today_summary_text()
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return
    text = await get_status_text()
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    meals = await db_queries.get_last_n_meals(1)
    if not meals:
        await update.message.reply_text("No meals to undo.")
        return

    last_meal = meals[0]
    meal_type = last_meal.get("meal_type", "meal")
    cal = last_meal.get("total_calories", 0)

    # Show confirmation keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, undo it", callback_data=f"undo:{last_meal['id']}"),
            InlineKeyboardButton("❌ Keep it", callback_data="undo:cancel"),
        ]
    ])
    await update.message.reply_text(
        f"Undo last meal? *{meal_type.capitalize()}* ({cal} kcal)",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    args = context.args
    n = int(args[0]) if args and args[0].isdigit() else 5
    n = min(n, 20)

    meals = await db_queries.get_last_n_meals(n)
    if not meals:
        await update.message.reply_text("No meals logged yet.")
        return

    tz = pytz.timezone(config.user_timezone)
    lines = [f"📋 *Last {len(meals)} meals:*\n"]
    for m in meals:
        try:
            dt = datetime.fromisoformat(m["eaten_at"].replace("Z", "+00:00")).astimezone(tz)
            date_str = dt.strftime("%b %d %H:%M")
        except Exception:
            date_str = m.get("eaten_at", "")[:16]
        lines.append(f"• {date_str} — {m.get('meal_type', '').capitalize()}: {m.get('total_calories', 0)} kcal")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return
    await update.message.reply_text("📊 Weekly AI Coach report is a Stage 3 feature. Coming soon!")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    help_text = (
        "🤖 *CalTrack Commands*\n\n"
        "📷 *Send a photo* — Log a meal\n\n"
        "⚖️ `/weight 87.3` — Log body weight\n"
        "💧 `/water 500` — Log water (ml)\n"
        "🏃 `/run 5.2 28:30 152` — Log a run (km, time, HR)\n\n"
        "📊 `/summary` or `/s` — Today's full summary\n"
        "🎯 `/status` — Remaining calories today\n"
        "📋 `/history 5` — Last N meals\n"
        "↩️ `/undo` — Cancel last meal\n"
        "📈 `/week` or `/w` — Weekly AI Coach report\n"
        "🔧 `/calibrate` — Recalculate BMR/TDEE targets\n"
        "❓ `/help` — This message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
