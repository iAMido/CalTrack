"""Israel-local day bounds (bot/db/queries.py). Pure functions, no network.

    docker compose run --rm --no-deps caltrack python tests/test_queries_timezone.py

Why this file exists: the daily queries filtered timestamptz columns against
naive strings like "2026-10-25T00:00:00". PostgREST resolves those in the
session timezone, which on Supabase is UTC, so the window ran from UTC
midnight — three hours late in IDT. A meal logged at 01:00 local was counted
on the PREVIOUS day. Meanwhile the coach's own rebuild bucketed by local date
correctly, so /summary and the weekly report disagreed about those meals.

The expected values below are not hand-derived: they were read out of Postgres
with `day::timestamp at time zone 'Asia/Jerusalem'`, so this test cross-checks
pytz against the database's own tzdata.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "555",
             "SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "x",
             "USER_TIMEZONE": "Asia/Jerusalem"}.items():
    os.environ[k] = v

from bot.db.queries import _local_day_bounds  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def norm(iso: str) -> str:
    """'2026-10-24T21:00:00+00:00' -> '2026-10-24 21:00:00+00' (Postgres shape)."""
    return iso.replace("T", " ").replace("+00:00", "+00").replace(".999999", "")


# (date, expected start utc, expected end utc, expected length in hours)
# Read from Postgres — see module docstring.
CASES = [
    ("2026-01-15", "2026-01-14 22:00:00+00", "2026-01-15 21:59:59+00", 24),  # IST +02
    ("2026-03-27", "2026-03-26 22:00:00+00", "2026-03-27 20:59:59+00", 23),  # spring forward
    ("2026-07-15", "2026-07-14 21:00:00+00", "2026-07-15 20:59:59+00", 24),  # IDT +03
    ("2026-10-25", "2026-10-24 21:00:00+00", "2026-10-25 21:59:59+00", 25),  # fall back
    ("2026-10-26", "2026-10-25 22:00:00+00", "2026-10-26 21:59:59+00", 24),  # IST again
]


def test_bounds_match_postgres():
    print("bounds match Postgres tzdata")
    for day, want_start, want_end, _ in CASES:
        got_start, got_end = _local_day_bounds(day)
        check(f"{day} start", norm(got_start) == want_start, f"{norm(got_start)} != {want_start}")
        check(f"{day} end", norm(got_end) == want_end, f"{norm(got_end)} != {want_end}")


def test_dst_day_lengths():
    print("DST transition days are not 24 hours")
    for day, _, _, want_hours in CASES:
        start, end = _local_day_bounds(day)
        hours = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
        check(f"{day} is {want_hours}h", round(hours) == want_hours, f"got {hours:.2f}h")


def test_no_lmt_offset():
    """pytz returns Jerusalem's 1880s LMT (+02:21) unless localize() is used.
    A 21-minute drift would be invisible in most data and wrong every day."""
    print("no LMT (+02:21) leakage")
    for day, _, _, _ in CASES:
        start, end = _local_day_bounds(day)
        check(f"{day} offsets are whole hours",
              start.endswith("+00:00") and end.endswith("+00:00")
              and ":21" not in start and ":21" not in end,
              f"{start} / {end}")


def test_the_actual_bug():
    """A meal at 01:00 Israel time belongs to that day, not the one before."""
    print("the 01:00 case that was mis-filed")
    # 2026-10-06 01:00 local (IDT) == 2026-10-05 22:00 UTC.
    meal_utc = datetime.fromisoformat("2026-10-05T22:00:00+00:00")

    s, e = _local_day_bounds("2026-10-06")
    check("lands inside 06/10",
          datetime.fromisoformat(s) <= meal_utc <= datetime.fromisoformat(e))

    s, e = _local_day_bounds("2026-10-05")
    check("does NOT land in 05/10",
          not (datetime.fromisoformat(s) <= meal_utc <= datetime.fromisoformat(e)))

    # The old naive filter would have put it in 05/10 — prove the difference is real.
    old_start = datetime.fromisoformat("2026-10-05T00:00:00+00:00")
    old_end = datetime.fromisoformat("2026-10-05T23:59:59+00:00")
    check("old naive window DID capture it (the bug)",
          old_start <= meal_utc <= old_end)


def test_days_tile_without_gap_or_overlap():
    """Consecutive days must abut exactly, or meals fall through the cracks."""
    print("consecutive days tile cleanly")
    d = datetime(2026, 10, 23)
    for _ in range(6):
        _, end = _local_day_bounds(d.strftime("%Y-%m-%d"))
        nxt_start, _ = _local_day_bounds((d + timedelta(days=1)).strftime("%Y-%m-%d"))
        gap = (datetime.fromisoformat(nxt_start) - datetime.fromisoformat(end)).total_seconds()
        check(f"{d:%Y-%m-%d} -> next day gap is 1us", abs(gap - 0.000001) < 1e-6, f"{gap}s")
        d += timedelta(days=1)


if __name__ == "__main__":
    test_bounds_match_postgres()
    test_dst_day_lengths()
    test_no_lmt_offset()
    test_the_actual_bug()
    test_days_tile_without_gap_or_overlap()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
