# scripts/

One-time setup and maintenance scripts. Run these locally — they are not part of the production bot.

## Setup Order (first-time)

```bash
# 1. Run SQL schema in Supabase SQL editor (in this order):
#    schema_part1.sql   — core tables (user_profile, meals, meal_items, etc.)
#    schema_part2.sql   — personal food learning tables
#    schema_part3.sql   — daily_summary, calibration_log, runs
#    schema_grants.sql  — RLS policies and grants

# 2. Seed your user profile
python scripts/seed_profile.py

# 3. Download USDA data files to data/ then import:
#    data/foundation_food.json  — USDA Foundation Foods (recommended)
#    data/sr_legacy_food.json   — USDA SR Legacy (optional, adds more items)
python scripts/import_usda.py
```

## Files

| File | Purpose |
|------|---------|
| `seed_profile.py` | Creates the initial `user_profile` row with your biometrics and goals |
| `import_usda.py` | Loads USDA Foundation Foods + SR Legacy into `usda_foundation` table. Paginates in batches of 500 to avoid Supabase limits. |
| `schema_part1.sql` | Core tables: `user_profile`, `meals`, `meal_items`, `usda_foundation` |
| `schema_part2.sql` | Learning tables: `personal_foods`, `personal_food_logs`, `ai_corrections` |
| `schema_part3.sql` | `daily_summary`, `calibration_log`, `weight_log`, `water_log`, `caltrack_runs` |
| `schema_grants.sql` | RLS policies and service_role grants |
| `setup_supabase.sql` | Deprecated — use the schema_part*.sql files instead |

## USDA Data Download

Download from the official USDA FoodData Central:
- Foundation Foods: https://fdc.nal.usda.gov/download-datasets (foundation_food.json)
- SR Legacy: https://fdc.nal.usda.gov/download-datasets (sr_legacy_food.json)

Place files in `data/` (gitignored). The import script auto-detects which files are present.
