"""Thursday recipe message — the reference half of the weekly coaching.

Split out of the Saturday coach report on 2026-10-25. Two reasons:

  1. Lifecycle. The report is read once; recipes and a day plan are consulted
     while shopping and cooking. Appended to a 2,400-word report they were
     never seen.
  2. Timing. The coach report fires Saturday 22:00 — after the weekend shop.
     Thursday morning reaches the user while the ingredients can still be
     bought.

Deliberately NOT personalised on the current week's deficit: that is the
report's job. This message answers "what do I cook", using the client's own
most-logged foods so the suggestions are things he actually eats.
"""

import json
import logging

import httpx

from bot.db import queries as db_queries
from bot.services.coach import _top_foods_last_4w, get_week_boundaries
from bot.utils.config import config

logger = logging.getLogger(__name__)

RECIPES_SYSTEM_PROMPT = """You are a clinical dietitian writing the weekly cooking message
for a client who is in a calorie deficit and under-eating protein.

Perform all reasoning in English. Produce the output ONLY in Hebrew.

=== LENGTH — HARD LIMIT ===
Under 3000 characters total. This must fit in ONE WhatsApp message.

=== WHAT TO PRODUCE — exactly these two parts, nothing else ===

1. 🍽 שתי מתכונים
   Exactly 2 recipes, each:
     - built from the client's TOP_FOODS (things he already eats and buys)
     - high protein, moderate calories, under 30 minutes
     - ingredients with quantities, then numbered steps, kept terse
     - calories + protein per serving
   No more than 8 ingredients and 5 steps each.

2. 📋 יום לדוגמה
   ONE example day hitting the client's calorie and protein targets:
     - 5 eating occasions (breakfast, snack, lunch, snack, dinner)
     - one line each: what, quantity, calories, protein
     - a total line
   This is a template to copy, not a prescription — say so in one short line.

=== DO NOT INCLUDE ===
  - Any analysis of the past week, any deficit/weight commentary, any grading
    of previous behaviour. The Saturday report covers all of that. This message
    is purely "what to cook".
  - Shopping lists, motivational text, or a closing summary.
"""


async def build_recipes_message(user_id: str) -> str:
    """Generate the Thursday recipe + day-plan message. Returns Hebrew text."""
    if not config.openrouter_api_key:
        return "⚠️ OpenRouter API key not configured."

    profile = await db_queries.get_user_profile()
    if not profile:
        return "⚠️ No user profile found."

    # Reuse the coach's own helper so "foods he actually eats" means the same
    # thing in both messages.
    _, saturday = get_week_boundaries()
    top_foods = await _top_foods_last_4w(user_id, saturday)

    target_cal = profile.get("target_daily_calories")
    weight = float(profile.get("current_weight_kg") or 0)
    # 1.6 g/kg is the low end of the muscle-preservation range used by the coach.
    protein_target = round(weight * 1.6) if weight else None

    user_prompt = f"""
CLIENT TARGETS:
  daily calories: {target_cal}
  daily protein: {protein_target} g  (1.6 g/kg at {weight} kg)
  food preferences: {json.dumps(profile.get("food_preferences", {}), ensure_ascii=False)}

TOP_FOODS (most-logged ingredients, last 28 days — build the recipes from these):
{json.dumps(top_foods, indent=2, ensure_ascii=False, default=str)}

Write the Hebrew cooking message.
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
                        {"role": "system", "content": RECIPES_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.4,
                    # Hebrew is token-hungry; the coach report was silently
                    # truncated for weeks at a lower cap. Leave headroom.
                    "max_tokens": 4000,
                },
            )
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Recipes API error: {e}")
        return "❌ שגיאה ביצירת הודעת המתכונים."

    choice = response.json()["choices"][0]
    text = choice["message"]["content"]
    if choice.get("finish_reason") == "length":
        logger.warning("Recipes message cut by max_tokens (%d chars)", len(text or ""))
    return text


async def weekly_recipes_job(context=None) -> None:
    """Thursday 09:00 — recipes + an example day, on WhatsApp."""
    try:
        from bot.whatsapp import gateway as wa

        profile = await db_queries.get_user_profile()
        if not profile:
            logger.warning("Weekly recipes: no user profile found.")
            return
        await wa.notify(await build_recipes_message(profile["id"]))
        logger.info("Weekly recipes message sent.")
    except Exception as e:
        logger.error(f"Weekly recipes job failed: {e}")
