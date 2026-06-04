"""
Telegram nudges for meals the user usually logs but hasn't yet today.

Three jobs registered from bot/main.py::post_init:
  11:00 — nudge if no `breakfast` logged today
  14:00 — nudge if no `lunch`     logged today
  19:30 — nudge if no `dinner`    logged today

Each nudge includes a `/t` shortcut and lists up to 3 of the user's
most-frequently-logged templates so they can one-tap re-log.

Quiet design — only one nudge per meal type per day, only if no log
exists. Never spams. Each job is no-op if the meal is already logged.
"""

import logging
from telegram.ext import ContextTypes
from bot.utils.config import config
from bot.db import queries as db_queries
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)


async def _build_template_hints(user_id: str, limit: int = 3) -> str:
    """Return a short '\\nQuick log: /t Name (N kcal)' block, or empty string."""
    try:
        client = db.get_client()
        resp = (
            client.table("meal_templates")
            .select("name,total_calories")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return ""
        lines = ["", "Quick options:"]
        for t in rows:
            cal = t.get("total_calories") or 0
            lines.append(f"  /t {t['name']} ({cal} kcal)")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"_build_template_hints failed: {e}")
        return ""


async def _send_if_missing(
    context: ContextTypes.DEFAULT_TYPE,
    meal_type: str,
    text: str,
) -> None:
    profile = await db_queries.get_user_profile()
    if not profile:
        return
    today_types = await db_queries.get_today_meal_types(profile["id"])
    if meal_type in today_types:
        logger.info(f"Nudge: {meal_type} already logged today, skipping.")
        return
    hints = await _build_template_hints(profile["id"])
    await context.bot.send_message(
        chat_id=config.telegram_allowed_chat_id,
        text=f"{text}{hints}",
        parse_mode="Markdown",
    )
    logger.info(f"Nudge sent: {meal_type}")


async def nudge_breakfast(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_if_missing(
        context,
        "breakfast",
        "🌅 *Breakfast not logged yet*\nSend a photo or use `/add בוקר ...`",
    )


async def nudge_lunch(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_if_missing(
        context,
        "lunch",
        "🥗 *Lunch not logged yet*\nSend a photo or use `/add צהריים ...`",
    )


async def nudge_dinner(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_if_missing(
        context,
        "dinner",
        "🍽 *Dinner not logged yet*\nSend a photo or use `/add ערב ...`",
    )
