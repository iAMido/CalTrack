# CalTrack — Main Project

## What This Is
A single-user, privacy-first calorie tracking system. You photograph meals via Telegram, AI identifies the food, you confirm weights, and the system tracks calories + macros automatically. Weekly AI coaching reports in Hebrew.

## Architecture Overview
- **Input**: Telegram Bot (`bot/`) — photo → AI vision → inline keyboard confirmation
- **Database**: Supabase (PostgreSQL + Storage) — all data behind RLS
- **Nutrition Data**: USDA Foundation Foods (local table, ~2,000 base foods)
- **Exercise**: Strava API auto-import + manual `/run` command
- **Analytics**: Streamlit dashboard (`dashboard/`)
- **AI Coach**: Weekly report via OpenRouter (Claude/GPT-4o), output in Hebrew

## Directory Map
```
caltrack/
├── bot/            # Telegram bot — core application
│   ├── handlers/   # Telegram update handlers (photo, commands, callbacks)
│   ├── services/   # Business logic (vision AI, nutrition, learning, strava)
│   ├── db/         # Database access (Supabase client, models, queries)
│   └── utils/      # Shared utilities (config, formatters, MET calculator)
├── dashboard/      # Streamlit analytics dashboard (Stage 3)
│   ├── pages/      # Individual dashboard pages
│   └── components/ # Reusable chart/filter components
├── data/           # Local data files (USDA CSV downloaded here)
└── scripts/        # One-time setup scripts (schema, seed, USDA import)
```

## Key Files
- `bot/main.py` — entry point, start the bot with `python -m bot.main`
- `bot/utils/config.py` — all configuration loaded from `.env`
- `scripts/setup_supabase.sql` — run once to create all DB tables
- `scripts/seed_profile.py` — run once to insert the user profile
- `scripts/import_usda.py` — run once to load USDA nutrition data
- `.env` — local secrets (gitignored, never commit)
- `.env.example` — template for `.env`

## First-Time Setup
```bash
pip install -r requirements.txt
# 1. Run schema in Supabase SQL editor: scripts/setup_supabase.sql
# 2. Seed your profile:
python scripts/seed_profile.py
# 3. Download USDA data and import:
python scripts/import_usda.py
# 4. Start the bot:
python -m bot.main
```

## Development Stages
| Stage | Features | Status |
|-------|----------|--------|
| 1 — MVP | Photo logging, inline confirmation, daily summary | 🔨 In progress |
| 2 — Learning | Personal food history, auto-approve, Strava sync | 📋 Planned |
| 3 — AI Coach | Weekly analysis in Hebrew, Streamlit dashboard, BMR calibration | 📋 Planned |
| 4 — Extras | Barcode scan, Garmin, reminders, Next.js dashboard | 📋 Future |

## Environment Variables
All secrets in `.env` (gitignored). See `.env.example` for the full list.

## Security
- Telegram: all updates checked against `TELEGRAM_ALLOWED_CHAT_ID` — anyone else gets ⛔
- Supabase: RLS enabled, photos in private storage bucket
- No secrets committed to git
