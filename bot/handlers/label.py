import logging
import uuid
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.services import vision
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)
ALLOWED_CHAT_IDS = config.allowed_chat_ids

# Custom fdc_id range for user-scanned labels (above USDA range)
CUSTOM_FDC_BASE = 9_000_000


async def handle_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /label — start the label scanning flow.
    Bot asks the user to send a photo of the nutrition label.
    """
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return
    context.user_data["awaiting_label_photo"] = True
    await update.message.reply_text(
        "📷 Send a photo of the nutrition label and I'll extract the macros.\n"
        "Make sure the *per 100g* column is clearly visible.",
        parse_mode="Markdown",
    )


async def handle_label_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Called from photo handler when awaiting_label_photo is set.
    Returns True if it handled the photo, False otherwise.
    """
    if not context.user_data.pop("awaiting_label_photo", False):
        return False

    msg = update.message
    await msg.reply_text("🔍 Reading the nutrition label...")

    photo_file = await msg.photo[-1].get_file()
    photo_bytes = bytes(await photo_file.download_as_bytearray())

    try:
        label = await vision.extract_nutrition_label(photo_bytes)
    except Exception as e:
        logger.error(f"Label extraction failed: {e}")
        await msg.reply_text(
            "❌ Could not read the label. Make sure the nutrition table is clearly visible and try again.\n"
            "Use /label to start again."
        )
        return True

    food_name = label.get("food_name", "Custom Food")
    food_name_he = label.get("food_name_he", food_name)
    cal = label.get("calories_per_100g", 0)
    protein = label.get("protein_per_100g", 0)
    carbs = label.get("carbs_per_100g", 0)
    fat = label.get("fat_per_100g", 0)
    fiber = label.get("fiber_per_100g", 0)
    sodium = label.get("sodium_mg_per_100g", 0)

    # Save to usda_foundation with a synthetic fdc_id so it's matchable
    synthetic_fdc_id = CUSTOM_FDC_BASE + abs(hash(food_name.lower())) % 900_000

    await db.upsert("usda_foundation", {
        "fdc_id": synthetic_fdc_id,
        "description": food_name,
        "food_category": "Custom (Label Scan)",
        "calories_per_100g": cal,
        "protein_per_100g": protein,
        "carbs_per_100g": carbs,
        "fat_per_100g": fat,
        "fiber_per_100g": fiber,
        "sodium_mg_per_100g": sodium,
    }, on_conflict="fdc_id")

    # Also save to personal_foods so it shows in history
    existing = (
        db.get_client()
        .table("personal_foods")
        .select("*")
        .eq("ingredient_name", food_name)
        .execute()
        .data
    )
    if not existing:
        await db.insert("personal_foods", {
            "ingredient_name": food_name,
            "fdc_id": synthetic_fdc_id,
            "total_times_logged": 0,
            "total_corrections": 0,
        })

    # Add to in-memory USDA cache immediately
    from bot.services.nutrition import _usda_cache
    _usda_cache[synthetic_fdc_id] = {
        "fdc_id": synthetic_fdc_id,
        "description": food_name,
        "food_category": "Custom (Label Scan)",
        "calories_per_100g": cal,
        "protein_per_100g": protein,
        "carbs_per_100g": carbs,
        "fat_per_100g": fat,
        "fiber_per_100g": fiber,
        "sodium_mg_per_100g": sodium,
    }

    await msg.reply_text(
        f"✅ *{food_name}* ({food_name_he}) saved!\n\n"
        f"Per 100g:\n"
        f"• Calories: *{cal}* kcal\n"
        f"• Protein: *{protein}*g\n"
        f"• Carbs: *{carbs}*g\n"
        f"• Fat: *{fat}*g\n"
        f"• Fiber: *{fiber}*g\n\n"
        f"This food is now in your database. Next time you photograph it, it will be matched automatically.",
        parse_mode="Markdown",
    )
    return True
