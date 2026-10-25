"""CalTrack without the Telegram app (2026-10-20, Ido: "I am only on WhatsApp").

The WhatsApp listener and the scheduled jobs used to live inside
python-telegram-bot's Application: post_init started WhatsApp, and PTB's
JobQueue ran the nudges and weekly reports. That made a valid Telegram token a
hard requirement even with Telegram switched off. Here they run on their own:
an asyncio loop, APScheduler (the same scheduler PTB's JobQueue wraps) and the
aiohttp WhatsApp server. No Telegram token is used.

Same jobs, same times (PTB counted Sunday as day 0):
  nudges 11:00 / 14:00 / 19:30 daily · calibration Sun 20:00 · coach Sat 22:00
  recipes Thu 09:00
The jobs take an unused `context` argument (from the PTB days); here it is None.

"""

import asyncio
import logging
import signal

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.utils.config import config

logger = logging.getLogger(__name__)

# (name, function path, cron fields) — mirrors bot/main.py post_init.
JOBS = [
    ("nudge_breakfast", "bot.services.nudge:nudge_breakfast", {"hour": 11, "minute": 0}),
    ("nudge_lunch", "bot.services.nudge:nudge_lunch", {"hour": 14, "minute": 0}),
    ("nudge_dinner", "bot.services.nudge:nudge_dinner", {"hour": 19, "minute": 30}),
    ("weekly_calibration", "bot.main:weekly_calibration_job", {"day_of_week": "sun", "hour": 20, "minute": 0}),
    ("weekly_coach", "bot.main:weekly_coach_job", {"day_of_week": "sat", "hour": 22, "minute": 0}),
    # Thursday, not Saturday: the coach report fires Sat 22:00, after the
    # weekend shop. Thursday morning still leaves time to buy ingredients.
    ("weekly_recipes", "bot.services.recipes:weekly_recipes_job", {"day_of_week": "thu", "hour": 9, "minute": 0}),
]


def _resolve(path: str):
    import importlib

    mod, fn = path.split(":")
    return getattr(importlib.import_module(mod), fn)


def build_scheduler() -> AsyncIOScheduler:
    tz = pytz.timezone(config.user_timezone)
    sched = AsyncIOScheduler(timezone=tz)
    for name, path, cron in JOBS:
        fn = _resolve(path)
        sched.add_job(fn, CronTrigger(timezone=tz, **cron), args=[None], id=name, name=name,
                      misfire_grace_time=600, coalesce=True)
    return sched


async def startup_checks() -> None:
    """What post_init did before the jobs: caches and the storage check."""
    from bot.db.supabase_client import storage_health_check
    from bot.services.nutrition import load_usda_cache

    logger.info("Loading USDA nutrition cache...")
    await load_usda_cache()
    ok, msg = await storage_health_check()
    (logger.info if ok else logger.error)(msg if ok else f"STORAGE WARNING: {msg}")


async def run_whatsapp_only() -> None:
    from bot.whatsapp import server as wa_server

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:        # Windows dev box
            pass
    await startup_checks()
    sched = build_scheduler()
    sched.start()
    for job in sched.get_jobs():
        logger.info(f"Scheduled {job.id}: next {job.next_run_time:%a %d/%m %H:%M}")
    runner = None
    try:
        runner = await wa_server.start()
    except Exception as e:
        logger.error(f"WhatsApp listener failed to start: {type(e).__name__}: {e}")
    logger.info("CalTrack running (WhatsApp only).")
    try:
        await stop.wait()
    finally:
        sched.shutdown(wait=False)
        if runner is not None:
            await runner.cleanup()
