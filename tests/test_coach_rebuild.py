"""daily_summary rebuild tests (bot/services/coach.py). No network: the Supabase
client and the upsert are replaced with fakes.

    docker compose run --rm --no-deps caltrack python tests/test_coach_rebuild.py

Why this file exists: the rebuild used to aggregate meals only, so every row it
wrote left calories_burned_exercise at the column default (0). The coach then
read that zero for the weekly total while separately being handed the real run
list, concluded the user had not logged his run, and said so in the report.
31 of 58 days were affected.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "555",
             "SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "x",
             "USER_TIMEZONE": "Asia/Jerusalem"}.items():
    os.environ[k] = v

import pytz  # noqa: E402
from bot.services import coach  # noqa: E402

TZ = pytz.timezone("Asia/Jerusalem")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


# --------------------------------------------------------------------------
# _local_date — the bucketing rule shared by meals and runs
# --------------------------------------------------------------------------
def test_local_date():
    print("_local_date")
    # 21:30 UTC on the 18th is 00:30 local on the 19th (IDT, +03:00).
    # Meals and runs must agree on this or the weekly totals contradict.
    check("post-midnight local rolls to next day",
          coach._local_date("2026-10-18T21:30:00+00:00", TZ) == "2026-10-19",
          coach._local_date("2026-10-18T21:30:00+00:00", TZ))
    # 20:30 UTC is 23:30 local the same day.
    check("pre-midnight local stays",
          coach._local_date("2026-10-18T20:30:00+00:00", TZ) == "2026-10-18")
    check("Z suffix handled",
          coach._local_date("2026-10-19T16:51:25Z", TZ) == "2026-10-19")
    check("space separator handled",
          coach._local_date("2026-10-19 16:51:25+00:00", TZ) == "2026-10-19")
    # A naive timestamp must be read as UTC, not as the container's clock.
    check("naive timestamp treated as UTC",
          coach._local_date("2026-10-18T21:30:00", TZ) == "2026-10-19",
          coach._local_date("2026-10-18T21:30:00", TZ))
    check("None in, None out", coach._local_date(None, TZ) is None)
    check("garbage in, None out", coach._local_date("not-a-date", TZ) is None)


# --------------------------------------------------------------------------
# the rebuild itself
# --------------------------------------------------------------------------
class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _FakeClient:
    def __init__(self, meals, runs):
        self._tables = {"meals": meals, "caltrack_runs": runs}

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


def run_rebuild(meals, runs, start="2026-10-18", end="2026-10-24"):
    """Run the rebuild against fakes; return {date: upserted_row}."""
    written = {}

    async def fake_upsert(table, data, on_conflict=""):
        written[data["date"]] = data
        return data

    orig_client, orig_upsert = coach.db.get_client, coach.db.upsert
    coach.db.get_client = lambda: _FakeClient(meals, runs)
    coach.db.upsert = fake_upsert
    try:
        asyncio.run(coach._rebuild_daily_summaries_for_window("u1", start, end))
    finally:
        coach.db.get_client, coach.db.upsert = orig_client, orig_upsert
    return written


def meal(ts, cal=500, p=30.0):
    return {"eaten_at": ts, "total_calories": cal, "total_protein_g": p,
            "total_carbs_g": 50.0, "total_fat_g": 20.0, "total_fiber_g": 5.0}


def test_rebuild():
    print("_rebuild_daily_summaries_for_window")

    # The real 19/10 case: one run, meals the same day.
    w = run_rebuild(
        meals=[meal("2026-10-19T09:00:00+00:00", 1712, 85.0)],
        runs=[{"run_date": "2026-10-19T16:51:25+00:00", "calories_burned": 527}],
    )
    check("exercise calories written",
          w["2026-10-19"]["calories_burned_exercise"] == 527,
          w["2026-10-19"])
    check("food numbers untouched by the fix",
          w["2026-10-19"]["total_calories_in"] == 1712
          and w["2026-10-19"]["meal_count"] == 1)

    # A run on a day with no logged meals still needs a row, or the deficit for
    # that day is computed against a missing/zero exercise figure.
    w = run_rebuild(
        meals=[],
        runs=[{"run_date": "2026-10-20T06:00:00+00:00", "calories_burned": 400}],
    )
    check("run-only day still creates a row", "2026-10-20" in w, list(w))
    check("run-only day has zeroed food",
          w["2026-10-20"]["total_calories_in"] == 0
          and w["2026-10-20"]["meal_count"] == 0
          and w["2026-10-20"]["calories_burned_exercise"] == 400)

    # Days with no runs must stay 0 — not inherit a neighbour's burn.
    w = run_rebuild(
        meals=[meal("2026-10-21T09:00:00+00:00"), meal("2026-10-22T09:00:00+00:00")],
        runs=[{"run_date": "2026-10-21T06:00:00+00:00", "calories_burned": 300}],
    )
    check("day with run = 300", w["2026-10-21"]["calories_burned_exercise"] == 300)
    check("day without run = 0", w["2026-10-22"]["calories_burned_exercise"] == 0)

    # Two runs in one day sum.
    w = run_rebuild(
        meals=[],
        runs=[{"run_date": "2026-10-21T06:00:00+00:00", "calories_burned": 300},
              {"run_date": "2026-10-21T17:00:00+00:00", "calories_burned": 250}],
    )
    check("two runs in a day sum", w["2026-10-21"]["calories_burned_exercise"] == 550)

    # Midnight boundary: run and meal at the same local instant land together.
    w = run_rebuild(
        meals=[meal("2026-10-18T21:30:00+00:00")],
        runs=[{"run_date": "2026-10-18T21:30:00+00:00", "calories_burned": 111}],
    )
    check("meal and run at same instant share a date",
          list(w) == ["2026-10-19"] and w["2026-10-19"]["calories_burned_exercise"] == 111,
          list(w))

    # Outside the window is ignored.
    w = run_rebuild(
        meals=[meal("2026-10-19T09:00:00+00:00")],
        runs=[{"run_date": "2026-11-05T06:00:00+00:00", "calories_burned": 900}],
    )
    check("run outside window ignored", "2026-11-05" not in w, list(w))

    # Null / missing calories must not crash or poison the total.
    w = run_rebuild(
        meals=[],
        runs=[{"run_date": "2026-10-21T06:00:00+00:00", "calories_burned": None},
              {"run_date": "2026-10-21T07:00:00+00:00", "calories_burned": 120}],
    )
    check("null calories_burned treated as 0",
          w["2026-10-21"]["calories_burned_exercise"] == 120)


# --------------------------------------------------------------------------
# _summarise_week — intake metrics must ignore run-only (zero-food) days
# --------------------------------------------------------------------------
def day(d, cal=0, meals=0, burn=0):
    return {"date": d, "total_calories_in": cal, "meal_count": meals,
            "calories_burned_exercise": burn, "total_protein_g": 0,
            "total_carbs_g": 0, "total_fat_g": 0, "total_fiber_g": 0,
            "weight_kg": None}


def test_summarise_week():
    print("_summarise_week")

    # Regression guard: the real 18-24 Oct week, all 7 days with food.
    # The report said 1,757 avg — this must not move.
    real = [day("2026-10-18", 1048, 1), day("2026-10-19", 1712, 4, 527),
            day("2026-10-20", 1300, 3), day("2026-10-21", 1626, 3),
            day("2026-10-22", 3145, 5), day("2026-10-23", 1485, 5),
            day("2026-10-24", 1983, 4)]
    out = coach._summarise_week("2026-10-18", "2026-10-24", real)
    check("real week average unchanged at 1757",
          out["avg_daily_calories"] == 1757, out["avg_daily_calories"])
    check("real week days_with_data still 7", out["days_with_data"] == 7)
    check("exercise total now 527, was 0",
          out["total_exercise_calories"] == 527, out["total_exercise_calories"])

    # A run-only day must not drag the average down or inflate days tracked.
    with_run_only = real + [day("2026-10-25", 0, 0, 400)]
    out2 = coach._summarise_week("2026-10-18", "2026-10-25", with_run_only)
    check("run-only day does not dilute the average",
          out2["avg_daily_calories"] == 1757, out2["avg_daily_calories"])
    check("run-only day does not inflate days tracked",
          out2["days_with_data"] == 7, out2["days_with_data"])
    check("run-only day still contributes its exercise",
          out2["total_exercise_calories"] == 927, out2["total_exercise_calories"])

    # All-zero week must not divide by zero.
    out3 = coach._summarise_week("2026-11-01", "2026-11-07", [day("2026-11-01", 0, 0, 300)])
    check("no food days -> avg 0, no ZeroDivisionError",
          out3["avg_daily_calories"] == 0 and out3["days_with_data"] == 0)


if __name__ == "__main__":
    test_local_date()
    test_rebuild()
    test_summarise_week()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
