# scripts/ — One-Time Setup Scripts

## What This Is
Setup and data-import scripts. Run each once during initial project setup. They are NOT part of the bot's runtime.

## Scripts (run in this order)
| Script | When | What It Does |
|--------|------|-------------|
| `setup_supabase.sql` | First | Creates all 12 database tables + indexes. Run in Supabase SQL editor or via psql. |
| `import_usda.py` | Second | Loads USDA Foundation Foods CSV into the `usda_foundation` table (~2,000 rows). Requires `data/usda_foundation.csv`. |
| `seed_profile.py` | Third | Inserts the user profile row (height, weight, age, goals) into `user_profile`. Also calculates initial BMR/TDEE. |

## Usage
```bash
# 1. Run setup_supabase.sql in Supabase SQL editor (copy-paste the file)

# 2. Download USDA data to data/ then:
python scripts/import_usda.py

# 3. Create your profile:
python scripts/seed_profile.py
```

## Notes
- `setup_supabase.sql` is idempotent — uses `CREATE TABLE IF NOT EXISTS` so it's safe to re-run.
- `seed_profile.py` uses upsert on `telegram_chat_id` so it's also safe to re-run (updates profile).
- `import_usda.py` uses upsert on `fdc_id` — safe to re-run, will update existing rows.
