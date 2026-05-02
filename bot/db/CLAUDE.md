# bot/db/ — Database Layer

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
| `user_profile` | Single row — biometrics, goals, Telegram chat ID |
| `usda_foundation` | 8,156 USDA foods + custom label-scanned foods (fdc_id ≥ 9,000,000) |
| `meals` | One row per eating event |
| `meal_items` | Individual ingredients within a meal |
| `personal_foods` | Per-ingredient aggregate stats (for auto-approve) |
| `personal_food_logs` | Full weight history per food+meal_type |
| `ai_corrections` | Every user weight correction (few-shot prompt improvement) |
| `weight_log` | Daily body weight entries |
| `water_log` | Water intake entries |
| `caltrack_runs` | Exercise sessions (manual or future Strava) |
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
