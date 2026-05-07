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
from bot.services.translator import translate
from bot.utils.formatters import detect_meal_type
from bot.services.calibration import check_and_recalibrate, format_calibration_message
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

    # Auto-recalibrate if milestone or weekly threshold reached
    try:
        cal_result = await check_and_recalibrate()
        if cal_result:
            await update.message.reply_text(format_calibration_message(cal_result), parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Auto-calibration after weight log failed: {e}")


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
    /add [meal_type] <food description>

    Supports two modes:
      Precise:  /add lunch 150g chicken breast
      Freeform: /add lunch פיתה שווארמה פרגית
                /add סושי סלמון רול
    """
    if not _check_auth(update):
        return

    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text(
            "Usage: `/add [meal\\_type] <food description>`\n\n"
            "*Precise:*\n"
            "`/add lunch 150g chicken breast`\n\n"
            "*Freeform (Hebrew/English):*\n"
            "`/add lunch פיתה שווארמה פרגית`\n"
            "`/add סושי סלמון רול`\n"
            "`/add dinner חלה עם שניצל וחומוס`",
            parse_mode="Markdown",
        )
        return

    # Parse meal_type (optional first word, before translation)
    meal_types_he = {"בוקר": "breakfast", "צהריים": "lunch", "ערב": "dinner", "חטיף": "snack", "נשנוש": "snack"}
    meal_types_en = {"breakfast", "lunch", "dinner", "snack"}

    words = raw.split()
    meal_type = None
    rest = raw

    if words[0].lower() in meal_types_en:
        meal_type = words[0].lower()
        rest = " ".join(words[1:])
    elif words[0] in meal_types_he:
        meal_type = meal_types_he[words[0]]
        rest = " ".join(words[1:])

    if not meal_type:
        meal_type = detect_meal_type()

    if not rest.strip():
        await update.message.reply_text("Please describe what you ate.")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found.")
        return

    # Try precise mode: "<number>g/ml <food>" or "<food> <number>g/ml"
    translated = await translate(rest)
    match = re.match(r"(\d+(?:\.\d+)?)\s*(?:g|ml)\s+(.+)", translated, re.IGNORECASE)
    if not match:
        match_rev = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s*(?:g|ml)\s*$", translated, re.IGNORECASE)
        if match_rev:
            # Swap groups so grams is group 1, food is group 2
            class _M:
                def group(self, n):
                    return match_rev.group(2) if n == 1 else match_rev.group(1)
            match = _M()

    if match:
        # Precise mode — single ingredient with known weight
        grams = float(match.group(1))
        food_name = match.group(2).strip()

        fdc_id = nut_service.find_usda_match(food_name)
        ai_fallback = None
        if not fdc_id:
            ai_fallback = await _estimate_nutrition_text(food_name)

        nut = nut_service.calculate_nutrition(fdc_id, int(grams), ai_fallback)
        items = [{"name": food_name, "grams": int(grams), "fdc_id": fdc_id, **nut}]
        total_cal = nut["calories"]
    else:
        # Freeform mode — AI breaks down the dish
        await update.message.reply_text("🔍 Breaking down your meal...")
        try:
            import asyncio as _aio
            breakdown = await _aio.wait_for(_analyze_dish(rest), timeout=25.0)
        except _aio.TimeoutError:
            await update.message.reply_text("❌ AI analysis timed out. Please try again.")
            return
        except Exception as e:
            logger.error(f"Freeform analysis crashed: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Analysis error: {e}")
            return

        if not breakdown:
            await update.message.reply_text(
                "❌ Could not analyze the food. Try being more specific or use the precise format:\n"
                "`/add lunch 150g chicken breast`",
                parse_mode="Markdown",
            )
            return

        items = []
        for ing in breakdown:
            try:
                grams = int(ing.get("grams") or ing.get("estimated_grams") or 100)
                fdc_id = nut_service.find_usda_match(ing["name_en"])
                if fdc_id:
                    nut = nut_service.calculate_nutrition(fdc_id, grams)
                else:
                    factor = grams / 100
                    nut = {
                        "calories": round(ing.get("calories_per_100g", 0) * factor),
                        "protein_g": round(ing.get("protein_per_100g", 0) * factor, 1),
                        "carbs_g": round(ing.get("carbs_per_100g", 0) * factor, 1),
                        "fat_g": round(ing.get("fat_per_100g", 0) * factor, 1),
                        "fiber_g": round(ing.get("fiber_per_100g", 0) * factor, 1),
                    }
                items.append({"name": ing["name_en"], "grams": grams, "fdc_id": fdc_id, **nut})
            except Exception as e:
                logger.warning(f"Skipping ingredient {ing}: {e}")
                continue

        if not items:
            await update.message.reply_text("❌ Could not process any ingredients.")
            return

        total_cal = sum(i["calories"] for i in items)

    # Save to DB
    tz = pytz.timezone(config.user_timezone)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    meal_id = str(uuid.uuid4())

    total_nut = {
        "calories": sum(i["calories"] for i in items),
        "protein_g": round(sum(i["protein_g"] for i in items), 1),
        "carbs_g": round(sum(i["carbs_g"] for i in items), 1),
        "fat_g": round(sum(i["fat_g"] for i in items), 1),
        "fiber_g": round(sum(i["fiber_g"] for i in items), 1),
    }

    try:
        await db.upsert("meals", {
            "id": meal_id,
            "user_id": profile["id"],
            "meal_type": meal_type,
            "eaten_at": datetime.now(tz).isoformat(),
            "total_calories": total_nut["calories"],
            "total_protein_g": total_nut["protein_g"],
            "total_carbs_g": total_nut["carbs_g"],
            "total_fat_g": total_nut["fat_g"],
            "total_fiber_g": total_nut["fiber_g"],
            "status": "confirmed",
        }, on_conflict="id")

        for item in items:
            await db.insert("meal_items", {
                "meal_id": meal_id,
                "ingredient_name": item["name"],
                "fdc_id": item.get("fdc_id"),
                "weight_grams": item["grams"],
                "weight_source": "user_confirmed" if match else "ai_estimate",
                "calories": item["calories"],
                "protein_g": item["protein_g"],
                "carbs_g": item["carbs_g"],
                "fat_g": item["fat_g"],
                "fiber_g": item["fiber_g"],
            })

        daily = await db_queries.refresh_daily_summary(today, profile["id"])
        cal_in = daily.get("total_calories_in", 0)
        target = daily.get("target_calories", 2285)
        remaining = target - cal_in
    except Exception as e:
        logger.error(f"Failed to save meal: {e}")
        await update.message.reply_text(f"❌ Failed to save: {e}")
        return

    # Build response with ingredient breakdown
    if len(items) == 1:
        item_str = f"*{items[0]['grams']}g {items[0]['name']}*"
    else:
        lines = [f"  • {i['name']} ({i['grams']}g) — {i['calories']} kcal" for i in items]
        item_str = "\n".join(lines)

    await update.message.reply_text(
        f"✅ Added to {meal_type} ({total_cal} kcal)\n"
        f"{item_str}\n\n"
        f"Today: *{cal_in:,} / {target:,} kcal* | Remaining: *{remaining:,} kcal*",
        parse_mode="Markdown",
    )


async def _analyze_dish(description: str) -> list[dict] | None:
    """Ask AI to break down a dish into individual ingredients with nutrition."""
    import httpx, json as _json
    from bot.utils.config import config as _cfg

    logger.info(f"_analyze_dish called with: '{description}'")
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": (
                "You are a clinical dietitian. The user describes a dish in Hebrew or English. "
                "Break it down into individual ingredients with estimated weights and nutrition per 100g. "
                "Return ONLY a JSON array (no markdown, no explanation): "
                '[{"name_en": "ingredient", "name_he": "מרכיב", "grams": 120, '
                '"calories_per_100g": 165, "protein_per_100g": 31, "carbs_per_100g": 0, '
                '"fat_per_100g": 3.6, "fiber_per_100g": 0}] '
                "RULES: Use realistic Israeli portion sizes. A pita ~60g, tahini ~30g, "
                "hummus serving ~80g, schnitzel ~150g. Include ALL components (bread, protein, "
                "sauces, vegetables). Nutrition values per 100g must never be 0 for real food."
            )},
            {"role": "user", "content": description},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
    }
    logger.info("Sending request to OpenRouter...")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{_cfg.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {_cfg.openrouter_api_key}",
                     "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
    logger.info(f"OpenRouter responded: {r.status_code}")
    content = r.json()["choices"][0]["message"]["content"].strip()
    logger.info(f"AI content: {content[:200]}")
    if content.startswith("```"):
        content = content.split("```")[1].lstrip("json").strip()
    result = _json.loads(content)
    if isinstance(result, dict) and "ingredients" in result:
        result = result["ingredients"]
    if isinstance(result, list) and len(result) > 0:
        return result
    logger.warning(f"Unexpected AI response format: {content[:200]}")
    return None


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

    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found.")
        return

    await update.message.reply_text("📊 Generating your weekly AI Coach report...")

    from bot.services.coach import run_weekly_coach, split_for_telegram
    try:
        report = await run_weekly_coach(profile["id"])
        chunks = split_for_telegram(report)
        for chunk in chunks:
            await update.message.reply_text(chunk)
    except Exception as e:
        logger.warning(f"Weekly coach report failed: {e}")
        await update.message.reply_text("❌ Could not generate the weekly report. Try again later.")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update):
        return

    help_text = (
        "🤖 *CalTrack Commands*\n\n"
        "*— Logging —*\n"
        "📷 Send a photo — Log a meal\n"
        "🏷 `/label` — Scan a nutrition label → save custom food\n"
        "➕ `/add lunch פיתה שווארמה` — Add food \\(Hebrew/English, AI breakdown\\)\n"
        "⚖️ `/weight 87.3` — Log body weight\n"
        "💧 `/water 500` — Log water \\(ml\\)\n"
        "🏃 `/run 5.2 28:30 152` — Log a run \\(km, time, HR\\)\n\n"
        "*— Summary —*\n"
        "📊 `/summary` or `/s` — Today's full summary\n"
        "🎯 `/status` — Remaining calories today\n"
        "📋 `/history 5` — Last N meals\n"
        "↩️ `/undo` — Cancel last meal\n\n"
        "*— System —*\n"
        "🔧 `/calibrate` — Recalculate BMR/TDEE targets\n"
        "📈 `/stats` — Current BMR/TDEE/target\n"
        "🏅 `/syncstrava` — Import latest Strava runs now\n"
        "📈 `/week` or `/w` — Weekly AI Coach report\n"
        "❓ `/help` — This message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
