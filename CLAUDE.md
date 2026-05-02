# CalTrack — Main Project

## What This Is
A single-user, privacy-first calorie tracking system. Photograph meals via Telegram, AI identifies the food, confirm weights, and the system tracks calories + macros automatically. Weekly AI coaching reports in Hebrew.

## Architecture Overview
- **Input**: Telegram Bot (`bot/`) — photo → OpenRouter Vision AI → inline keyboard confirmation
- **Database**: Supabase (PostgreSQL + Storage) — service_role key, all tables in public schema
- **Nutrition Data**: USDA SR Legacy + Foundation Foods (8,156 foods in `usda_foundation` table)
- **Exercise**: Manual `/run` command (Strava planned for Stage 2)
- **Analytics**: Streamlit dashboard (`dashboard/`) — Stage 3
- **AI Coach**: Weekly report via OpenRouter, output in Hebrew — Stage 3

## Directory Map
```
caltrack/
├── bot/            # Telegram bot — core application
│   ├── handlers/   # photo.py, commands.py, callbacks.py, admin.py
│   ├── services/   # vision.py, nutrition.py, personal_foods.py, calibration.py, daily_summary.py
│   ├── db/         # supabase_client.py, queries.py, models.py
│   └── utils/      # config.py, formatters.py, met_calculator.py
├── dashboard/      # Streamlit analytics dashboard (Stage 3, not yet built)
├── data/           # USDA JSON files (gitignored)
└── scripts/        # One-time setup scripts
```

## Key Files
- `bot/main.py` — entry point: `python -m bot.main`
- `bot/utils/config.py` — all config loaded from `.env` via pydantic-settings
- `bot/db/supabase_client.py` — Supabase REST helpers (insert/upsert/select/update)
- `bot/db/queries.py` — higher-level queries; paginates USDA load (8k+ rows)
- `bot/services/vision.py` — OpenRouter vision AI; AI returns food name + calories; we match USDA locally
- `bot/services/nutrition.py` — in-memory USDA cache + fuzzy name matcher + AI fallback calories
- `scripts/import_usda.py` — imports Foundation Foods + SR Legacy + FNDDS (any available)
- `.env` — local secrets (gitignored)

## Development Stages
| Stage | Features | Status |
|-------|----------|--------|
| 1 — MVP | Photo logging, inline confirmation, daily summary, /run /weight /water /undo | ✅ Complete |
| 2 — Learning | Personal food history, auto-approve, Strava sync, /label, /add | 🔨 Partial (personal_foods DB done, Strava/label/add pending) |
| 3 — AI Coach | Weekly Hebrew report, Streamlit dashboard, BMR calibration | 📋 Planned |
| 4 — Extras | Barcode scan, Garmin, reminders, Next.js dashboard | 📋 Future |

## First-Time Setup
```bash
pip install -r requirements.txt
# 1. Run schema in Supabase SQL editor (in order):
#    scripts/schema_part1.sql, schema_part2.sql, schema_part3.sql, schema_grants.sql
# 2. Seed profile:
python scripts/seed_profile.py
# 3. Download USDA datasets to data/ and import:
#    data/foundation_food.json  (Foundation Foods)
#    data/sr_legacy_food.json   (SR Legacy — recommended)
python scripts/import_usda.py
# 4. Create 'meals' bucket in Supabase Storage (private)
# 5. Start the bot:
python -m bot.main
```

## Environment Variables (.env)
| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_ID` | Your Telegram user ID (single-user auth) |
| `OPENROUTER_API_KEY` | OpenRouter key for Vision AI + Coach |
| `OPENROUTER_VISION_MODEL` | e.g. `openai/gpt-4o` |
| `OPENROUTER_COACH_MODEL` | e.g. `anthropic/claude-sonnet-4-5` |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_KEY` | service_role key (bypasses RLS) |
| `USER_TIMEZONE` | e.g. `Asia/Jerusalem` |

## Security
- Telegram: all updates checked against `TELEGRAM_ALLOWED_CHAT_ID`
- Supabase: service_role key kept in `.env` (gitignored), never committed
- Photos stored in private Supabase Storage bucket
