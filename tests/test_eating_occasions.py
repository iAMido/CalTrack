"""Eating occasions (bot/utils/meals.py). Pure functions, no network.

    docker compose run --rm --no-deps caltrack python tests/test_eating_occasions.py

One meal often arrives as several WhatsApp messages — pizza at 21:00 and the
yogurt at 21:15 — so meal_count counted submissions, not meals, and the weekly
report said "5 ארוחות" for a day that had four. Across the real data, 52 of 151
consecutive same-day pairs are inside 15 minutes.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "555",
             "SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "x",
             "USER_TIMEZONE": "Asia/Jerusalem"}.items():
    os.environ[k] = v

from bot.utils.meals import (  # noqa: E402
    MEAL_GAP_MINUTES, assign_eating_occasions, count_eating_occasions,
)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


BASE = datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc)


def at(*minutes):
    return [(BASE + timedelta(minutes=m)).isoformat() for m in minutes]


def test_the_users_examples():
    print("the two cases that prompted this")
    # "pizza at 9pm and at 9:15 yogurt"
    check("21:00 pizza + 21:15 yogurt = 1 meal",
          count_eating_occasions(at(0, 15)) == 1)
    # "a plate at 14:00, adding additional items at 14:20"
    check("14:00 plate + 14:20 extras = 1 meal",
          count_eating_occasions(at(0, 20)) == 1)


def test_threshold_edges():
    print("threshold")
    check(f"gap of exactly {MEAL_GAP_MINUTES}min joins",
          count_eating_occasions(at(0, MEAL_GAP_MINUTES)) == 1)
    check(f"gap over {MEAL_GAP_MINUTES}min splits",
          count_eating_occasions(at(0, MEAL_GAP_MINUTES + 1)) == 2)
    check("a real second meal 3h later is separate",
          count_eating_occasions(at(0, 180)) == 2)


def test_chains_and_counts():
    print("chains")
    # Each step is inside the gap, so the whole run is one meal even though
    # the first and last are 45 minutes apart.
    check("15+15+15 chain is one meal", count_eating_occasions(at(0, 15, 30, 45)) == 1)
    check("a real day: 3 meals logged in 6 messages",
          count_eating_occasions(at(0, 5, 240, 250, 255, 600)) == 3)
    check("empty day is 0", count_eating_occasions([]) == 0)
    check("single meal is 1", count_eating_occasions(at(0)) == 1)
    check("order does not matter", count_eating_occasions(at(45, 0, 15, 30)) == 1)


def test_input_robustness():
    print("input handling")
    check("Z suffix parses", count_eating_occasions(
        ["2026-10-22T18:00:00Z", "2026-10-22T18:10:00Z"]) == 1)
    check("datetime objects accepted",
          count_eating_occasions([BASE, BASE + timedelta(minutes=10)]) == 1)
    check("naive timestamps read as UTC, not the container clock",
          count_eating_occasions(["2026-10-22T18:00:00", "2026-10-22T18:10:00"]) == 1)
    # A bad row must not silently become an extra meal.
    check("unparseable timestamps ignored, not counted",
          count_eating_occasions(at(0, 10) + ["nonsense", None]) == 1)
    check("all-unparseable is 0", count_eating_occasions(["x", None]) == 0)


def test_assign_tags_rows():
    print("assign_eating_occasions")
    rows = [{"eaten_at": t, "id": i} for i, t in enumerate(at(0, 5, 240, 250))]
    out = assign_eating_occasions(rows)
    check("rows tagged 1,1,2,2", [r["occasion"] for r in out] == [1, 1, 2, 2],
          [r["occasion"] for r in out])
    check("occasion count matches count_eating_occasions()",
          len({r["occasion"] for r in out}) == count_eating_occasions(at(0, 5, 240, 250)))
    check("original rows not mutated", "occasion" not in rows[0])

    shuffled = [{"eaten_at": t, "id": i} for i, t in enumerate(at(250, 0, 240, 5))]
    out = assign_eating_occasions(shuffled)
    check("output sorted by time", [r["occasion"] for r in out] == [1, 1, 2, 2])

    out = assign_eating_occasions([{"eaten_at": "bad"}, {"eaten_at": at(0)[0]}])
    check("unparseable row keeps occasion=None and sorts last",
          out[0]["occasion"] == 1 and out[-1]["occasion"] is None,
          [r["occasion"] for r in out])


def test_matches_production_shape():
    """Last week's 22/10 had 5 rows and should read as 4 meals at 20 minutes."""
    print("against real data shape")
    # 5 rows where two sit 12 minutes apart
    day = at(0, 12, 180, 400, 700)
    check("5 rows -> 4 meals", count_eating_occasions(day) == 4, count_eating_occasions(day))


if __name__ == "__main__":
    test_the_users_examples()
    test_threshold_edges()
    test_chains_and_counts()
    test_input_robustness()
    test_assign_tags_rows()
    test_matches_production_shape()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
