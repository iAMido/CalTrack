"""CalTrack entry point (`python -m bot.main`). WhatsApp only since 2026-10-20.

The Telegram bot and python-telegram-bot are gone ("CalTrack without
Telegram", steps 1–3). bot/runner.py runs the scheduler (meal nudges, weekly
calibration and coach report) and the WhatsApp listener that TARS's
wa-gateway posts the "CalTrack" group to.
"""

import asyncio
import logging

from bot.services.calibration import format_calibration_message, recalibrate
from bot.services.coach import run_weekly_coach
from bot.whatsapp import gateway as wa

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

# httpx logs every request URL at INFO; Supabase URLs go through it too.
# WARNING still surfaces real transport failures.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def weekly_calibration_job(context=None) -> None:
    """Sunday 20:00 — recalibrates BMR/TDEE and tells Ido on WhatsApp."""
    try:
        result = await recalibrate(trigger="weekly_auto")
        await wa.notify(format_calibration_message(result))
        logger.info("Weekly calibration completed.")
    except Exception as e:
        logger.error(f"Weekly calibration job failed: {e}")


async def weekly_coach_job(context=None) -> None:
    """Saturday 22:00 — the weekly AI Coach report (Hebrew) on WhatsApp."""
    try:
        from bot.db import queries as db_queries
        profile = await db_queries.get_user_profile()
        if not profile:
            logger.warning("Weekly coach: no user profile found.")
            return
        await wa.notify(await run_weekly_coach(profile["id"]))
        logger.info("Weekly coach report sent.")
    except Exception as e:
        logger.error(f"Weekly coach job failed: {e}")


def main() -> None:
    from bot.runner import run_whatsapp_only

    asyncio.run(run_whatsapp_only())


if __name__ == "__main__":
    main()
