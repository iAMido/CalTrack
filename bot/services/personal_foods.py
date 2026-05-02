import statistics
import logging
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

AUTO_APPROVE_MIN_LOGS = 5
AUTO_APPROVE_MAX_CORRECTION_RATE = 0.20
AUTO_APPROVE_MAX_STD_DEV = 30.0


def _round_to_10(grams: int) -> int:
    return round(grams / 10) * 10


async def get_or_create_personal_food(ingredient_name: str, fdc_id: int | None) -> dict:
    rows = await db.select("personal_foods", {"ingredient_name": ingredient_name})
    if rows:
        return rows[0]
    return await db.insert("personal_foods", {
        "ingredient_name": ingredient_name,
        "fdc_id": fdc_id,
        "total_times_logged": 0,
        "total_times_corrected": 0,
    })


async def get_weight_history(personal_food_id: str, meal_type: str, limit: int = 5) -> list[int]:
    client = db.get_client()
    result = (
        client.table("personal_food_logs")
        .select("weight_grams")
        .eq("personal_food_id", personal_food_id)
        .eq("meal_type", meal_type)
        .order("logged_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [r["weight_grams"] for r in (result.data or [])]


async def should_auto_approve(personal_food_id: str, meal_type: str) -> tuple[bool, int | None]:
    """
    Returns (should_auto_approve, suggested_weight).
    Auto-approves only if all three criteria are met.
    """
    client = db.get_client()

    # Count total logs and corrections for this food+meal_type
    logs_result = (
        client.table("personal_food_logs")
        .select("weight_grams,was_corrected")
        .eq("personal_food_id", personal_food_id)
        .eq("meal_type", meal_type)
        .execute()
    )
    logs = logs_result.data or []

    if len(logs) < AUTO_APPROVE_MIN_LOGS:
        return False, None

    weights = [l["weight_grams"] for l in logs]
    corrections = sum(1 for l in logs if l.get("was_corrected"))
    correction_rate = corrections / len(logs)

    if correction_rate >= AUTO_APPROVE_MAX_CORRECTION_RATE:
        return False, None

    if len(weights) >= 2:
        std_dev = statistics.stdev(weights)
        if std_dev >= AUTO_APPROVE_MAX_STD_DEV:
            return False, None

    # All criteria met — use mode (most common weight)
    try:
        suggested = statistics.mode(weights)
    except statistics.StatisticsError:
        suggested = round(sum(weights) / len(weights))

    return True, suggested


async def get_weight_suggestions(personal_food_id: str, meal_type: str, ai_estimate: int) -> list[int]:
    """
    Returns 3–4 weight options for the inline keyboard.
    """
    history = await get_weight_history(personal_food_id, meal_type, limit=5)

    if len(history) >= 3:
        weights = history
        options = sorted(set([min(weights), statistics.mode(weights), max(weights)]))
    else:
        options = sorted(set([
            _round_to_10(int(ai_estimate * 0.75)),
            _round_to_10(ai_estimate),
            _round_to_10(int(ai_estimate * 1.25)),
        ]))

    return options


async def log_food_entry(
    personal_food_id: str,
    meal_id: str,
    meal_type: str,
    weight_grams: int,
    weight_source: str,
    ai_estimated_grams: int | None,
    was_corrected: bool,
) -> None:
    await db.insert("personal_food_logs", {
        "personal_food_id": personal_food_id,
        "meal_id": meal_id,
        "meal_type": meal_type,
        "weight_grams": weight_grams,
        "weight_source": weight_source,
        "ai_estimated_grams": ai_estimated_grams,
        "was_corrected": was_corrected,
    })

    # Increment counters on personal_foods
    food_rows = await db.select("personal_foods", {"id": personal_food_id})
    if food_rows:
        food = food_rows[0]
        update_data = {
            "total_times_logged": food.get("total_times_logged", 0) + 1,
            "last_logged_at": "now()",
        }
        if was_corrected:
            update_data["total_times_corrected"] = food.get("total_times_corrected", 0) + 1
        await db.update("personal_foods", {"id": personal_food_id}, update_data)


async def log_ai_correction(meal_item_id: str, ingredient_name: str, meal_type: str, ai_grams: int, user_grams: int) -> None:
    await db.insert("ai_corrections", {
        "meal_item_id": meal_item_id,
        "ingredient_name": ingredient_name,
        "meal_type": meal_type,
        "ai_estimated_grams": ai_grams,
        "user_corrected_grams": user_grams,
    })
