"""Weigh-in nudge tests (bot/services/nudge.py). No network: the Supabase
client, the profile lookup and the WhatsApp send are replaced with fakes.

    docker compose run --rm --no-deps caltrack python tests/test_nudge_weigh_in.py

The contract that matters is the quiet one: someone who is already weighing
himself must hear nothing. The nudge exists because the weekly report asked
four times and was ignored; a reminder that fires when it is not needed would
be ignored the same way.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "555",
             "SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "x",
             "USER_TIMEZONE": "Asia/Jerusalem"}.items():
    os.environ[k] = v

from bot.services import nudge  # noqa: E402
from bot.db import queries as db_queries  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


class _Q:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _Client:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _Q(self._rows)


def fire(weight_rows, profile={"id": "u1"}):
    """Run the nudge against fakes; return the list of messages sent."""
    sent = []

    async def fake_notify(text):
        sent.append(text)

    async def fake_profile():
        return profile

    orig = (nudge.db.get_client, nudge._notify, db_queries.get_user_profile)
    nudge.db.get_client = lambda: _Client(weight_rows)
    nudge._notify = fake_notify
    db_queries.get_user_profile = fake_profile
    try:
        asyncio.run(nudge.nudge_weigh_in(None))
    finally:
        nudge.db.get_client, nudge._notify, db_queries.get_user_profile = orig
    return sent


def ago(days):
    return [{"measured_at": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}]


def test_quiet_when_not_needed():
    print("quiet design")
    check("weighed today -> silent", fire(ago(0)) == [])
    check("weighed yesterday -> silent", fire(ago(1)) == [])
    check("weighed 2 days ago -> silent", fire(ago(2)) == [])


def test_fires_when_due():
    print("fires when due")
    check("3 days -> one message", len(fire(ago(3))) == 1)
    check("8 days -> one message", len(fire(ago(8))) == 1)
    check("never weighed -> one message", len(fire([])) == 1)
    check("exactly one message, never two", len(fire(ago(30))) == 1)


def test_message_content():
    print("message")
    msg = fire(ago(21))[0]
    check("states how long it has been", "3" in msg and "שבועות" in msg, msg)
    check("says how to log", "/weight" in msg)
    check("gives the conditions", "בבוקר" in msg)
    never = fire([])[0]
    check("never-weighed wording differs", "אין עדיין" in never, never)
    check("no escalation language",
          not any(w in msg for w in ("פעם הרביעית", "דרישה", "חובה")), msg)
    check("single message fits one send", len(msg) < 1000, len(msg))


def test_degrades_safely():
    print("failure handling")
    # No profile -> no crash, no message.
    check("no profile -> silent", fire(ago(99), profile=None) == [])

    # A lookup failure must not silence the nudge: None means "never weighed",
    # which is exactly the client this is for.
    class _Boom:
        def table(self, _n):
            raise RuntimeError("supabase down")

    sent = []

    async def fake_notify(t):
        sent.append(t)

    async def fake_profile():
        return {"id": "u1"}

    orig = (nudge.db.get_client, nudge._notify, db_queries.get_user_profile)
    nudge.db.get_client = lambda: _Boom()
    nudge._notify = fake_notify
    db_queries.get_user_profile = fake_profile
    try:
        asyncio.run(nudge.nudge_weigh_in(None))
    finally:
        nudge.db.get_client, nudge._notify, db_queries.get_user_profile = orig
    check("db error -> still nudges, does not crash", len(sent) == 1, sent)


if __name__ == "__main__":
    test_quiet_when_not_needed()
    test_fires_when_due()
    test_message_content()
    test_degrades_safely()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
