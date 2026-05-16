import logging
import uuid
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.utils.formatters import detect_meal_type
from bot.db import supabase_client as db
from bot.db import queries as db_queries

logger = logging.getLogger(__name__)


async def handle_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /template — list saved meal templates as buttons for one-tap logging.
    /template <name> — log a template by name directly.
    """
    profile = await db_queries.get_user_profile()
    if not profile:
        await update.message.reply_text("⚠️ No profile found.")
        return

    client = db.get_client()
    result = (
        client.table("meal_templates")
        .select("id, name, total_calories, total_protein_g, total_carbs_g, total_fat_g")
        .eq("user_id", profile["id"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    templates = result.data or []

    if not templates:
        await update.message.reply_text(
            "📋 No templates saved yet.\n\n"
            "Save a template from the dashboard:\n"
            "Add Meal → add ingredients → Save as Template",
        )
        return

    # If user typed /template <name>, try to match and log directly
    args = " ".join(context.args).strip() if context.args else ""
    if args:
        match = next((t for t in templates if t["name"].lower() == args.lower()), None)
        if not match:
            # Partial match
            match = next((t for t in templates if args.lower() in t["name"].lower()), None)
        if match:
            await _log_template(update, match, profile)
            return
        else:
            await update.message.reply_text(f"❌ No template matching \"{args}\".")
            return

    # Show template list as inline buttons
    buttons = []
    for t in templates:
        cal = t.get("total_calories") or 0
        label = f"{t['name']} ({cal} kcal)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"tmpl:{t['id']}")])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="tmpl:cancel")])

    await update.message.reply_text(
        "📋 *Your Meal Templates*\nTap to log instantly:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def handle_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, template_id: str) -> None:
    """Handle template selection from inline keyboard."""
    query = update.callback_query

    if template_id == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        return

    profile = await db_queries.get_user_profile()
    if not profile:
        await query.edit_message_text("⚠️ No profile found.")
        return

    client = db.get_client()
    result = (
        client.table("meal_templates")
        .select("id, name, total_calories, total_protein_g, total_carbs_g, total_fat_g")
        .eq("id", template_id)
        .single()
        .execute()
    )

    if not result.data:
        await query.edit_message_text("❌ Template not found.")
        return

    await query.edit_message_text(f"⏳ Logging *{result.data['name']}*...", parse_mode="Markdown")
    await _log_template(update, result.data, profile, edit_message=query.message)


async def _log_template(update: Update, template: dict, profile: dict, edit_message=None) -> None:
    """Save a template as a new meal."""
    client = db.get_client()

    # Fetch template items
    items_result = (
        client.table("meal_template_items")
        .select("*")
        .eq("template_id", template["id"])
        .execute()
    )
    items = items_result.data or []

    if not items:
        msg = "❌ Template has no items."
        if edit_message:
            await edit_message.edit_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    tz = pytz.timezone(config.user_timezone)
    meal_id = str(uuid.uuid4())
    meal_type = detect_meal_type()

    # Calculate totals from items
    total_cal = sum(i.get("calories") or 0 for i in items)
    total_protein = round(sum(float(i.get("protein_g") or 0) for i in items), 1)
    total_carbs = round(sum(float(i.get("carbs_g") or 0) for i in items), 1)
    total_fat = round(sum(float(i.get("fat_g") or 0) for i in items), 1)
    total_fiber = round(sum(float(i.get("fiber_g") or 0) for i in items), 1)

    try:
        await db.upsert("meals", {
            "id": meal_id,
            "user_id": profile["id"],
            "meal_type": meal_type,
            "eaten_at": datetime.now(tz).isoformat(),
            "total_calories": total_cal,
            "total_protein_g": total_protein,
            "total_carbs_g": total_carbs,
            "total_fat_g": total_fat,
            "total_fiber_g": total_fiber,
            "notes": f"📋 {template['name']}",
            "status": "confirmed",
        }, on_conflict="id")

        for item in items:
            await db.insert("meal_items", {
                "meal_id": meal_id,
                "ingredient_name": item["ingredient_name"],
                "fdc_id": item.get("fdc_id"),
                "weight_grams": item["weight_grams"],
                "weight_source": "ai_estimate",
                "calories": item.get("calories"),
                "protein_g": item.get("protein_g"),
                "carbs_g": item.get("carbs_g"),
                "fat_g": item.get("fat_g"),
                "fiber_g": item.get("fiber_g"),
            })

        today = datetime.now(tz).strftime("%Y-%m-%d")
        daily = await db_queries.refresh_daily_summary(today, profile["id"])
        cal_in = daily.get("total_calories_in", 0)
        target = daily.get("target_calories", 2285)
        remaining = target - cal_in

    except Exception as e:
        logger.error(f"Failed to log template: {e}")
        msg = f"❌ Failed to save: {e}"
        if edit_message:
            await edit_message.edit_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    # Build response
    lines = [f"  • {i['ingredient_name']} ({i['weight_grams']}g) — {i.get('calories', 0)} kcal" for i in items]
    item_str = "\n".join(lines)

    response = (
        f"✅ Logged *{template['name']}* as {meal_type}\n"
        f"{item_str}\n"
        f"*Total: {total_cal} kcal*\n\n"
        f"Today: *{cal_in:,} / {target:,} kcal* | Remaining: *{remaining:,} kcal*"
    )

    if edit_message:
        await edit_message.edit_text(response, parse_mode="Markdown")
    else:
        await update.message.reply_text(response, parse_mode="Markdown")
