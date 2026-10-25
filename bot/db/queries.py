from datetime import datetime, date
import pytz
from bot.db import supabase_client as db
from bot.utils.config import config


def _today_str() -> str:
    tz = pytz.timezone(config.user_timezone)
    return datetime.now(tz).strftime("%Y-%m-%d")


def _local_day_bounds(date_str: str) -> tuple[str, str]:
    """UTC ISO bounds for one Israel-local calendar day: (start, end).

    PostgREST compares a naive timestamp string in the database session's
    timezone, which on Supabase is UTC. So filtering eaten_at between
    "2026-10-25T00:00:00" and "2026-10-25T23:59:59" selected UTC midnight to
    UTC midnight — three hours late in IDT. A meal logged at 01:00 local was
    counted on the PREVIOUS day, and one logged at 01:00 the next morning was
    counted as today. The coach's own rebuild buckets by local date correctly,
    so /summary and the weekly report disagreed for exactly those meals.

    Note tz.localize(), never day.replace(tzinfo=tz): pytz tzinfo objects carry
    the zone's 1880s LMT offset (Jerusalem +02:21) until localize() picks the
    right one for the date.

    DST-safe by construction: start and end are localized independently, so on
    a transition day the window is the real 23 or 25 hours rather than a fixed
    24.
    """
    tz = pytz.timezone(config.user_timezone)
    day = datetime.strptime(date_str, "%Y-%m-%d")
    start = tz.localize(day)
    end = tz.localize(day.replace(hour=23, minute=59, second=59, microsecond=999999))
    return start.astimezone(pytz.utc).isoformat(), end.astimezone(pytz.utc).isoformat()


async def get_user_profile() -> dict | None:
    rows = await db.select("user_profile", limit=1)
    return rows[0] if rows else None


async def get_today_meals(user_id: str | None = None) -> list[dict]:
    today = _today_str()
    _day_start, _day_end = _local_day_bounds(today)
    client = db.get_client()
    query = (
        client.table("meals")
        .select("*")
        .gte("eaten_at", _day_start)
        .lte("eaten_at", _day_end)
        .eq("status", "confirmed")
        .order("eaten_at", desc=False)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.execute()
    return result.data or []


async def get_today_meal_types(user_id: str) -> set[str]:
    """Return the set of meal_types already logged today (for nudge logic)."""
    meals = await get_today_meals(user_id)
    return {m.get("meal_type") for m in meals if m.get("meal_type")}


async def get_meal_items(meal_id: str) -> list[dict]:
    return await db.select("meal_items", {"meal_id": meal_id})


async def get_or_create_daily_summary(date_str: str, user_id: str) -> dict:
    existing = await db.select_one("daily_summary", {"date": date_str, "user_id": user_id})
    if existing:
        return existing
    row = {"date": date_str, "user_id": user_id}
    return await db.upsert("daily_summary", row, on_conflict="user_id,date")


async def refresh_daily_summary(date_str: str, user_id: str) -> dict:
    """Recalculate daily totals from meals and runs tables for `user_id`.

    Every sub-query is filtered by user_id — previously they were not, which
    was harmless on the single-user instance but would leak between users
    the moment a second profile existed.

    `date_str` is an Israel-local calendar date (callers derive it from
    datetime.now(tz)), so the query windows are built from it rather than
    compared as naive strings — see _local_day_bounds.
    """
    day_start, day_end = _local_day_bounds(date_str)
    client = db.get_client()

    # Sum meals
    meals_result = (
        client.table("meals")
        .select("total_calories,total_protein_g,total_carbs_g,total_fat_g,total_fiber_g,meal_type")
        .eq("user_id", user_id)
        .gte("eaten_at", day_start)
        .lte("eaten_at", day_end)
        .eq("status", "confirmed")
        .execute()
    )
    meals = meals_result.data or []

    cal_in = sum(m.get("total_calories", 0) for m in meals)
    protein = sum(m.get("total_protein_g", 0) for m in meals)
    carbs = sum(m.get("total_carbs_g", 0) for m in meals)
    fat = sum(m.get("total_fat_g", 0) for m in meals)
    fiber = sum(m.get("total_fiber_g", 0) for m in meals)

    # Sum exercise calories
    runs_result = (
        client.table("caltrack_runs")
        .select("calories_burned")
        .eq("user_id", user_id)
        .gte("run_date", day_start)
        .lte("run_date", day_end)
        .execute()
    )
    runs = runs_result.data or []
    burned = sum(r.get("calories_burned", 0) or 0 for r in runs)

    # Get latest weight for this date
    weight_result = (
        client.table("weight_log")
        .select("weight_kg")
        .eq("user_id", user_id)
        .gte("measured_at", day_start)
        .lte("measured_at", day_end)
        .order("measured_at", desc=True)
        .limit(1)
        .execute()
    )
    weight_kg = weight_result.data[0]["weight_kg"] if weight_result.data else None

    # Sum water
    water_result = (
        client.table("water_log")
        .select("amount_ml")
        .eq("user_id", user_id)
        .gte("logged_at", day_start)
        .lte("logged_at", day_end)
        .execute()
    )
    water_ml = sum(w.get("amount_ml", 0) for w in (water_result.data or []))

    # Get user targets
    profile = await get_user_profile()
    target = profile.get("target_daily_calories") if profile else None
    bmr = profile.get("bmr") if profile else None
    tdee = profile.get("tdee") if profile else None

    summary = {
        "date": date_str,
        "user_id": user_id,
        "total_calories_in": cal_in,
        "total_protein_g": round(protein, 2),
        "total_carbs_g": round(carbs, 2),
        "total_fat_g": round(fat, 2),
        "total_fiber_g": round(fiber, 2),
        "meal_count": len(meals),
        "calories_burned_exercise": burned,
        "bmr_calories": bmr,
        "tdee_calories": tdee,
        "target_calories": target,
        "weight_kg": weight_kg,
        "water_ml": water_ml,
    }

    return await db.upsert("daily_summary", summary, on_conflict="user_id,date")


async def get_last_n_meals(n: int = 5, user_id: str | None = None) -> list[dict]:
    client = db.get_client()
    query = (
        client.table("meals")
        .select("*")
        .eq("status", "confirmed")
        .order("eaten_at", desc=True)
        .limit(n)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.execute()
    return result.data or []


async def get_usda_food(fdc_id: int) -> dict | None:
    return await db.select_one("usda_foundation", {"fdc_id": fdc_id})


async def get_all_usda_foods() -> list[dict]:
    """Load all USDA foods, paginating past the 1,000-row API limit."""
    client = db.get_client()
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        result = (
            client.table("usda_foundation")
            .select("fdc_id,description,food_category,calories_per_100g,protein_per_100g,carbs_per_100g,fat_per_100g,fiber_per_100g")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = result.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows
