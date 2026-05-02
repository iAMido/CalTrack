import logging
import re
import uuid
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.services.daily_summary import get_today_summary_text, get_status_text
from bot.utils.met_calculator import calculate_calories_burned, pace_to_sec_per_km, format_pace
from bot.services import nutrition as nut_service
from bot.utils.formatters import detect_meal_type
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


async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /add [meal_type] <grams>g <food name>

    Examples:
      /add lunch 15g olive oil
      /add 200g white rice
      /add dinner 120g grilled salmon
    """
    if not _check_auth(update):
        return

    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text(
            "Usage: `/add [meal\\_type] <grams>g <food name>`\n"
            "Example: `/add lunch 15g olive oil`",
            parse_mode="Markdown",
        )
        return

    # Parse meal_type (optional first word)
    meal_types = {"breakfast", "lunch", "dinner", "snack"}
    words = raw.split()
    if words[0].lower() in meal_types:
        meal_type = words[0].lower()
        rest = " ".join(words[1:])
    else:
        meal_type = detect_meal_type()
        rest = raw

    # Parse grams and food name: "<grams>g <name>"
    match = re.match(r"(\d+(?:\.\d+)?)\s*g\s+(.+)", rest, re.IGNORECASE)
    if not match:
        await update.message.reply_text(
            "Could not parse. Format: `/add lunch 15g olive oil`",
            parse_mode="Markdown",
        )
        return

    grams = float(match.group(1))
    food_name = match.group(2).strip()

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("No user profile found.")
        return

    # Find USDA match and calculate nutrition
    fdc_id = nut_service.find_usda_match(food_name)
    ai_fallback = None
    if not fdc_id:
        # Ask AI for nutrition estimate via a lightweight text call
        ai_fallback = await _estimate_nutrition_text(food_name)

    nut = nut_service.calculate_nutrition(fdc_id, int(grams), ai_fallback)

    tz = pytz.timezone(config.user_timezone)
    today = datetime.now(tz).strftime("%Y-%m-%d")

    # Find today's meal of this type, or create one
    client = db.get_client()
    existing_meals = (
        client.table("meals")
        .select("id,total_calories,total_protein_g,total_carbs_g,total_fat_g,total_fiber_g")
        .eq("meal_type", meal_type)
        .eq("status", "confirmed")
        .gte("eaten_at", f"{today}T00:00:00")
        .lte("eaten_at", f"{today}T23:59:59")
        .order("eaten_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if existing_meals:
        meal_id = existing_meals[0]["id"]
        # Update meal totals
        old = existing_meals[0]
        await db.update("meals", {"id": meal_id}, {
            "total_calories": (old.get("total_calories") or 0) + nut["calories"],
            "total_protein_g": round((old.get("total_protein_g") or 0) + nut["protein_g"], 2),
            "total_carbs_g": round((old.get("total_carbs_g") or 0) + nut["carbs_g"], 2),
            "total_fat_g": round((old.get("total_fat_g") or 0) + nut["fat_g"], 2),
            "total_fiber_g": round((old.get("total_fiber_g") or 0) + nut["fiber_g"], 2),
        })
    else:
        # Create a new meal entry
        meal_id = str(uuid.uuid4())
        await db.upsert("meals", {
            "id": meal_id,
            "user_id": profile["id"],
            "meal_type": meal_type,
            "eaten_at": datetime.now(tz).isoformat(),
            "total_calories": nut["calories"],
            "total_protein_g": nut["protein_g"],
            "total_carbs_g": nut["carbs_g"],
            "total_fat_g": nut["fat_g"],
            "total_fiber_g": nut["fiber_g"],
            "status": "confirmed",
        }, on_conflict="id")

    # Append meal item
    await db.insert("meal_items", {
        "meal_id": meal_id,
        "ingredient_name": food_name,
        "fdc_id": fdc_id,
        "weight_grams": int(grams),
        "weight_source": "user_text",
        "calories": nut["calories"],
        "protein_g": nut["protein_g"],
        "carbs_g": nut["carbs_g"],
        "fat_g": nut["fat_g"],
        "fiber_g": nut["fiber_g"],
    })

    # Refresh daily summary
    daily = await db_queries.refresh_daily_summary(today, profile["id"])

    cal_in = daily.get("total_calories_in", 0)
    target = daily.get("target_calories", 2285)
    remaining = target - cal_in

    await update.message.reply_text(
        f"✅ Added *{int(grams)}g {food_name}* to {meal_type} ({nut['calories']} kcal)\n\n"
        f"Today: *{cal_in:,} / {target:,} kcal* | Remaining: *{remaining:,} kcal*",
        parse_mode="Markdown",
    )


async def _estimate_nutrition_text(food_name: str) -> dict | None:
    """Ask OpenRouter for nutrition per 100g via text (no image)."""
    try:
        import httpx, json as _json
        from bot.utils.config import config as _cfg
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": (
                    "Return ONLY a JSON object with nutrition per 100g for the food. "
                    "Keys: calories_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, fiber_per_100g. "
                    "No explanation, no markdown."
                )},
                {"role": "user", "content": food_name},
            ],
            "temperature": 0.1,
            "max_tokens": 100,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{_cfg.openrouter_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {_cfg.openrouter_api_key}",
                         "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1].lstrip("json").strip()
        return _json.loads(content)
    except Exception as e:
        logger.warning(f"Text nutrition estimate failed for '{food_name}': {e}")
        return None


async def handle_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return
    await update.message.reply_text("📊 Weekly AI Coach report is a Stage 3 feature. Coming soon!")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    help_text = (
        "🤖 *CalTrack Commands*\n\n"
        "📷 *Send a photo* — Log a meal\n"
        "🏷 `/label` — Scan a nutrition label → save custom food\n"
        "➕ `/add lunch 15g olive oil` — Add a missed ingredient\n\n"
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
