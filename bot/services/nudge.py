"""
WhatsApp nudges for meals the user usually logs but hasn't yet today.

Four jobs registered in bot/runner.py:
  11:00 — nudge if no `breakfast` logged today
  14:00 — nudge if no `lunch`     logged today
  19:30 — nudge if no `dinner`    logged today
  Sun 08:00 — nudge if no weigh-in in the last WEIGH_IN_QUIET_DAYS days

Each nudge includes a `/t` shortcut and lists up to 3 of the user's
most-frequently-logged templates so they can one-tap re-log.

Quiet design — only one nudge per meal type per day, only if no log
exists. Never spams. Each job is no-op if the meal is already logged.

The weigh-in nudge exists because the weekly coach report asked for a weigh-in
four weeks running and was ignored four times; by 2026-10-25 the last entry in
weight_log was 20 weeks old. A request that has failed that often is not a
wording problem, it is a channel problem — a report read once on Saturday night
is the wrong place for an action to take tomorrow morning. Asking once, on the
morning it should happen, is the whole point, so the report no longer asks at
all.
"""

import logging
from bot.ui import ContextTypes
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
    await _notify(f"{text}{hints}")
    logger.info(f"Nudge sent: {meal_type}")


async def _notify(text: str) -> None:
    """Single delivery seam for every nudge in this module."""
    from bot.whatsapp import gateway as wa

    await wa.notify(text)


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


# Weighing is only comparable under the same conditions, so the nudge targets
# Sunday morning. 3 days, not 7: someone weighing every few days is already
# doing the thing and should hear nothing.
WEIGH_IN_QUIET_DAYS = 3


async def _days_since_last_weigh_in(user_id: str) -> int | None:
    """Whole days since the most recent weight_log row. None if never weighed
    or the lookup failed — callers treat None as 'nudge', since a client who
    has never weighed in is exactly who this is for."""
    from datetime import datetime, timezone

    try:
        client = db.get_client()
        resp = (
            client.table("weight_log")
            .select("measured_at")
            .eq("user_id", user_id)
            .order("measured_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        raw = str(rows[0]["measured_at"]).replace("Z", "+00:00")
        last = datetime.fromisoformat(raw)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).days
    except Exception as e:  # noqa: BLE001
        logger.warning(f"_days_since_last_weigh_in failed: {e}")
        return None


async def nudge_weigh_in(context: ContextTypes.DEFAULT_TYPE = None) -> None:
    """Sunday morning — ask for a weigh-in, but only if one is actually due."""
    profile = await db_queries.get_user_profile()
    if not profile:
        return

    days = await _days_since_last_weigh_in(profile["id"])
    if days is not None and days < WEIGH_IN_QUIET_DAYS:
        logger.info(f"Weigh-in nudge: last weigh-in {days}d ago, skipping.")
        return

    if days is None:
        since = "אין עדיין שקילה מתועדת"
    elif days >= 14:
        since = f"השקילה האחרונה לפני {days // 7} שבועות"
    else:
        since = f"השקילה האחרונה לפני {days} ימים"

    lines = [
        "⚖️ *שקילה*",
        f"{since}.",
        "הכי מדויק: בבוקר, אחרי שירותים, לפני ארוחת בוקר.",
        "לתיעוד: `/weight 91.5`",
    ]
    await _notify("\n".join(lines))
    logger.info(f"Weigh-in nudge sent (days since last: {days}).")
