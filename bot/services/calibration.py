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


# ── Energy model ─────────────────────────────────────────────────────
# CalTrack tracks every workout explicitly and credits its calories to
# the daily budget (dashboard, /status, coach all do target + exercise).
# The activity factor must therefore be the SEDENTARY baseline — using
# 1.55 ("moderately active", which already includes 3-5 workouts/week)
# would count the same run twice: once inside the multiplier, once as
# an explicit credit. That inflates run-day budgets by 300-500 kcal.
SEDENTARY_ACTIVITY_FACTOR = 1.2


def calculate_tdee(bmr: int, activity_factor: float) -> int:
    return round(bmr * activity_factor)


def calculate_target(tdee: int, weekly_deficit_kg: float, min_calories: int) -> int:
    daily_deficit = (weekly_deficit_kg * 7700) / 7
    target = round(tdee - daily_deficit)
    return max(target, min_calories)


async def get_7day_weight_avg(user_id: str | None = None) -> float | None:
    """Average weight from the last 7 days of weight_log. Returns None if no data."""
    tz = pytz.timezone(config.user_timezone)
    since = (datetime.now(tz) - timedelta(days=7)).isoformat()
    client = db.get_client()
    query = client.table("weight_log").select("weight_kg").gte("measured_at", since)
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.execute()
    weights = [r["weight_kg"] for r in (result.data or [])]
    return round(sum(weights) / len(weights), 2) if weights else None


async def get_weight_trend_7d(user_id: str | None = None) -> float | None:
    """Weight change over last 7 days (negative = lost). None if < 2 data points."""
    tz = pytz.timezone(config.user_timezone)
    since = (datetime.now(tz) - timedelta(days=7)).isoformat()
    client = db.get_client()
    query = (
        client.table("weight_log")
        .select("weight_kg,measured_at")
        .gte("measured_at", since)
        .order("measured_at", desc=False)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.execute()
    rows = result.data or []
    if len(rows) < 2:
        return None
    return round(rows[-1]["weight_kg"] - rows[0]["weight_kg"], 2)


async def get_last_calibration(user_id: str | None = None) -> dict | None:
    client = db.get_client()
    query = (
        client.table("calibration_log")
        .select("*")
        .order("calibrated_at", desc=True)
        .limit(1)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.execute()
    return result.data[0] if result.data else None


async def get_empirical_tdee(user_id: str, window_days: int = 28) -> dict | None:
    """Back-solve the user's ACTUAL base burn rate from their own data.

    Energy balance over a window:
        intake − (base_tdee + exercise) = Δweight_kg × 7700 / days
    so:
        base_tdee = avg_intake − avg_exercise − (Δkg × 7700 / days)

    This measures the real metabolism instead of estimating it from
    population formulas — the same idea MacroFactor is built on.

    Returns None when the data isn't trustworthy enough:
      - fewer than 14 fully-logged days (≥800 kcal and ≥2 meals/day)
      - fewer than 4 weigh-ins, or weigh-ins spanning under 14 days
      - implausible result (outside 800–5000 kcal)
    """
    tz = pytz.timezone(config.user_timezone)
    since = (datetime.now(tz) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    client = db.get_client()

    days = (
        client.table("daily_summary")
        .select("date,total_calories_in,calories_burned_exercise,meal_count")
        .eq("user_id", user_id)
        .gte("date", since)
        .order("date", desc=False)
        .execute().data or []
    )
    # Only fully-logged days — a day with one 300 kcal snack logged would
    # drag the average down and corrupt the estimate.
    logged = [
        d for d in days
        if (d.get("total_calories_in") or 0) >= 800 and (d.get("meal_count") or 0) >= 2
    ]
    if len(logged) < 14:
        return None

    weights = (
        client.table("weight_log")
        .select("weight_kg,measured_at")
        .eq("user_id", user_id)
        .gte("measured_at", f"{since}T00:00:00")
        .order("measured_at", desc=False)
        .execute().data or []
    )
    if len(weights) < 4:
        return None

    try:
        first_dt = datetime.fromisoformat(str(weights[0]["measured_at"]).replace("Z", "+00:00"))
        last_dt = datetime.fromisoformat(str(weights[-1]["measured_at"]).replace("Z", "+00:00"))
    except Exception:
        return None
    span_days = (last_dt - first_dt).days
    if span_days < 14:
        return None

    # Smooth scale noise: average the first k and last k weigh-ins
    k = min(3, len(weights) // 2)
    w_start = sum(float(w["weight_kg"]) for w in weights[:k]) / k
    w_end = sum(float(w["weight_kg"]) for w in weights[-k:]) / k
    delta_kg = w_end - w_start

    avg_intake = sum(d["total_calories_in"] for d in logged) / len(logged)
    avg_exercise = sum(d.get("calories_burned_exercise") or 0 for d in logged) / len(logged)
    daily_imbalance = delta_kg * 7700 / span_days
    base_tdee = round(avg_intake - avg_exercise - daily_imbalance)

    if not (800 <= base_tdee <= 5000):
        return None

    return {
        "base_tdee": base_tdee,
        "days_logged": len(logged),
        "weigh_in_span_days": span_days,
        "avg_intake": round(avg_intake),
        "avg_exercise": round(avg_exercise),
        "weight_delta_kg": round(delta_kg, 2),
    }


async def recalibrate(trigger: str = "manual") -> dict:
    """Recalculate BMR/TDEE/target and update user_profile. Returns calibration result dict."""
    profile = await db_queries.get_user_profile()
    if not profile:
        raise ValueError("No user profile found")

    min_cal = config.min_calories_male if profile["sex"] == "male" else config.min_calories_female

    # Use 7-day average weight when available — more stable than a single reading
    avg_weight = await get_7day_weight_avg(profile["id"])
    weight_for_calc = avg_weight if avg_weight else profile["current_weight_kg"]
    trend = await get_weight_trend_7d(profile["id"])

    new_bmr = calculate_bmr(
        weight_for_calc,
        profile["height_cm"],
        profile["age"],
        profile["sex"],
    )

    # Formula TDEE — sedentary baseline; logged exercise is credited
    # explicitly per-day, so it must NOT be baked into the multiplier.
    # Cap at the sedentary factor even if the profile row still carries
    # a legacy 1.55 value.
    activity_factor = min(
        float(profile.get("activity_factor") or SEDENTARY_ACTIVITY_FACTOR),
        SEDENTARY_ACTIVITY_FACTOR,
    )
    formula_tdee = calculate_tdee(new_bmr, activity_factor)

    # Empirical TDEE — measured from the user's own intake + weight trend.
    # Blend by data quantity: more fully-logged days → trust the
    # measurement more (capped at 75% so the formula always anchors it).
    empirical = await get_empirical_tdee(profile["id"])
    if empirical:
        blend_w = min(empirical["days_logged"] / 28, 0.75)
        new_tdee = round(blend_w * empirical["base_tdee"] + (1 - blend_w) * formula_tdee)
    else:
        blend_w = 0.0
        new_tdee = formula_tdee

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
        "formula_tdee": formula_tdee,
        "empirical": empirical,
        "blend_weight": blend_w,
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

    last_cal = await get_last_calibration(profile["id"])

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

    # Show the formula-vs-measured breakdown when we have real data
    empirical = result.get("empirical")
    if empirical:
        blend_pct = round(result.get("blend_weight", 0) * 100)
        lines.append(
            f"   🧮 Formula: {result.get('formula_tdee')} kcal | "
            f"📐 Measured: *{empirical['base_tdee']}* kcal "
            f"({empirical['days_logged']}d of your data, {blend_pct}% weight)"
        )
        lines.append(
            f"   _Measured from {empirical['avg_intake']} kcal/day eaten, "
            f"{empirical['weight_delta_kg']:+.1f} kg over {empirical['weigh_in_span_days']}d_"
        )
    elif result.get("formula_tdee"):
        lines.append(
            "   🧮 Formula only — log 14+ full days with regular weigh-ins "
            "to unlock measured TDEE"
        )

    delta = (result["new_target"] or 0) - (result["old_target"] or 0)
    sign = "+" if delta >= 0 else ""
    lines.append(f"🎯 Daily target: {result['old_target']} → *{result['new_target']}* kcal ({sign}{delta})")
    lines.append("_Exercise you log is credited on top of this target._")

    return "\n".join(lines)
