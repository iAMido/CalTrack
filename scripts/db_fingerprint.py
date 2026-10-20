"""Fingerprint of the real CalTrack database: row count + newest row id per
table. Run before and after a QA run; any difference = something was written.

  python scripts/db_fingerprint.py > before.json   ...   python scripts/db_fingerprint.py > after.json
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k, v in {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_CHAT_ID": "1"}.items():
    os.environ.setdefault(k, v)

from bot.db import supabase_client as db  # noqa: E402

TABLES = ["meals", "meal_items", "weight_log", "water_log", "runs", "coach_reports", "calibration_log",
          "personal_foods", "personal_food_logs", "ai_corrections", "meal_templates", "meal_template_items",
          "user_profile", "daily_summary"]
c = db.get_client()
fp = {}
for t in TABLES:
    try:
        r = c.table(t).select("*", count="exact").limit(1).execute()
        rows = c.table(t).select("*").limit(1000).execute().data
        fp[t] = {"count": r.count, "digest": hashlib.md5(json.dumps(sorted(rows, key=lambda x: str(x.get("id"))), sort_keys=True, default=str).encode()).hexdigest()[:12]}
    except Exception as e:  # noqa: BLE001
        fp[t] = {"error": str(e)[:60]}
print(json.dumps(fp, sort_keys=True))
