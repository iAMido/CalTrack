# bot/db/ — Database Layer

## What This Is
All Supabase access lives here. Uses `supabase-py` (sync client wrapped in async functions).

## Files
| File | Purpose |
|------|---------|
| `supabase_client.py` | Singleton client + helpers: insert, upsert, select, select_one, update, delete_row, upload_photo |
| `queries.py` | Higher-level queries: get_user_profile, refresh_daily_summary, get_all_usda_foods (paginated) |
| `models.py` | Pydantic models for DB rows |

## Important: upsert API
`upsert(table, data, on_conflict="col")` — passes `on_conflict` as kwarg to `.upsert()`, NOT as a chained `.on_conflict()` method (that method doesn't exist in current supabase-py).

## Supabase Tables
| Table | Purpose |
|-------|---------|
| `user_profile` | Single row — biometrics, goals, Telegram chat ID |
| `usda_foundation` | 8,156 USDA foods with macros per 100g |
| `meals` | One row per eating event |
| `meal_items` | Individual ingredients within a meal |
| `personal_foods` | Per-ingredient aggregate stats (for auto-approve) |
| `personal_food_logs` | Full history of every confirmed weight |
| `ai_corrections` | Every user weight correction (for few-shot prompt improvement) |
| `weight_log` | Daily body weight entries |
| `water_log` | Water intake entries |
| `caltrack_runs` | Exercise sessions (manual or Strava) |
| `daily_summary` | Aggregated daily totals, refreshed after every meal/run/water |
| `calibration_log` | History of BMR/TDEE recalculations |

## Key Notes
- Uses **service_role** key — bypasses RLS, full access to all tables
- `get_all_usda_foods()` paginates in 1,000-row batches to load all 8,156 foods
- `refresh_daily_summary()` recalculates from scratch on every meal save — no incremental updates
- Timestamps: all TIMESTAMPTZ (UTC in DB); converted to `Asia/Jerusalem` in application layer
