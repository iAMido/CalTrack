import logging
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.services import nutrition as nut_service, personal_foods as pf
from bot.services.daily_summary import get_status_text
from bot.utils.formatters import build_meal_keyboard, format_post_save
from bot.db import supabase_client as db
from bot.db import queries as db_queries

logger = logging.getLogger(__name__)
ALLOWED_CHAT_IDS = config.allowed_chat_ids


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        await query.answer()
        return

    await query.answer()
    data = query.data

    if data.startswith("w:"):
        await _handle_weight_selection(query, context, data)
    elif data == "ok":
        await _handle_confirm_all(query, context)
    elif data == "no":
        await _handle_cancel(query, context)
    elif data == "re":
        await _handle_reanalyze(query, context)
    elif data.startswith("undo:"):
        await _handle_undo_confirm(query, context, data)
    elif data.startswith("mt:"):
        await _handle_meal_type_change(query, context, data)
    elif data == "add":
        await _handle_add_item(query, context)


async def _handle_add_item(query, context) -> None:
    """Prompt user to type a manual item as 'name,grams'."""
    pending = context.user_data.get("pending_meal")
    if not pending:
        await query.edit_message_text("❌ Session expired. Please send the photo again.")
        return
    context.user_data["awaiting_add_item"] = True
    await query.edit_message_text(
        "✏️ Type the item to add in this format:\n`item name, grams`\n\nExample: `white rice, 150`",
        parse_mode="Markdown",
    )


async def _handle_weight_selection(query, context, data: str) -> None:
    """Handle weight button press: w:{idx}:{grams|m}"""
    pending = context.user_data.get("pending_meal")
    if not pending:
        await query.edit_message_text("❌ Session expired. Please send the photo again.")
        return

    parts = data.split(":")
    idx = int(parts[1])
    value = parts[2]

    if value == "m":
        # Manual entry — ask user to type the weight
        item_name = pending["items"][idx].get("ingredient_name", "item")
        context.user_data["awaiting_manual_weight"] = idx
        await query.edit_message_text(
            f"✏️ Enter weight in grams for *{item_name}*:\n(Reply with a number, e.g. `150`)",
            parse_mode="Markdown",
        )
        return

    new_weight = int(value)
    pending["items"][idx]["weight_grams"] = new_weight
    pending["items"][idx]["weight_source"] = "user_confirmed"

    # Recalculate nutrition
    fdc_id = pending["items"][idx].get("fdc_id")
    ai_fallback = pending["items"][idx].get("ai_fallback")
    nut = nut_service.calculate_nutrition(fdc_id, new_weight, ai_fallback)
    pending["items"][idx].update(nut)

    # Rebuild keyboard
    nutrition_map = {
        item["fdc_id"]: nut_service.calculate_nutrition(item["fdc_id"], item["weight_grams"], item.get("ai_fallback"))
        for item in pending["items"] if item.get("fdc_id")
    }
    text, keyboard = build_meal_keyboard(pending, nutrition_map)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def _handle_confirm_all(query, context) -> None:
    """Save the confirmed meal to the database."""
    pending = context.user_data.get("pending_meal")
    if not pending:
        await query.edit_message_text("❌ Session expired. Please send the photo again.")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await query.edit_message_text("⚠️ No user profile found.")
        return

    tz = pytz.timezone(config.user_timezone)
    items = pending["items"]

    # Calculate totals
    totals = nut_service.calculate_meal_totals(items)

    # Insert meal
    meal_row = {
        "id": pending["meal_id"],
        "user_id": profile["id"],
        "meal_type": pending["meal_type"],
        "eaten_at": datetime.now(tz).isoformat(),
        "photo_path": pending.get("photo_path"),
        "total_calories": totals["total_calories"],
        "total_protein_g": totals["total_protein_g"],
        "total_carbs_g": totals["total_carbs_g"],
        "total_fat_g": totals["total_fat_g"],
        "total_fiber_g": totals["total_fiber_g"],
        "ai_model_used": pending.get("ai_model"),
        "status": "confirmed",
    }
    meal = await db.upsert("meals", meal_row, on_conflict="id")
    meal_id = meal.get("id") or pending["meal_id"]

    # Insert meal items + update personal foods
    for item in items:
        ai_weight = item.get("ai_estimated_grams")
        confirmed_weight = item["weight_grams"]
        was_corrected = ai_weight is not None and ai_weight != confirmed_weight
        weight_source = item.get("weight_source", "user_confirmed")

        item_row = {
            "meal_id": meal_id,
            "ingredient_name": item.get("ingredient_name"),
            "ingredient_name_he": item.get("ingredient_name_he"),
            "fdc_id": item.get("fdc_id"),
            "weight_grams": confirmed_weight,
            "weight_source": weight_source,
            "ai_estimated_grams": ai_weight,
            "calories": item.get("calories"),
            "protein_g": item.get("protein_g"),
            "carbs_g": item.get("carbs_g"),
            "fat_g": item.get("fat_g"),
            "fiber_g": item.get("fiber_g"),
            "ai_confidence": item.get("ai_confidence"),
        }
        saved_item = await db.insert("meal_items", item_row)

        # Update personal food logs
        pf_id = item.get("personal_food_id")
        if pf_id:
            await pf.log_food_entry(
                personal_food_id=pf_id,
                meal_id=meal_id,
                meal_type=pending["meal_type"],
                weight_grams=confirmed_weight,
                weight_source=weight_source,
                ai_estimated_grams=ai_weight,
                was_corrected=was_corrected,
            )
            # Log AI correction if applicable
            if was_corrected and saved_item.get("id"):
                await pf.log_ai_correction(
                    saved_item["id"],
                    item.get("ingredient_name", ""),
                    pending["meal_type"],
                    ai_weight,
                    confirmed_weight,
                )

    # Refresh daily summary
    today = datetime.now(tz).strftime("%Y-%m-%d")
    daily = await db_queries.refresh_daily_summary(today, profile["id"])

    # Clear pending state
    context.user_data.pop("pending_meal", None)

    await query.edit_message_text(format_post_save(daily), parse_mode="Markdown")


async def _handle_cancel(query, context) -> None:
    context.user_data.pop("pending_meal", None)
    await query.edit_message_text("❌ Meal cancelled.")


async def _handle_reanalyze(query, context) -> None:
    pending = context.user_data.get("pending_meal")
    if not pending:
        await query.edit_message_text("❌ Session expired. Please send the photo again.")
        return
    context.user_data.pop("pending_meal", None)
    await query.edit_message_text("🔄 Please send the photo again to re-analyze.")


async def _handle_undo_confirm(query, context, data: str) -> None:
    meal_id = data.split(":")[1]
    if meal_id == "cancel":
        await query.edit_message_text("✅ Meal kept.")
        return

    profile = await db_queries.get_user_profile()
    await db.update("meals", {"id": meal_id}, {"status": "cancelled"})

    tz = pytz.timezone(config.user_timezone)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    if profile:
        await db_queries.refresh_daily_summary(today, profile["id"])

    await query.edit_message_text("↩️ Last meal undone.")


async def _handle_meal_type_change(query, context, data: str) -> None:
    new_type = data.split(":")[1]
    pending = context.user_data.get("pending_meal")
    if pending:
        pending["meal_type"] = new_type
        nutrition_map = {
            item["fdc_id"]: nut_service.calculate_nutrition(item["fdc_id"], item["weight_grams"], item.get("ai_fallback"))
            for item in pending["items"] if item.get("fdc_id")
        }
        text, keyboard = build_meal_keyboard(pending, nutrition_map)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text replies for manual weight entry and add-item flow."""
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        return

    text = (update.message.text or "").strip()
    pending = context.user_data.get("pending_meal")

    # --- Manual weight for existing item ---
    if "awaiting_manual_weight" in context.user_data:
        idx = context.user_data.pop("awaiting_manual_weight")
        if not pending:
            await update.message.reply_text("Session expired. Please send the photo again.")
            return
        try:
            grams = int(float(text))
            if grams <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Please enter a valid number of grams, e.g. `150`", parse_mode="Markdown")
            context.user_data["awaiting_manual_weight"] = idx
            return

        pending["items"][idx]["weight_grams"] = grams
        pending["items"][idx]["weight_source"] = "user_confirmed"
        fdc_id = pending["items"][idx].get("fdc_id")
        pending["items"][idx].update(nut_service.calculate_nutrition(fdc_id, grams, pending["items"][idx].get("ai_fallback")))

        nutrition_map = {
            item["fdc_id"]: nut_service.calculate_nutrition(item["fdc_id"], item["weight_grams"], item.get("ai_fallback"))
            for item in pending["items"] if item.get("fdc_id")
        }
        msg_text, keyboard = build_meal_keyboard(pending, nutrition_map)
        await update.message.reply_text(msg_text, reply_markup=keyboard, parse_mode="Markdown")
        return

    # --- Add new item ---
    if context.user_data.pop("awaiting_add_item", False):
        if not pending:
            await update.message.reply_text("Session expired. Please send the photo again.")
            return
        try:
            # Accept "name, grams" or "name grams"
            if "," in text:
                name_part, grams_part = text.rsplit(",", 1)
            else:
                parts = text.rsplit(None, 1)
                if len(parts) != 2:
                    raise ValueError
                name_part, grams_part = parts
            name = name_part.strip()
            grams = int(float(grams_part.strip()))
            if not name or grams <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            await update.message.reply_text(
                "Format not recognised. Try: `chicken breast, 150`", parse_mode="Markdown"
            )
            context.user_data["awaiting_add_item"] = True
            return

        new_item = {
            "ingredient_name": name,
            "ingredient_name_he": name,
            "fdc_id": None,
            "weight_grams": grams,
            "ai_estimated_grams": grams,
            "weight_source": "user_confirmed",
            "ai_confidence": 1.0,
            "auto_approved": False,
        }
        new_item.update(nut_service.calculate_nutrition(None, grams))
        pending["items"].append(new_item)

        nutrition_map = {
            item["fdc_id"]: nut_service.calculate_nutrition(item["fdc_id"], item["weight_grams"])
            for item in pending["items"] if item.get("fdc_id")
        }
        msg_text, keyboard = build_meal_keyboard(pending, nutrition_map)
        await update.message.reply_text(msg_text, reply_markup=keyboard, parse_mode="Markdown")
