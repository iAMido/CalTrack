import httpx
import json
import logging
from datetime import datetime, timedelta
import pytz
from bot.utils.config import config
from bot.db import supabase_client as db
from bot.utils.meals import assign_eating_occasions, count_eating_occasions

logger = logging.getLogger(__name__)

COACH_SYSTEM_PROMPT = """You are an experienced clinical dietitian analyzing a client's weekly food and exercise log.
Your goal is to help the client maintain a consistent calorie deficit for healthy weight loss.

IMPORTANT: Perform ALL analysis, reasoning, and calculations in English internally.
Produce ONLY the final output in Hebrew.
Be direct and honest — if the client overate, say so clearly.

=== LENGTH — HARD LIMIT ===
The entire report MUST fit in ONE WhatsApp message: under 3500 characters,
target 400-450 words. A report longer than that does not get read, which makes
it worthless however good the analysis is. If you are running long, cut
explanation and justification — never cut the numbers.

=== NO REPETITION — THE MOST IMPORTANT RULE ===
State each number EXACTLY ONCE, in the section where it belongs, then refer
back to it without restating it. Never re-derive evidence you have already
given. Specifically:
  - Do NOT restate the weekly average in the macro, pattern, adherence or
    recommendation sections. It belongs in section 1 only.
  - Do NOT justify a recommendation by repeating the data that motivated it.
    One short clause of "why" is enough.
  - Do NOT write a closing summary section. The report is short enough to read
    whole; a summary is a third restatement of the same facts.

=== DO NOT INCLUDE ===
  - Recipes. A separate recipe message is sent on Thursday.
  - Full day meal plans with per-item gram breakdowns. Same reason.
  - Any instruction to weigh in, and any escalation about weighing ("this is
    the fourth time I am asking", "this is not a recommendation"). A separate
    reminder handles weigh-ins on Sunday morning, which is when the client can
    act on it. Reporting in section 3 that weight data is missing is fine;
    demanding action on it is not, and repeating a demand that has already
    been ignored does not make it more persuasive.
  - More than ONE mention of any other piece of missing data.

=== SECTIONS — all six, in this order, none added ===

1. 📊 סיכום שבועי
   - Average daily intake vs target
   - Average daily NET (intake − exercise). Exercise calories come from the
     data given to you; trust them.
   - Total deficit/surplus for the week, and whether that is on track
   Max 5 bullets.

2. 💪 מאקרו
   - Protein in g/kg bodyweight vs the 1.6-2.0 g/kg target
   - Carb/fat split, fiber vs 25g/day
   Max 4 bullets. No per-day breakdown.

3. 📈 מגמת משקל
   - Weight change this week, using PREVIOUS_WEEK_SUMMARY. Do NOT invent numbers.
   - If there is no weight data, say so in ONE line and move on.
   Max 3 bullets.

4. 🔍 דפוסים
   - EXACTLY 3 patterns, the 3 most actionable. Not 3 good and 3 bad — 3 total.
   - Draw on timing, weekday/weekend, post-exercise eating, and recurring
     low-nutrient foods (cross-reference TOP_FOODS_LAST_4W).
   - One line each.

5. 🎯 מעקב אחר ההמלצות הקודמות
   - Read PREVIOUS_COACH_REPORT. For each of its 3 action items, ONE line:
     ✅ / ⚠️ / ❌ plus at most 10 words. No evidence, no numbers, no explanation.
   - Skip this section entirely if there is no previous report.

6. ✅ המלצות לשבוע הבא
   - EXACTLY 3 actions, ranked by expected impact on the deficit.
   - Each is at most 2 lines: the action, and its expected calorie impact.
   - Concrete and specific, but no meal plans and no recipes.
   - Do not repeat verbatim what the previous report said — build on it.
   - Do NOT spend one of the 3 actions on weighing in; the Sunday reminder
     covers it. Spend all 3 on food."""


def get_week_boundaries() -> tuple[str, str]:
    """Get current Sun-Sat week boundaries as (sunday_str, saturday_str)."""
    tz = pytz.timezone(config.user_timezone)
    now = datetime.now(tz)
    days_since_sunday = (now.weekday() + 1) % 7
    sunday = now - timedelta(days=days_since_sunday)
    saturday = sunday + timedelta(days=6)
    return sunday.strftime("%Y-%m-%d"), saturday.strftime("%Y-%m-%d")


def _previous_week_boundaries(sunday_str: str) -> tuple[str, str]:
    """Sun-Sat boundaries for the week immediately before the given Sunday."""
    sunday = datetime.strptime(sunday_str, "%Y-%m-%d")
    prev_sat = sunday - timedelta(days=1)
    prev_sun = prev_sat - timedelta(days=6)
    return prev_sun.strftime("%Y-%m-%d"), prev_sat.strftime("%Y-%m-%d")


def _empty_day_bucket() -> dict:
    """Zeroed daily aggregate. `burn` lives here so a run on a day with no meals
    still produces a row — otherwise that day keeps a stale or absent exercise
    figure and the weekly deficit is computed against 0."""
    return {"cal": 0, "p": 0.0, "c": 0.0, "f": 0.0, "fib": 0.0, "times": [], "burn": 0}


def _local_date(value, tz) -> str | None:
    """UTC timestamp from Supabase -> Israel-local YYYY-MM-DD, or None if unparseable.

    Shared by the meal and run loops below so both bucket by exactly the same
    rule. A run at 00:30 local and a meal at 00:30 local must land on the same
    date, or the weekly totals disagree with themselves.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(tz).strftime("%Y-%m-%d")


async def _rebuild_daily_summaries_for_window(
    user_id: str, start_date: str, end_date: str
) -> None:
    """Defensive: recompute daily_summary rows from raw meals for the given
    inclusive date window (Israel-local). Bypasses any drift caused by
    dashboard upserts that may have missed or hit the wrong date."""
    client = db.get_client()
    try:
        # Fetch every confirmed meal whose Israel-local date falls in [start, end]
        # We pull a slightly wider UTC window then group locally.
        start_utc = f"{start_date}T00:00:00+00:00"
        # End-of-day Israel = 23:59 + ~3h offset → next day 02:59 UTC. Pad to next day 23:59 UTC for safety.
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        end_utc = f"{end_dt.strftime('%Y-%m-%d')}T23:59:59+00:00"

        meals_resp = (
            client.table("meals")
            .select("eaten_at,total_calories,total_protein_g,total_carbs_g,total_fat_g,total_fiber_g")
            .eq("user_id", user_id)
            .eq("status", "confirmed")
            .gte("eaten_at", start_utc)
            .lte("eaten_at", end_utc)
            .execute()
        )
        meals = meals_resp.data or []

        # Exercise calories. This query is the whole point of the fix: without
        # it the upsert below writes rows with calories_burned_exercise unset,
        # which lands at the column default (0) and makes the coach believe no
        # exercise happened — even while it is separately handed the run list.
        runs_resp = (
            client.table("caltrack_runs")
            .select("run_date,calories_burned")
            .eq("user_id", user_id)
            .gte("run_date", start_utc)
            .lte("run_date", end_utc)
            .execute()
        )
        runs = runs_resp.data or []

        tz = pytz.timezone(config.user_timezone)
        by_date: dict[str, dict] = {}
        for m in meals:
            d = _local_date(m.get("eaten_at"), tz)
            if d is None or d < start_date or d > end_date:
                continue
            bucket = by_date.setdefault(d, _empty_day_bucket())
            bucket["cal"] += m.get("total_calories") or 0
            bucket["p"]   += float(m.get("total_protein_g") or 0)
            bucket["c"]   += float(m.get("total_carbs_g") or 0)
            bucket["f"]   += float(m.get("total_fat_g") or 0)
            bucket["fib"] += float(m.get("total_fiber_g") or 0)
            bucket["times"].append(m.get("eaten_at"))

        for r in runs:
            d = _local_date(r.get("run_date"), tz)
            if d is None or d < start_date or d > end_date:
                continue
            # setdefault, not a lookup: a run on a day with no logged meals
            # must still create its row.
            by_date.setdefault(d, _empty_day_bucket())["burn"] += (
                r.get("calories_burned") or 0
            )

        # Upsert one row per date. Uses (user_id, date) conflict resolution.
        for d, agg in by_date.items():
            await db.upsert("daily_summary", {
                "user_id": user_id,
                "date": d,
                "total_calories_in": agg["cal"],
                "total_protein_g": round(agg["p"], 1),
                "total_carbs_g": round(agg["c"], 1),
                "total_fat_g": round(agg["f"], 1),
                "total_fiber_g": round(agg["fib"], 1),
                # Eating occasions, not rows — see bot/utils/meals.py.
                "meal_count": count_eating_occasions(agg["times"]),
                "calories_burned_exercise": agg["burn"],
            }, on_conflict="user_id,date")
        logger.info(
            f"Rebuilt daily_summary for {len(by_date)} day(s) "
            f"in window {start_date}..{end_date}"
        )
    except Exception as e:
        # Non-fatal — coach falls back to whatever is already in daily_summary
        logger.warning(f"daily_summary rebuild failed (non-fatal): {e}")


async def _gather_meal_items_bulk(meal_ids: list[str]) -> list[dict]:
    """Single round-trip replacement for the previous N+1 loop."""
    if not meal_ids:
        return []
    client = db.get_client()
    out: list[dict] = []
    # Supabase REST has practical IN-list limits; chunk just in case.
    CHUNK = 100
    for i in range(0, len(meal_ids), CHUNK):
        batch = meal_ids[i:i+CHUNK]
        try:
            resp = (
                client.table("meal_items")
                .select("meal_id,ingredient_name,weight_grams,calories,protein_g,carbs_g,fat_g,fiber_g")
                .in_("meal_id", batch)
                .execute()
            )
            out.extend(resp.data or [])
        except Exception as e:
            logger.warning(f"meal_items bulk fetch failed for chunk: {e}")
    return out


async def _previous_coach_report(user_id: str, before_date: str) -> dict | None:
    """Fetch the most recent coach_reports row strictly before `before_date`."""
    client = db.get_client()
    try:
        resp = (
            client.table("coach_reports")
            .select("week_start,week_end,report_text")
            .eq("user_id", user_id)
            .lt("week_start", before_date)
            .order("week_start", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"Could not fetch previous coach report: {e}")
        return None


async def _top_foods_last_4w(user_id: str, end_date: str) -> list[dict]:
    """Top ingredients by frequency over the 28 days ending at end_date."""
    client = db.get_client()
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=28)
        # Fetch meal IDs in window
        meals_resp = (
            client.table("meals")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "confirmed")
            .gte("eaten_at", f"{start_dt.strftime('%Y-%m-%d')}T00:00:00")
            .lte("eaten_at", f"{end_date}T23:59:59")
            .execute()
        )
        meal_ids = [r["id"] for r in (meals_resp.data or [])]
        if not meal_ids:
            return []
        items = await _gather_meal_items_bulk(meal_ids)
        agg: dict[str, dict] = {}
        for it in items:
            name = (it.get("ingredient_name") or "").strip().lower()
            if not name:
                continue
            bucket = agg.setdefault(name, {"count": 0, "total_cal": 0})
            bucket["count"] += 1
            bucket["total_cal"] += it.get("calories") or 0
        ranked = sorted(agg.items(), key=lambda kv: -kv[1]["count"])[:10]
        return [
            {
                "ingredient": name,
                "times_eaten": d["count"],
                "total_kcal_28d": d["total_cal"],
                "avg_daily_kcal_contribution": round(d["total_cal"] / 28),
            }
            for name, d in ranked
        ]
    except Exception as e:
        logger.warning(f"top_foods_last_4w failed: {e}")
        return []


async def gather_weekly_data(user_id: str, sunday_str: str, saturday_str: str) -> dict:
    """Collect meals, items, runs, weight, and water for a Sun-Sat week,
    plus a previous-week summary block for trend comparison."""
    # Defensive: rebuild summaries for both this week and the previous week
    # so PREVIOUS_WEEK_SUMMARY is accurate too.
    prev_sun, prev_sat = _previous_week_boundaries(sunday_str)
    await _rebuild_daily_summaries_for_window(user_id, prev_sun, saturday_str)

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

    # Bulk fetch meal_items in a single round trip (replaces N+1)
    meal_ids = [m["id"] for m in meals]
    meal_items = await _gather_meal_items_bulk(meal_ids)

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

    # ── Previous-week comparison block ──
    prev_summaries = (
        client.table("daily_summary").select("date,total_calories_in,total_protein_g,total_carbs_g,total_fat_g,total_fiber_g,meal_count,weight_kg,calories_burned_exercise")
        .eq("user_id", user_id)
        .gte("date", prev_sun).lte("date", prev_sat)
        .execute().data or []
    )
    prev_week_summary = _summarise_week(prev_sun, prev_sat, prev_summaries)
    this_week_summary = _summarise_week(sunday_str, saturday_str, summaries)

    # ── Previous coach report (for adherence grading) ──
    prev_report = await _previous_coach_report(user_id, sunday_str)

    # ── Top foods last 4 weeks ──
    top_foods = await _top_foods_last_4w(user_id, saturday_str)

    return {
        # Tagged, not merged: the prompt is given meal_count (occasions) AND
        # these rows. Untagged, 4 vs 5 would be two contradictory facts and the
        # model would invent a reason for the difference.
        "meals": assign_eating_occasions(meals),
        "meal_items": meal_items,
        "runs": runs,
        "weight_log": weights,
        "water_log": water,
        "daily_summaries": summaries,
        "this_week_summary": this_week_summary,
        "previous_week_summary": prev_week_summary,
        "previous_coach_report": prev_report,
        "top_foods_last_4w": top_foods,
        "week": f"{sunday_str} to {saturday_str}",
    }


def _summarise_week(start_date: str, end_date: str, summaries: list[dict]) -> dict:
    """Aggregate stat-block for a week, derived from daily_summary rows."""
    if not summaries:
        return {
            "week_start": start_date,
            "week_end": end_date,
            "days_with_data": 0,
            "total_calories_in": 0,
            "avg_daily_calories": 0,
            "total_protein_g": 0,
            "total_carbs_g": 0,
            "total_fat_g": 0,
            "total_fiber_g": 0,
            "total_meals": 0,
            "total_exercise_calories": 0,
            "weight_start_kg": None,
            "weight_end_kg": None,
            "weight_delta_kg": None,
        }
    cal = sum(s.get("total_calories_in") or 0 for s in summaries)
    pro = sum(float(s.get("total_protein_g") or 0) for s in summaries)
    car = sum(float(s.get("total_carbs_g") or 0) for s in summaries)
    fat = sum(float(s.get("total_fat_g") or 0) for s in summaries)
    fib = sum(float(s.get("total_fiber_g") or 0) for s in summaries)
    n = sum(s.get("meal_count") or 0 for s in summaries)
    ex = sum(s.get("calories_burned_exercise") or 0 for s in summaries)
    sorted_s = sorted(summaries, key=lambda s: s.get("date") or "")
    w_start = next((s.get("weight_kg") for s in sorted_s if s.get("weight_kg")), None)
    w_end = next((s.get("weight_kg") for s in reversed(sorted_s) if s.get("weight_kg")), None)
    delta = round(w_end - w_start, 2) if (w_start and w_end) else None
    # Count days the user actually logged FOOD, not rows present. The rebuild
    # now also creates rows for days with a run but no meals, so len(summaries)
    # would both overstate "days tracked" and dilute the intake average with
    # zero-calorie days — corrupting the week-over-week comparison.
    food_days = sum(1 for s in summaries if (s.get("meal_count") or 0) > 0)
    return {
        "week_start": start_date,
        "week_end": end_date,
        "days_with_data": food_days,
        "total_calories_in": cal,
        "avg_daily_calories": round(cal / food_days) if food_days else 0,
        "total_protein_g": round(pro, 1),
        "total_carbs_g": round(car, 1),
        "total_fat_g": round(fat, 1),
        "total_fiber_g": round(fib, 1),
        "total_meals": n,
        "total_exercise_calories": ex,
        "weight_start_kg": w_start,
        "weight_end_kg": w_end,
        "weight_delta_kg": delta,
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

    prev_report_block = "NONE — this is the first weekly report for this client."
    if weekly_data.get("previous_coach_report"):
        pr = weekly_data["previous_coach_report"]
        prev_report_block = (
            f"Previous report covered {pr.get('week_start')} to {pr.get('week_end')}:\n"
            f"{pr.get('report_text', '')}"
        )

    # #12 — Token budget guard.
    # On heavy weeks (40+ meals × 4 items) the raw JSON dump approaches the
    # model's input limit and inflates cost. Compress to one line per meal
    # whenever item count exceeds the soft cap; keep raw items otherwise.
    MEAL_ITEMS_SOFT_CAP = 150
    if len(weekly_data["meal_items"]) > MEAL_ITEMS_SOFT_CAP:
        meal_items_block = _compress_meal_items(weekly_data["meal_items"])
    else:
        meal_items_block = (
            "MEAL ITEMS (individual foods):\n"
            + json.dumps(weekly_data["meal_items"], indent=2, default=str)
        )

    user_prompt = f"""
WEEK: {weekly_data['week']}

CLIENT PROFILE:
{json.dumps(profile_summary, indent=2, default=str)}

THIS_WEEK_SUMMARY (authoritative — derived from raw meals just now):
{json.dumps(weekly_data['this_week_summary'], indent=2, default=str)}

PREVIOUS_WEEK_SUMMARY (use for trend comparison):
{json.dumps(weekly_data['previous_week_summary'], indent=2, default=str)}

PREVIOUS_COACH_REPORT (use for adherence grading):
{prev_report_block}

TOP_FOODS_LAST_4W (use for pattern detection + recipe matching):
{json.dumps(weekly_data['top_foods_last_4w'], indent=2, default=str)}

DAILY SUMMARIES (this week, per day):
{json.dumps(weekly_data['daily_summaries'], indent=2, default=str)}

MEALS ({len(weekly_data['meals'])} rows, grouped into eating occasions by the
"occasion" field — rows sharing an occasion are ONE meal logged in several
messages, e.g. a plate at 14:00 and what was added at 14:20. meal_count in the
summaries counts occasions, not rows, so it will be lower than this number.
Treat one occasion as one meal; never describe the extra rows as separate
meals or as the client eating more often than he does):
{json.dumps(weekly_data['meals'], indent=2, default=str)}

{meal_items_block}

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
                    # 2026-10-20 deep QA: every saved report since September was
                    # ~4,950 chars and ended mid-sentence ("חטיף (10") — Hebrew
                    # used up 3,500 tokens before the end. Room for the whole report.
                    "max_tokens": 9000,
                },
            )
            response.raise_for_status()
    except Exception as e:
        logger.error(f"AI Coach API error: {e}")
        return "❌ שגיאה ביצירת הדוח השבועי. נסה שוב מאוחר יותר."

    choice = response.json()["choices"][0]
    report_text = choice["message"]["content"]
    if choice.get("finish_reason") == "length":
        logger.warning("AI Coach report was cut by max_tokens (%d chars) — raise the limit", len(report_text or ""))

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


def _compress_meal_items(items: list[dict]) -> str:
    """One-line-per-meal compressed block for very heavy weeks.

    Trades per-item visibility for token budget: groups by meal_id, joins
    ingredient names + grams + calories into a single string per meal.
    Activated only when item count exceeds the soft cap (~150 items).
    """
    by_meal: dict[str, list[dict]] = {}
    for it in items:
        by_meal.setdefault(it.get("meal_id") or "_", []).append(it)
    lines = [
        "MEAL ITEMS (compressed — heavy week, one line per meal):",
    ]
    for meal_id, its in by_meal.items():
        parts = []
        for it in its:
            name = (it.get("ingredient_name") or "?")[:30]
            grams = it.get("weight_grams") or 0
            cal = it.get("calories") or 0
            parts.append(f"{name} {grams}g/{cal}kcal")
        lines.append(f"  {meal_id[:8]}: " + ", ".join(parts))
    return "\n".join(lines)


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
