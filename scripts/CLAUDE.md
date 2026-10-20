# scripts/ — One-Time Setup Scripts

## What This Is
Setup and data-import scripts. Run each once during initial project setup. Not part of the bot runtime.

## Scripts
| Script | Run Order | What It Does | Status |
|--------|-----------|-------------|--------|
| `schema_part1.sql` | 1st | Creates: user_profile, usda_foundation, meals, meal_items | Done |
| `schema_part2.sql` | 2nd | Creates: personal_foods, personal_food_logs, ai_corrections, weight_log, water_log | Done |
| `schema_part3.sql` | 3rd | Creates: caltrack_runs, daily_summary, calibration_log | Done |
| `schema_grants.sql` | 4th | Grants SELECT/INSERT/UPDATE/DELETE to all Supabase roles | Done |
| `seed_profile.py` | 5th | Inserts user profile (183cm, 90kg, 44yo male, target 81kg) | Done |
| `import_usda.py` | 6th | Loads USDA datasets into usda_foundation table | Done (8,156 foods) |

## Usage
```bash
# SQL scripts: paste into Supabase SQL editor, run in order above

python scripts/seed_profile.py   # creates/updates user profile
python scripts/import_usda.py    # imports all data/*.json files found
```

## import_usda.py Details
- Auto-detects: `data/foundation_food.json`, `data/sr_legacy_food.json`, `data/fndds_food.json`
- Deduplicates by fdc_id (Foundation Foods takes priority)
- Safe to re-run (upsert on fdc_id)
- Handles SR Legacy JSON format (`SRLegacyFoods` key) and FNDDS (`SurveyFoods` key)

## Notes
- All scripts are Windows-safe (no emoji in print statements — use ASCII)
- `schema_grants.sql` must be run after every new table is created

## QA scripts (2026-10-20), run in the CalTrack image on the VPS
| Script | What it does |
|---|---|
| `wa_smoke.py [baseline.json]` | 7 WhatsApp steps through a fake gateway (help, summary, status, history, typed meal → ❌, voice). With a baseline: exits 1 on a different shape. Never writes. |
| `wa_deep_qa.py [--json out.json]` | ~53 steps: every command and flow, photo with a real image, all scheduled jobs. **Every DB write is intercepted and listed, never executed.** `--json` saves a transcript for an A/B diff. |
| `db_fingerprint.py` | Row count + md5 of 14 tables. Run before and after any QA; identical = nothing was written. |

How to run, and what they found: `docs/QA-2026-10-20.md`. Not one-time setup scripts. Unlike the others above, these are run after every change.
