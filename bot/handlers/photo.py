import io
import uuid
import logging
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.utils.formatters import build_meal_keyboard, detect_meal_type
from bot.services import vision, nutrition, personal_foods as pf
from bot.db import supabase_client as db
from bot.db import queries as db_queries

logger = logging.getLogger(__name__)

ALLOWED_CHAT_IDS = config.allowed_chat_ids


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return

    msg = update.message
    await msg.reply_text("🔍 Analyzing your meal...")

    # Download the photo (highest resolution)
    photo_file = await msg.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    # Upload to Supabase Storage
    meal_id = str(uuid.uuid4())
    tz = pytz.timezone(config.user_timezone)
    date_str = datetime.now(tz).strftime("%Y-%m-%d")
    storage_path = f"{date_str}/{meal_id}.jpg"

    try:
        await db.upload_photo(bytes(photo_bytes), storage_path)
    except Exception as e:
        logger.warning(f"Photo upload failed (continuing without storage): {e}")
        storage_path = None

    # Detect meal type from time of day
    meal_type = detect_meal_type()

    # Get recent AI corrections as few-shot examples
    corrections = await _get_corrections_summary()

    # Call Vision AI
    try:
        ai_items = await vision.analyze_meal_photo(bytes(photo_bytes), corrections=corrections)
    except Exception as e:
        logger.error(f"Vision AI error: {e}")
        await msg.reply_text(f"❌ Could not analyze the photo: {e}\n\nPlease try again or use /summary to log manually.")
        return

    if not ai_items:
        await msg.reply_text("🤔 I couldn't identify any food in this photo. Try a clearer photo or use `/add` to log manually.")
        return

    # Enrich items: check personal food history, get weight suggestions
    enriched_items = []
    profile = await db_queries.get_user_profile()

    for item in ai_items:
        ingredient_name = item.get("ingredient_name", "")
        # AI no longer returns fdc_id — find best USDA match locally
        fdc_id = nutrition.find_usda_match(ingredient_name)
        ai_weight = item.get("estimated_weight_grams", 100)
        confidence = item.get("confidence", 0.5)

        # Get or create personal food record
        pf_record = await pf.get_or_create_personal_food(ingredient_name, fdc_id)
        pf_id = pf_record.get("id")

        # Check auto-approve
        auto_approve, auto_weight = await pf.should_auto_approve(pf_id, meal_type)

        if auto_approve and auto_weight:
            confirmed_weight = auto_weight
            weight_source = "personal_db_auto"
            suggestions = [auto_weight]
        else:
            confirmed_weight = ai_weight
            weight_source = "ai_estimate"
            suggestions = await pf.get_weight_suggestions(pf_id, meal_type, ai_weight)

        # AI-provided nutrition values as fallback when no USDA match
        ai_fallback = {
            "calories_per_100g": item.get("calories_per_100g"),
            "protein_per_100g": item.get("protein_per_100g"),
            "carbs_per_100g": item.get("carbs_per_100g"),
            "fat_per_100g": item.get("fat_per_100g"),
            "fiber_per_100g": item.get("fiber_per_100g"),
        } if item.get("calories_per_100g") else None

        # Calculate nutrition at current weight
        nut = nutrition.calculate_nutrition(fdc_id, confirmed_weight, ai_fallback)

        enriched_items.append({
            "ingredient_name": ingredient_name,
            "ingredient_name_he": item.get("ingredient_name_he", ""),
            "fdc_id": fdc_id,
            "ai_fallback": ai_fallback,
            "weight_grams": confirmed_weight,
            "ai_estimated_grams": ai_weight,
            "ai_confidence": confidence,
            "weight_source": weight_source,
            "auto_approved": auto_approve,
            "weight_suggestions": suggestions,
            "personal_food_id": pf_id,
            **nut,
        })

    # Build nutrition map for keyboard display
    nutrition_map = {
        item["fdc_id"]: nutrition.calculate_nutrition(item["fdc_id"], item["weight_grams"])
        for item in enriched_items
        if item.get("fdc_id")
    }

    # Store pending meal in context
    context.user_data["pending_meal"] = {
        "meal_id": meal_id,
        "meal_type": meal_type,
        "photo_path": storage_path,
        "photo_file_id": msg.photo[-1].file_id,
        "items": enriched_items,
        "user_id": profile["id"] if profile else None,
        "ai_model": config.openrouter_vision_model,
    }

    # Build and send confirmation keyboard
    text, keyboard = build_meal_keyboard({"meal_type": meal_type, "items": enriched_items}, nutrition_map)

    await msg.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def _get_corrections_summary(limit: int = 10) -> list[dict]:
    """Get most frequent AI corrections for few-shot prompt improvement."""
    try:
        client = db.get_client()
        # Manual aggregation since supabase-py doesn't support GROUP BY directly
        result = (
            client.table("ai_corrections")
            .select("ingredient_name,meal_type,ai_estimated_grams,user_corrected_grams")
            .execute()
        )
        rows = result.data or []

        # Aggregate in Python
        agg: dict[tuple, list] = {}
        for r in rows:
            key = (r["ingredient_name"], r["meal_type"])
            agg.setdefault(key, []).append(r)

        corrections = []
        for (name, meal_type), entries in agg.items():
            if len(entries) >= 3:
                corrections.append({
                    "ingredient_name": name,
                    "meal_type": meal_type,
                    "avg_ai_estimate": round(sum(e["ai_estimated_grams"] for e in entries) / len(entries)),
                    "avg_user_correction": round(sum(e["user_corrected_grams"] for e in entries) / len(entries)),
                    "times_corrected": len(entries),
                })

        return sorted(corrections, key=lambda x: -x["times_corrected"])[:limit]
    except Exception as e:
        logger.warning(f"Could not load corrections: {e}")
        return []
