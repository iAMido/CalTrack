import logging
from bot.db import supabase_client as db
from bot.db import queries as db_queries
from bot.utils.config import config

logger = logging.getLogger(__name__)


def calculate_bmr(weight_kg: float, height_cm: int, age: int, sex: str) -> int:
    """Mifflin-St Jeor equation."""
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age)
    return round(base + 5 if sex == "male" else base - 161)


def calculate_tdee(bmr: int, activity_factor: float) -> int:
    return round(bmr * activity_factor)


def calculate_target(tdee: int, weekly_deficit_kg: float, min_calories: int) -> int:
    daily_deficit = (weekly_deficit_kg * 7700) / 7
    target = round(tdee - daily_deficit)
    return max(target, min_calories)


async def recalibrate(trigger: str = "manual") -> dict:
    """Recalculate BMR/TDEE/target and update user_profile. Returns calibration result."""
    profile = await db_queries.get_user_profile()
    if not profile:
        raise ValueError("No user profile found")

    min_cal = config.min_calories_male if profile["sex"] == "male" else config.min_calories_female

    new_bmr = calculate_bmr(
        profile["current_weight_kg"],
        profile["height_cm"],
        profile["age"],
        profile["sex"],
    )
    new_tdee = calculate_tdee(new_bmr, profile.get("activity_factor", 1.55))
    new_target = calculate_target(new_tdee, profile.get("target_weekly_deficit_kg", 0.5), min_cal)

    old_bmr = profile.get("bmr")
    old_tdee = profile.get("tdee")
    old_target = profile.get("target_daily_calories")

    # Log calibration
    await db.insert("calibration_log", {
        "previous_weight_kg": profile["current_weight_kg"],
        "previous_bmr": old_bmr,
        "previous_tdee": old_tdee,
        "previous_target_calories": old_target,
        "new_weight_kg": profile["current_weight_kg"],
        "new_bmr": new_bmr,
        "new_tdee": new_tdee,
        "new_target_calories": new_target,
        "trigger": trigger,
    })

    # Update profile
    await db.update("user_profile", {"id": profile["id"]}, {
        "bmr": new_bmr,
        "tdee": new_tdee,
        "target_daily_calories": new_target,
        "last_calibration_date": "now()",
    })

    return {
        "old_bmr": old_bmr,
        "new_bmr": new_bmr,
        "old_tdee": old_tdee,
        "new_tdee": new_tdee,
        "old_target": old_target,
        "new_target": new_target,
        "weight_kg": profile["current_weight_kg"],
    }


def format_calibration_message(result: dict) -> str:
    lines = ["📊 *Calibration updated*\n"]
    lines.append(f"⚖️ Weight: {result['weight_kg']} kg")
    lines.append(f"🔥 BMR: {result['old_bmr']} → *{result['new_bmr']}* kcal")
    lines.append(f"📈 TDEE: {result['old_tdee']} → *{result['new_tdee']}* kcal")
    delta = (result['new_target'] or 0) - (result['old_target'] or 0)
    sign = "+" if delta >= 0 else ""
    lines.append(f"🎯 Daily target: {result['old_target']} → *{result['new_target']}* kcal ({sign}{delta})")
    return "\n".join(lines)
