# bot/db/ — Database Layer

## What This Is
All database access lives here. Uses the `supabase-py` library to talk to the Supabase PostgreSQL instance.

## Files
| File | Purpose |
|------|---------|
| `supabase_client.py` | Singleton Supabase client + low-level helpers (insert, select, update, delete) |
| `models.py` | Pydantic models matching each DB table — used for type safety in and out of DB calls |
| `queries.py` | Higher-level query functions (e.g., `get_today_meals()`, `get_user_profile()`) |

## Database Tables
All tables are defined in `scripts/setup_supabase.sql`. Quick reference:
| Table | Purpose |
|-------|---------|
| `user_profile` | Single row — user biometrics, goals, Telegram chat ID |
| `usda_foundation` | ~2,000 base foods with calories/macros per 100g |
| `meals` | One row per eating event (breakfast/lunch/dinner/snack) |
| `meal_items` | Individual food items within a meal |
| `personal_foods` | Aggregate stats per ingredient across all meals |
| `personal_food_logs` | Full history of every confirmed weight per food+meal_type |
| `ai_corrections` | Every user correction of AI weight estimates |
| `weight_log` | Daily body weight measurements |
| `water_log` | Water intake entries |
| `runs` | Exercise sessions (from Strava or manual) |
| `daily_summary` | Aggregated daily totals (updated after each meal/run/weight) |
| `calibration_log` | History of BMR/TDEE recalculations |

## Supabase Client Note
The project uses the `publishable` key (anon key) with RLS enabled. For backend operations that need to bypass RLS (e.g., seed script), use the `service_role` key — obtainable from Supabase dashboard → Settings → API.
