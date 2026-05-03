import logging
from datetime import datetime, timedelta, date
import pytz
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


async def get_7day_weight_avg() -> float | None:
    """Average weight from the last 7 days of weight_log. Returns None if no data."""
    tz = pytz.timezone(config.user_timezone)
    since = (datetime.now(tz) - timedelta(days=7)).isoformat()
    client = db.get_client()
    result = (
        client.table("weight_log")
        .select("weight_kg")
        .gte("measured_at", since)
        .execute()
    )
    weights = [r["weight_kg"] for r in (result.data or [])]
    return round(sum(weights) / len(weights), 2) if weights else None


async def get_weight_trend_7d() -> float | None:
    """Weight change over last 7 days (negative = lost). None if < 2 data points."""
    tz = pytz.timezone(config.user_timezone)
    since = (datetime.now(tz) - timedelta(days=7)).isoformat()
    client = db.get_client()
    result = (
        client.table("weight_log")
        .select("weight_kg,measured_at")
        .gte("measured_at", since)
        .order("measured_at", desc=False)
        .execute()
    )
    rows = result.data or []
    if len(rows) < 2:
        return None
    return round(rows[-1]["weight_kg"] - rows[0]["weight_kg"], 2)


async def get_last_calibration() -> dict | None:
    client = db.get_client()
    result = (
        client.table("calibration_log")
        .select("*")
        .order("calibrated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def recalibrate(trigger: str = "manual") -> dict:
    """Recalculate BMR/TDEE/target and update user_profile. Returns calibration result dict."""
    profile = await db_queries.get_user_profile()
    if not profile:
        raise ValueError("No user profile found")

    min_cal = config.min_calories_male if profile["sex"] == "male" else config.min_calories_female

    # Use 7-day average weight when available — more stable than a single reading
    avg_weight = await get_7day_weight_avg()
    weight_for_calc = avg_weight if avg_weight else profile["current_weight_kg"]
    trend = await get_weight_trend_7d()

    new_bmr = calculate_bmr(
        weight_for_calc,
        profile["height_cm"],
        profile["age"],
        profile["sex"],
    )
    new_tdee = calculate_tdee(new_bmr, profile.get("activity_factor", 1.55))
    new_target = calculate_target(new_tdee, profile.get("target_weekly_deficit_kg", 0.5), min_cal)

    old_bmr = profile.get("bmr")
    old_tdee = profile.get("tdee")
    old_target = profile.get("target_daily_calories")

    tz = pytz.timezone(config.user_timezone)
    today = datetime.now(tz).strftime("%Y-%m-%d")

    await db.insert("calibration_log", {
        "previous_weight_kg": profile["current_weight_kg"],
        "previous_bmr": old_bmr,
        "previous_tdee": old_tdee,
        "previous_target_calories": old_target,
        "new_weight_kg": weight_for_calc,
        "new_bmr": new_bmr,
        "new_tdee": new_tdee,
        "new_target_calories": new_target,
        "weight_trend_7d": trend,
        "calibration_trigger": trigger,
    })

    await db.update("user_profile", {"id": profile["id"]}, {
        "bmr": new_bmr,
        "tdee": new_tdee,
        "target_daily_calories": new_target,
        "last_calibration_date": today,
    })

    return {
        "trigger": trigger,
        "weight_used_kg": weight_for_calc,
        "weight_trend_7d": trend,
        "old_bmr": old_bmr,
        "new_bmr": new_bmr,
        "old_tdee": old_tdee,
        "new_tdee": new_tdee,
        "old_target": old_target,
        "new_target": new_target,
    }


async def check_and_recalibrate() -> dict | None:
    """
    Auto-trigger calibration if warranted. Returns result dict if recalibrated, else None.

    Triggers:
    - weight_milestone: current weight differs ≥2 kg from weight at last calibration
    - weekly_auto: last calibration was ≥7 days ago (or never)
    """
    profile = await db_queries.get_user_profile()
    if not profile:
        return None

    last_cal = await get_last_calibration()

    # Milestone check
    if last_cal:
        delta = abs(profile["current_weight_kg"] - last_cal["new_weight_kg"])
        if delta >= 2.0:
            logger.info(f"Weight milestone triggered: Δ{delta:.1f} kg")
            return await recalibrate(trigger="weight_milestone")

    # Weekly check
    last_date = profile.get("last_calibration_date")
    if not last_date:
        return await recalibrate(trigger="weekly_auto")

    days_since = (date.today() - date.fromisoformat(str(last_date))).days
    if days_since >= 7:
        logger.info(f"Weekly auto-calibration triggered ({days_since} days since last)")
        return await recalibrate(trigger="weekly_auto")

    return None


def format_calibration_message(result: dict) -> str:
    trigger_label = {
        "manual": "manual",
        "weekly_auto": "weekly auto",
        "weight_milestone": "weight milestone",
    }.get(result.get("trigger", "manual"), "")

    lines = [f"📊 *Calibration updated* ({trigger_label})\n"]
    lines.append(f"⚖️ Weight used: *{result['weight_used_kg']} kg* (7-day avg)")

    trend = result.get("weight_trend_7d")
    if trend is not None:
        direction = "📉" if trend < 0 else "📈"
        lines.append(f"{direction} 7-day trend: *{trend:+.1f} kg*")

    lines.append(f"🔥 BMR: {result['old_bmr']} → *{result['new_bmr']}* kcal")
    lines.append(f"📈 TDEE: {result['old_tdee']} → *{result['new_tdee']}* kcal")

    delta = (result["new_target"] or 0) - (result["old_target"] or 0)
    sign = "+" if delta >= 0 else ""
    lines.append(f"🎯 Daily target: {result['old_target']} → *{result['new_target']}* kcal ({sign}{delta})")

    return "\n".join(lines)
