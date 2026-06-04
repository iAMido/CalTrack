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
    meals = await db_queries.get_today_meals(profile["id"])

    return format_daily_summary(_today_display(), daily, meals)


# Macro pacing targets — derived from body weight + standard ratios.
# Protein:  1.6 g per kg body weight (muscle preservation on a cut)
# Fiber:    flat 25 g daily target
def _protein_target_g(profile: dict) -> int:
    weight = float(profile.get("current_weight_kg") or 80)
    return round(weight * 1.6)


def _fiber_target_g() -> int:
    return 25


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

    # Macro pacing — show protein and fiber remaining vs target.
    # Under-protein on a deficit is the actual risk; flag explicitly.
    protein_in = float(daily.get("total_protein_g") or 0)
    fiber_in = float(daily.get("total_fiber_g") or 0)
    protein_target = _protein_target_g(profile)
    fiber_target = _fiber_target_g()
    protein_remaining = max(round(protein_target - protein_in), 0)
    fiber_remaining = max(round(fiber_target - fiber_in), 0)
    protein_pct = round((protein_in / protein_target) * 100) if protein_target else 0
    fiber_pct = round((fiber_in / fiber_target) * 100) if fiber_target else 0

    symbol = "✅" if remaining > 0 else "🔴"
    protein_symbol = "🟢" if protein_pct >= 90 else ("🟡" if protein_pct >= 60 else "🔴")
    fiber_symbol = "🟢" if fiber_pct >= 90 else ("🟡" if fiber_pct >= 60 else "🟠")

    return (
        f"{symbol} *Today's status*\n"
        f"In: {cal_in:,} kcal | Out: {burned:,} kcal\n"
        f"Net: {net:,} / {target:,} kcal\n"
        f"Remaining: *{remaining:,} kcal*\n\n"
        f"{protein_symbol} Protein: {round(protein_in)}g / {protein_target}g "
        f"({protein_pct}%) — *{protein_remaining}g* to go\n"
        f"{fiber_symbol} Fiber: {round(fiber_in)}g / {fiber_target}g "
        f"({fiber_pct}%) — *{fiber_remaining}g* to go"
    )
