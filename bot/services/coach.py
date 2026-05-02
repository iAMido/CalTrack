"""
AI Coach weekly analysis — Stage 3.
Gathers 7 days of data, calls OpenRouter, returns Hebrew report.
"""
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
Produce ONLY the final output summary in Hebrew. Use clear headers, bullet points, and numbers.
Be direct and honest — if the client overate, say so clearly with specific numbers."""


async def gather_weekly_data(user_id: str, end_date: str | None = None) -> dict:
    """Collect 7 days of meals, runs, and weight data."""
    tz = pytz.timezone(config.user_timezone)
    if end_date:
        end = datetime.fromisoformat(end_date).replace(tzinfo=tz)
    else:
        end = datetime.now(tz)

    start = end - timedelta(days=7)
    start_str = start.strftime("%Y-%m-%dT00:00:00")
    end_str = end.strftime("%Y-%m-%dT23:59:59")
    client = db.get_client()

    meals = client.table("meals").select("*").eq("user_id", user_id).gte("eaten_at", start_str).lte("eaten_at", end_str).execute().data or []
    runs = client.table("runs").select("*").eq("user_id", user_id).gte("run_date", start_str).lte("run_date", end_str).execute().data or []
    weights = client.table("weight_log").select("*").eq("user_id", user_id).gte("measured_at", start_str).lte("measured_at", end_str).execute().data or []
    summaries = client.table("daily_summary").select("*").eq("user_id", user_id).gte("date", start.strftime("%Y-%m-%d")).lte("date", end.strftime("%Y-%m-%d")).execute().data or []

    return {
        "meals": meals,
        "runs": runs,
        "weight_log": weights,
        "daily_summaries": summaries,
    }


async def run_weekly_coach(user_id: str) -> str:
    """Run the AI Coach analysis. Returns formatted Hebrew report."""
    if not config.openrouter_api_key:
        return "⚠️ OpenRouter API key not configured. Set OPENROUTER_API_KEY in .env"

    from bot.db import queries as db_queries
    profile = await db_queries.get_user_profile()
    weekly_data = await gather_weekly_data(user_id)

    user_prompt = f"""
CLIENT PROFILE:
{json.dumps(profile, indent=2, default=str)}

THIS WEEK'S DAILY SUMMARIES:
{json.dumps(weekly_data['daily_summaries'], indent=2, default=str)}

THIS WEEK'S MEAL DATA:
{json.dumps(weekly_data['meals'], indent=2, default=str)}

THIS WEEK'S EXERCISE DATA:
{json.dumps(weekly_data['runs'], indent=2, default=str)}

WEIGHT MEASUREMENTS:
{json.dumps(weekly_data['weight_log'], indent=2, default=str)}

Please analyze this week's data and produce your report in Hebrew.
Include: deficit status, macro balance, pattern detection, 3 actionable tips, and 2 recipe suggestions.
"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{config.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.openrouter_api_key}",
                "Content-Type": "application/json",
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

    return response.json()["choices"][0]["message"]["content"]
