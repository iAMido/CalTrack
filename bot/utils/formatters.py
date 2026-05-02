from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pytz
from bot.utils.config import config


def get_meal_type_emoji(meal_type: str) -> str:
    return {"breakfast": "☀️", "lunch": "🌤", "dinner": "🌙", "snack": "🍪"}.get(meal_type, "🍽")


def detect_meal_type(tz_name: str = None) -> str:
    tz = pytz.timezone(tz_name or config.user_timezone)
    hour = datetime.now(tz).hour
    if 6 <= hour < 11:
        return "breakfast"
    elif 11 <= hour < 15:
        return "lunch"
    elif 15 <= hour < 18:
        return "snack"
    elif 18 <= hour < 23:
        return "dinner"
    else:
        return "snack"


def build_meal_keyboard(pending_meal: dict, nutrition_map: dict) -> tuple[str, InlineKeyboardMarkup]:
    """
    Build the inline keyboard for meal confirmation.

    pending_meal: dict with 'meal_type', 'items' list
    nutrition_map: {fdc_id: {calories, protein_g, carbs_g, fat_g}} for current weights

    Returns (message_text, InlineKeyboardMarkup)
    """
    meal_type = pending_meal["meal_type"]
    items = pending_meal["items"]
    now_str = datetime.now(pytz.timezone(config.user_timezone)).strftime("%B %d, %H:%M")
    emoji = get_meal_type_emoji(meal_type)

    lines = [f"{emoji} *{meal_type.capitalize()} — {now_str}*\n"]

    keyboard_rows = []
    total_cal = 0

    for idx, item in enumerate(items):
        name = item.get("ingredient_name", "Unknown")
        name_he = item.get("ingredient_name_he", "")
        weight = item["weight_grams"]
        ai_weight = item.get("ai_estimated_grams", weight)
        confidence = item.get("ai_confidence", 0)
        auto = item.get("auto_approved", False)
        suggestions = item.get("weight_suggestions", [])

        # Calculate nutrition for this item
        fdc_id = item.get("fdc_id")
        nutrition = nutrition_map.get(fdc_id) or {}
        cal = nutrition.get("calories", 0)
        total_cal += cal

        if auto:
            lines.append(f"*{idx + 1}. {name}* ({name_he})")
            lines.append(f"   ✅ Auto-approved: {weight}g _(from history)_\n")
        else:
            conf_pct = int(confidence * 100)
            lines.append(f"*{idx + 1}. {name}* ({name_he})")
            lines.append(f"   AI estimate: {ai_weight}g (confidence: {conf_pct}%)")

            # Build weight buttons from suggestions
            btn_row = []
            for w in suggestions:
                label = f"{'✓ ' if w == weight else ''}{w}g"
                btn_row.append(InlineKeyboardButton(label, callback_data=f"w:{idx}:{w}"))
            btn_row.append(InlineKeyboardButton("✏️", callback_data=f"w:{idx}:m"))
            keyboard_rows.append(btn_row)
            lines.append("")

    # Aggregate totals (rough sum)
    lines.append("─────────────────────")
    lines.append(f"Total: ~{total_cal} kcal")

    # Action buttons
    keyboard_rows.append([
        InlineKeyboardButton("✅ Confirm All", callback_data="ok"),
        InlineKeyboardButton("❌ Cancel", callback_data="no"),
    ])
    keyboard_rows.append([
        InlineKeyboardButton("🔄 Re-analyze", callback_data="re"),
        InlineKeyboardButton("📝 Add item", callback_data="add"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard_rows)


def format_post_save(daily: dict) -> str:
    cal_in = daily.get("total_calories_in", 0)
    target = daily.get("target_calories", 2000)
    remaining = target - cal_in
    burned = daily.get("calories_burned_exercise", 0)
    meal_count = daily.get("meal_count", 0)
    water_ml = daily.get("water_ml", 0)
    water_l = water_ml / 1000

    sign = "🏃" if burned > 0 else ""
    burn_str = f" | {sign} -{burned} kcal" if burned > 0 else ""

    return (
        f"✅ *Saved!*\n\n"
        f"Today: *{cal_in:,} / {target:,} kcal*{burn_str}\n"
        f"Remaining: *{remaining:,} kcal*\n"
        f"Meals: {meal_count} | 💧 {water_l:.1f}L"
    )


def format_daily_summary(date_str: str, daily: dict, meals: list) -> str:
    lines = [f"📊 *{date_str}*\n"]

    if meals:
        lines.append("🍽 *Meals:*")
        for m in meals:
            emoji = get_meal_type_emoji(m.get("meal_type", "snack"))
            eaten_at = m.get("eaten_at", "")
            time_str = ""
            if eaten_at:
                try:
                    dt = datetime.fromisoformat(eaten_at.replace("Z", "+00:00"))
                    tz = pytz.timezone(config.user_timezone)
                    time_str = f" ({dt.astimezone(tz).strftime('%H:%M')})"
                except Exception:
                    pass
            lines.append(f"  {emoji} {m.get('meal_type', '').capitalize()}: {m.get('total_calories', 0):,} kcal{time_str}")
    else:
        lines.append("No meals logged yet.")

    lines.append("")
    cal_in = daily.get("total_calories_in", 0)
    burned = daily.get("calories_burned_exercise", 0)
    net = cal_in - burned
    target = daily.get("target_calories", 0)
    deficit = net - target

    lines.append(f"📥 Total in:  *{cal_in:,} kcal*")
    if burned:
        lines.append(f"📤 Exercise:  *-{burned:,} kcal*")
    lines.append(f"📊 Net:       *{net:,} kcal*")
    if target:
        lines.append(f"🎯 Target:    *{target:,} kcal*")
        symbol = "✅" if deficit < 0 else "⚠️"
        label = "Deficit" if deficit < 0 else "Surplus"
        lines.append(f"{symbol} {label}:   *{deficit:+,} kcal*")

    protein = daily.get("total_protein_g", 0)
    carbs = daily.get("total_carbs_g", 0)
    fat = daily.get("total_fat_g", 0)
    fiber = daily.get("total_fiber_g", 0)
    if cal_in > 0:
        lines.append(f"\n💪 Macros: P {protein:.0f}g | C {carbs:.0f}g | F {fat:.0f}g | Fiber {fiber:.0f}g")

    water_ml = daily.get("water_ml", 0)
    if water_ml:
        lines.append(f"💧 Water: {water_ml / 1000:.1f}L")

    weight = daily.get("weight_kg")
    if weight:
        lines.append(f"⚖️ Weight: {weight} kg")

    return "\n".join(lines)
