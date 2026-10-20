# bot/db/ — Database Layer

> **20/10/2026:** CalTrack is WhatsApp-only (no Telegram). See `bot/whatsapp/CLAUDE.md` and `docs/QA-2026-10-20.md` (the full QA record).


## What This Is
All Supabase access lives here. Uses `supabase-py` (sync client wrapped in async functions).

## Files
| File | Purpose |
|------|---------|
| `supabase_client.py` | Singleton client + helpers: insert, upsert, select, select_one, update, delete_row, upload_photo |
| `queries.py` | Higher-level queries: get_user_profile, refresh_daily_summary, get_all_usda_foods (paginated) |
| `models.py` | Pydantic models for DB rows |

## Critical API Note
`upsert(table, data, on_conflict="col")` — passes `on_conflict` as kwarg to `.upsert()`.
Do NOT chain `.on_conflict()` — that method does not exist in supabase-py.

## Supabase Tables
| Table | Purpose |
|-------|---------|
| `user_profile` | Single row — biometrics, goals, `telegram_chat_id` (a legacy column, unused since 2026-10-20) |
| `usda_foundation` | 8,156 USDA foods + custom label-scanned foods (fdc_id ≥ 9,000,000) |
| `meals` | One row per eating event |
| `meal_items` | Individual ingredients within a meal |
| `personal_foods` | Per-ingredient aggregate stats (for auto-approve) |
| `personal_food_logs` | Full weight history per food+meal_type |
| `ai_corrections` | Every user weight correction (few-shot prompt improvement) |
| `weight_log` | Daily body weight entries |
| `water_log` | Water intake entries |
| `caltrack_runs` | Exercise sessions — **a VIEW**, not a table (see root CLAUDE.md). Reads `runcoach.runs` for dates ≥ 2026-06-30; history ≤ 2026-06-29 comes from `_bak_caltrack_runs`. Inserts work via `INSTEAD OF` triggers |
| `_bak_caltrack_runs` | Physical table behind the `caltrack_runs` view; holds the 28 pre-cutover rows plus every new `/run` insert |
| `daily_summary` | Aggregated daily totals, refreshed after every meal/run/water |
| `calibration_log` | History of BMR/TDEE recalculations (`calibration_trigger` column, not `trigger`) |

## Storage
Bucket: `meals` (private, 10MB limit, JPEG/PNG/WebP).
Created via SQL: `INSERT INTO storage.buckets (id, name, public) VALUES ('meals', 'meals', false)`.

## Key Behaviours
- Uses **service_role** key — bypasses RLS
- `get_all_usda_foods()` paginates in 1,000-row batches (Supabase REST default limit)
- `refresh_daily_summary()` recalculates from scratch on every save
- All timestamps: TIMESTAMPTZ (UTC in DB), converted to `Asia/Jerusalem` in app layer

## Testing against the real database (20/10/2026)
There's one production database. QA reads it but must never write:
- `scripts/wa_deep_qa.py` `install_write_guard()` replaces `insert/upsert/update/delete_row/upload_photo` and wraps `get_client()`, so `.table(...).insert/update/upsert/delete` and Storage uploads are **recorded, not executed**; selects pass through.
- `scripts/db_fingerprint.py`: row count + md5 of 14 tables; run before and after, and identical means nothing was written.
- The writes the QA observed per flow are listed in `docs/QA-2026-10-20.md` § 3.
