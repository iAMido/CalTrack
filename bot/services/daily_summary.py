import logging
from datetime import datetime
import pytz
from bot.db import queries as db_queries
from bot.utils.config import config
from bot.utils.formatters import format_daily_summary

logger = logging.getLogger(__name__)


def _today_str() -> str:
    tz = pytz.timezone(config.user_timezone)
    return datetime.now(tz).strftime("%Y-%m-%d")


def _today_display() -> str:
    tz = pytz.timezone(config.user_timezone)
    return datetime.now(tz).strftime("%A, %B %d, %Y")


async def get_today_summary_text() -> str:
    profile = await db_queries.get_user_profile()
    if not profile:
        return "⚠️ No user profile found. Run `python scripts/seed_profile.py` first."

    today = _today_str()
    daily = await db_queries.refresh_daily_summary(today, profile["id"])
    meals = await db_queries.get_today_meals()

    return format_daily_summary(_today_display(), daily, meals)


async def get_status_text() -> str:
    profile = await db_queries.get_user_profile()
    if not profile:
        return "⚠️ No user profile found."

    today = _today_str()
    daily = await db_queries.refresh_daily_summary(today, profile["id"])

    cal_in = daily.get("total_calories_in", 0)
    target = daily.get("target_calories") or profile.get("target_daily_calories", 2000)
    burned = daily.get("calories_burned_exercise", 0)
    net = cal_in - burned
    remaining = target - net

    symbol = "✅" if remaining > 0 else "🔴"
    return (
        f"{symbol} *Today's status*\n"
        f"In: {cal_in:,} kcal | Out: {burned:,} kcal\n"
        f"Net: {net:,} / {target:,} kcal\n"
        f"Remaining: *{remaining:,} kcal*"
    )
