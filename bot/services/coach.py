import httpx
import json
import logging
from datetime import datetime, timedelta
import pytz
from bot.utils.config import config
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

COACH_SYSTEM_PROMPT = """You are an experienced clinical dietitian analyzing a client's weekly food and exercise log.
Your goal is to help the client maintain a consistent calorie deficit for healthy weight loss.

IMPORTANT: Perform ALL analysis, reasoning, and calculations in English internally.
Produce ONLY the final output summary in Hebrew.
Structure it clearly with emoji headers, bullet points, and specific numbers.
Be direct and honest — if the client overate, say so clearly.

YOUR REPORT MUST INCLUDE THESE SECTIONS:

1. 📊 סיכום שבועי (Weekly Summary)
   - Average daily calorie intake vs target
   - Average daily net (intake - exercise)
   - Total deficit/surplus for the week
   - Is the client on track for their weekly weight loss goal?

2. 💪 מאקרו (Macro Balance)
   - Average protein/carbs/fat split (grams and %)
   - Is protein sufficient for muscle preservation? (target: 1.6-2.0g per kg body weight)
   - Fiber intake vs 25g/day target

3. 📈 מגמת משקל (Weight Trend)
   - Weight change this week
   - Compare to last week if data available

4. 🔍 דפוסים (Pattern Detection)
   - Late-night eating patterns
   - Weekend vs weekday differences
   - Post-exercise eating (overcompensation?)
   - Recurring high-calorie, low-nutrient foods

5. ✅ המלצות לשבוע הבא (3 Action Items)
   - Exactly 3 specific, actionable recommendations
   - Ranked by expected impact on deficit
   - Include specific calorie numbers

6. 🍽 מתכונים מומלצים (2 Recipe Suggestions)
   - Match the client's food preferences
   - High protein, moderate calorie
   - Simple to prepare (< 30 min)
   - Include estimated calories and macros per serving"""


def get_week_boundaries() -> tuple[str, str]:
    """Get current Sun-Sat week boundaries as (sunday_str, saturday_str)."""
    tz = pytz.timezone(config.user_timezone)
    now = datetime.now(tz)
    days_since_sunday = (now.weekday() + 1) % 7
    sunday = now - timedelta(days=days_since_sunday)
    saturday = sunday + timedelta(days=6)
    return sunday.strftime("%Y-%m-%d"), saturday.strftime("%Y-%m-%d")


async def gather_weekly_data(user_id: str, sunday_str: str, saturday_str: str) -> dict:
    """Collect meals, items, runs, weight, and water for a Sun-Sat week."""
    start_ts = f"{sunday_str}T00:00:00"
    end_ts = f"{saturday_str}T23:59:59"
    client = db.get_client()

    meals = (
        client.table("meals").select("*")
        .eq("user_id", user_id).eq("status", "confirmed")
        .gte("eaten_at", start_ts).lte("eaten_at", end_ts)
        .order("eaten_at", desc=False)
        .execute().data or []
    )

    meal_ids = [m["id"] for m in meals]
    meal_items = []
    for mid in meal_ids:
        items = (
            client.table("meal_items").select("ingredient_name,weight_grams,calories,protein_g,carbs_g,fat_g,fiber_g")
            .eq("meal_id", mid)
            .execute().data or []
        )
        meal_items.extend([{**item, "meal_id": mid} for item in items])

    runs = (
        client.table("caltrack_runs").select("distance_km,duration_minutes,calories_burned,avg_pace_sec_per_km,run_date")
        .eq("user_id", user_id)
        .gte("run_date", start_ts).lte("run_date", end_ts)
        .execute().data or []
    )

    weights = (
        client.table("weight_log").select("weight_kg,measured_at")
        .eq("user_id", user_id)
        .gte("measured_at", start_ts).lte("measured_at", end_ts)
        .order("measured_at", desc=False)
        .execute().data or []
    )

    water = (
        client.table("water_log").select("amount_ml,logged_at")
        .eq("user_id", user_id)
        .gte("logged_at", start_ts).lte("logged_at", end_ts)
        .execute().data or []
    )

    summaries = (
        client.table("daily_summary").select("*")
        .eq("user_id", user_id)
        .gte("date", sunday_str).lte("date", saturday_str)
        .execute().data or []
    )

    return {
        "meals": meals,
        "meal_items": meal_items,
        "runs": runs,
        "weight_log": weights,
        "water_log": water,
        "daily_summaries": summaries,
        "week": f"{sunday_str} to {saturday_str}",
    }


async def run_weekly_coach(user_id: str) -> str:
    """Run the AI Coach analysis for the current Sun-Sat week. Returns Hebrew report."""
    if not config.openrouter_api_key:
        return "⚠️ OpenRouter API key not configured."

    from bot.db import queries as db_queries
    profile = await db_queries.get_user_profile()
    if not profile:
        return "⚠️ No user profile found."

    sunday, saturday = get_week_boundaries()
    weekly_data = await gather_weekly_data(user_id, sunday, saturday)

    if not weekly_data["meals"] and not weekly_data["runs"]:
        return f"📊 אין מספיק נתונים לשבוע {sunday} עד {saturday}.\nהתחל לתעד ארוחות כדי לקבל דוח שבועי."

    profile_summary = {
        "weight_kg": float(profile.get("current_weight_kg", 0)),
        "height_cm": profile.get("height_cm"),
        "age": profile.get("age"),
        "sex": profile.get("sex"),
        "target_weight_kg": float(profile.get("target_weight_kg", 0)),
        "target_daily_calories": profile.get("target_daily_calories"),
        "bmr": profile.get("bmr"),
        "tdee": profile.get("tdee"),
        "activity_factor": float(profile.get("activity_factor", 1.55)),
        "food_preferences": profile.get("food_preferences", {}),
    }

    user_prompt = f"""
WEEK: {weekly_data['week']}

CLIENT PROFILE:
{json.dumps(profile_summary, indent=2, default=str)}

DAILY SUMMARIES:
{json.dumps(weekly_data['daily_summaries'], indent=2, default=str)}

MEALS ({len(weekly_data['meals'])} total):
{json.dumps(weekly_data['meals'], indent=2, default=str)}

MEAL ITEMS (individual foods):
{json.dumps(weekly_data['meal_items'], indent=2, default=str)}

EXERCISE ({len(weekly_data['runs'])} runs):
{json.dumps(weekly_data['runs'], indent=2, default=str)}

WEIGHT LOG:
{json.dumps(weekly_data['weight_log'], indent=2, default=str)}

WATER LOG:
{json.dumps(weekly_data['water_log'], indent=2, default=str)}

Analyze this week and produce your full report in Hebrew.
"""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{config.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://caltrack.app",
                    "X-Title": "CalTrack",
                },
                json={
                    "model": config.openrouter_coach_model,
                    "messages": [
                        {"role": "system", "content": COACH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 3000,
                },
            )
            response.raise_for_status()
    except Exception as e:
        logger.error(f"AI Coach API error: {e}")
        return "❌ שגיאה ביצירת הדוח השבועי. נסה שוב מאוחר יותר."

    report_text = response.json()["choices"][0]["message"]["content"]

    # Persist report to DB for dashboard history
    try:
        client = db.get_client()
        client.table("coach_reports").insert({
            "user_id": user_id,
            "week_start": sunday,
            "week_end": saturday,
            "report_text": report_text,
        }).execute()
        logger.info(f"Coach report saved to DB: {sunday} to {saturday}")
    except Exception as e:
        logger.warning(f"Could not save coach report to DB (non-fatal): {e}")

    return report_text


def split_for_telegram(text: str, max_len: int = 4000) -> list[str]:
    """Split long text into Telegram-safe chunks, breaking at line boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)
    return chunks
