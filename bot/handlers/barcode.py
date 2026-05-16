"""
Barcode scanning handler: /barcode command + photo processing.

Flow:
  1. User sends /barcode  → bot asks for photo (sets waiting_for="barcode")
  2. User sends photo     → decode barcode → Open Food Facts lookup → show result
  3. User taps gram button → save as snack meal
"""

import logging
import uuid
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.services import barcode as bc_service
from bot.db import supabase_client as db
from bot.db import queries as db_queries

logger = logging.getLogger(__name__)
ALLOWED_CHAT_IDS = config.allowed_chat_ids


async def handle_barcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return
    context.user_data["waiting_for"] = "barcode"
    await update.message.reply_text(
        "📷 Send me a clear photo of the product barcode (EAN/UPC).",
        parse_mode="Markdown",
    )


async def handle_barcode_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called when a photo arrives while waiting_for == 'barcode'."""
    context.user_data.pop("waiting_for", None)
    msg = update.message

    await msg.reply_text("🔍 Decoding barcode…")

    photo_file = await msg.photo[-1].get_file()
    photo_bytes = bytes(await photo_file.download_as_bytearray())

    barcode = bc_service.decode_barcode(photo_bytes)
    if not barcode:
        await msg.reply_text(
            "❌ Could not read a barcode from that photo.\n"
            "Try a clearer, well-lit image, or send the barcode *number* as text: `/barcode 5000112545747`",
            parse_mode="Markdown",
        )
        return

    await _process_barcode(msg, context, barcode)


async def handle_barcode_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Called by the text handler. Returns True if the text looked like a barcode number."""
    text = (update.message.text or "").strip()
    if not text.isdigit() or len(text) < 8:
        return False
    if context.user_data.get("waiting_for") != "barcode_text":
        return False

    context.user_data.pop("waiting_for", None)
    await _process_barcode(update.message, context, text)
    return True


async def _process_barcode(msg, context: ContextTypes.DEFAULT_TYPE, barcode: str) -> None:
    await msg.reply_text(f"🔎 Looking up barcode `{barcode}`…", parse_mode="Markdown")

    product = await bc_service.lookup_product(barcode)
    if not product:
        await msg.reply_text(
            f"❌ Product `{barcode}` not found in Open Food Facts database.\n"
            "You can add it at [openfoodfacts.org](https://world.openfoodfacts.org).",
            parse_mode="Markdown",
        )
        return

    nutrition = bc_service.extract_nutrition(product)
    if not nutrition:
        await msg.reply_text(
            f"⚠️ Found *{product.get('product_name', barcode)}* but it has no calorie data.",
            parse_mode="Markdown",
        )
        return

    # Store nutrition in user_data for the callback to pick up
    context.user_data["barcode_nutrition"] = nutrition

    cal = nutrition["calories_per_100g"]
    prot = nutrition["protein_per_100g"]
    carbs = nutrition["carbs_per_100g"]
    fat = nutrition["fat_per_100g"]
    fiber = nutrition["fiber_per_100g"]

    text = (
        f"✅ *{nutrition['name']}*\n"
        f"Per 100 g: *{cal} kcal* | P {prot}g · C {carbs}g · F {fat}g · Fib {fiber}g\n\n"
        "How many grams did you eat?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("50 g", callback_data="bc_gram_50"),
            InlineKeyboardButton("100 g", callback_data="bc_gram_100"),
            InlineKeyboardButton("150 g", callback_data="bc_gram_150"),
        ],
        [
            InlineKeyboardButton("200 g", callback_data="bc_gram_200"),
            InlineKeyboardButton("250 g", callback_data="bc_gram_250"),
            InlineKeyboardButton("300 g", callback_data="bc_gram_300"),
        ],
    ])
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def handle_barcode_gram_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, grams: int
) -> None:
    """Save the scanned product as a snack meal with the chosen gram amount."""
    query = update.callback_query
    await query.answer()

    nutrition = context.user_data.pop("barcode_nutrition", None)
    if not nutrition:
        await query.edit_message_text("⚠️ Session expired. Please scan again.")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await query.edit_message_text("⚠️ No user profile found.")
        return

    factor = grams / 100
    cal = round(nutrition["calories_per_100g"] * factor)
    prot = round(nutrition["protein_per_100g"] * factor * 10) / 10
    carbs = round(nutrition["carbs_per_100g"] * factor * 10) / 10
    fat = round(nutrition["fat_per_100g"] * factor * 10) / 10
    fiber = round(nutrition["fiber_per_100g"] * factor * 10) / 10

    tz = pytz.timezone(config.user_timezone)
    now = datetime.now(tz).isoformat()
    today = now.split("T")[0]
    meal_id = str(uuid.uuid4())
    user_id = profile["id"]

    try:
        await db.insert("meals", {
            "id": meal_id,
            "user_id": user_id,
            "meal_type": "snack",
            "eaten_at": now,
            "total_calories": cal,
            "total_protein_g": prot,
            "total_carbs_g": carbs,
            "total_fat_g": fat,
            "total_fiber_g": fiber,
            "notes": nutrition["name"],
            "status": "confirmed",
        })
        await db.insert("meal_items", {
            "meal_id": meal_id,
            "ingredient_name": nutrition["name"],
            "fdc_id": None,
            "weight_grams": grams,
            "weight_source": "barcode_lookup",
            "calories": cal,
            "protein_g": prot,
            "carbs_g": carbs,
            "fat_g": fat,
            "fiber_g": fiber,
        })

        # Refresh daily summary
        day_meals_res = (
            db.get_client()
            .table("meals")
            .select("total_calories,total_protein_g,total_carbs_g,total_fat_g,total_fiber_g")
            .eq("user_id", user_id)
            .eq("status", "confirmed")
            .gte("eaten_at", f"{today}T00:00:00")
            .lte("eaten_at", f"{today}T23:59:59")
            .execute()
        )
        if day_meals_res.data:
            day = day_meals_res.data
            dc = sum(m["total_calories"] or 0 for m in day)
            dp = sum(m["total_protein_g"] or 0 for m in day)
            dcarb = sum(m["total_carbs_g"] or 0 for m in day)
            df = sum(m["total_fat_g"] or 0 for m in day)
            dfib = sum(m["total_fiber_g"] or 0 for m in day)
            await db.upsert("daily_summary", {
                "user_id": user_id,
                "date": today,
                "total_calories_in": dc,
                "total_protein_g": round(dp * 10) / 10,
                "total_carbs_g": round(dcarb * 10) / 10,
                "total_fat_g": round(df * 10) / 10,
                "total_fiber_g": round(dfib * 10) / 10,
                "target_calories": profile.get("target_daily_calories", 2000),
                "net_calories": dc,
            }, on_conflict="user_id,date")

        await query.edit_message_text(
            f"✅ Logged *{nutrition['name']}* ({grams} g) — *{cal} kcal*",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Barcode meal save error: {e}")
        await query.edit_message_text("❌ Failed to save meal. Please try again.")
