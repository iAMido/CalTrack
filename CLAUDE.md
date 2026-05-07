# CalTrack — Main Project

## What This Is
A single-user, privacy-first calorie tracking system. Photograph meals via Telegram, AI identifies the food, confirm weights, and the system tracks calories + macros automatically. Weekly AI coaching reports in Hebrew.

## Architecture Overview
- **Input**: Telegram Bot (`bot/`) — photo → OpenRouter Vision AI → inline keyboard confirmation
- **Input**: Freeform `/add` command — Hebrew text → AI breakdown → nutrition calculation
- **Database**: Supabase (PostgreSQL + Storage) — service_role key, all tables in public schema
- **Dashboard**: Next.js web app (lives in `running-coach` repo at `/caltrack`) — meals CRUD, weight, overview
- **Nutrition Data**: USDA SR Legacy + Foundation Foods (8,156 foods in `usda_foundation` table)
- **Nutrition (freeform)**: AI-provided values (OpenRouter gpt-4o-mini) — used directly, not USDA matched
- **Exercise**: Manual `/run` command (Strava planned for Stage 3)
- **AI Coach**: Weekly report via OpenRouter, output in Hebrew — Stage 3
- **Language**: Hebrew input supported everywhere via translation layer (gpt-4o-mini)

## Directory Map
```
caltrack/
├── bot/            # Telegram bot — core application
│   ├── handlers/   # photo.py, commands.py, callbacks.py, admin.py, label.py
│   ├── services/   # vision.py, nutrition.py, personal_foods.py, calibration.py,
│   │               # daily_summary.py, translator.py
│   ├── db/         # supabase_client.py, queries.py, models.py
│   └── utils/      # config.py, formatters.py, met_calculator.py
├── dashboard/      # (unused — dashboard lives in running-coach repo at /caltrack)
├── data/           # USDA JSON files (gitignored)
└── scripts/        # One-time setup scripts
```

## Key Files
- `bot/main.py` — entry point: `python -m bot.main`
- `bot/utils/config.py` — all config loaded from `.env` via pydantic-settings
- `bot/db/supabase_client.py` — Supabase REST helpers (insert/upsert/select/update)
- `bot/db/queries.py` — higher-level queries; paginates USDA load (8k+ rows)
- `bot/services/vision.py` — OpenRouter vision AI (meal photos) + label extraction
- `bot/services/nutrition.py` — 8k USDA in-memory cache + fuzzy matcher + AI fallback
- `bot/services/translator.py` — Hebrew→English translation (fast local map + gpt-4o-mini)
- `bot/handlers/label.py` — `/label` command: scan nutrition label → save custom food
- `scripts/import_usda.py` — imports Foundation Foods + SR Legacy + FNDDS (any available)
- `.env` — local secrets (gitignored)

## Development Stages
| Stage | Features | Status |
|-------|----------|--------|
| 1 — MVP | Photo logging, inline confirmation, daily summary, /run /weight /water /undo | ✅ Complete |
| 2 — Learning | /label, /add (freeform AI), per-item rename, Hebrew input, meal editing, personal food history | ✅ Complete |
| 2.5 — Dashboard | Next.js dashboard (in running-coach): meals CRUD, AI analysis, weight tracking, overview | ✅ Complete |
| 3 — AI Coach | Weekly Hebrew report, BMR calibration, Strava sync | 📋 Planned |
| 4 — Extras | Personal foods library, barcode scan, Garmin, reminders | 📋 Future |

## Dashboard (Next.js — lives in running-coach repo)
The CalTrack web dashboard is at `C:\Users\ido\running-coach\app\caltrack\`. It connects to the same Supabase database as the Telegram bot.

**Dashboard pages:**
- `/caltrack` — Overview: today's calories/macros, weight chart, weekly averages
- `/caltrack/meals` — Meals list with add/edit/delete, AI analysis, date range filter
- `/caltrack/weight` — Weight log
- `/caltrack/foods` — Food database browser

**Dashboard API routes** (`running-coach/app/api/caltrack/`):
- `meals/route.ts` — GET meals list (with ingredient names)
- `meals/add/route.ts` — POST new meal with ingredients
- `meals/edit/route.ts` — PUT edit meal (type, ingredients, recalculate)
- `meals/delete/route.ts` — DELETE meal (cascades: ai_corrections → meal_items → meal)
- `analyze/route.ts` — POST AI food analysis (Hebrew → ingredients + nutrition)
- `overview/route.ts` — GET daily summary + stats

## Key Design Decisions
- **Freeform `/add` uses AI nutrition directly** — not USDA fuzzy matching. USDA matching caused accuracy issues (e.g., "egg" matched "Egg, whole, dried" at 575 cal/100g). AI values from gpt-4o-mini are more accurate for freeform text input.
- **Original Hebrew description saved in `meals.notes`** — displayed as meal title in dashboard instead of ingredient names. E.g., "3 מיני בורקסים" shows as the title.
- **`weight_source` constraint** — `meal_items.weight_source` must be one of: `ai_estimate`, `user_confirmed`, `user_corrected`, `personal_db_auto`, `barcode_lookup`. Dashboard uses `ai_estimate` for new meals, `user_corrected` for edits.

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
# 4. Storage bucket 'meals' already created (private, via SQL)
# 5. Start the bot:
python -m bot.main
```

## Environment Variables (.env)
| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_ID` | Your Telegram user ID (single-user auth) |
| `OPENROUTER_API_KEY` | OpenRouter key for Vision AI + Coach + translation |
| `OPENROUTER_VISION_MODEL` | e.g. `openai/gpt-4o` |
| `OPENROUTER_COACH_MODEL` | e.g. `anthropic/claude-sonnet-4-5` |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_KEY` | service_role key (bypasses RLS) |
| `USER_TIMEZONE` | e.g. `Asia/Jerusalem` |

## Deployment (Railway)
The bot runs 24/7 on Railway. `master` branch is the production branch — every push triggers an automatic redeploy.

**Railway files (safe to commit):**
- `railway.toml` — build config (`startCommand = "python -m bot.main"`)
- `Dockerfile` — Docker container definition (Railway auto-detects Dockerfile over nixpacks)
- `.dockerignore` — must include `!requirements.txt` (has `*.txt` pattern that would exclude it)
- `Procfile` — process type fallback

**Railway files (gitignored):**
- `.railway/` — local Railway CLI auth tokens, never commit

**Secrets in production:** Set all env vars in Railway dashboard → Service → Variables. Never in any committed file.

**Git → Railway workflow:**
```bash
git add <files>
git commit -m "..."
git push origin master   # triggers Railway redeploy (~2 min)
```

**Dependency rule:** `python-telegram-bot==21.3` requires `httpx~=0.27`. Use `supabase>=2.7.0` — older supabase pins httpx<0.26 and causes a build conflict.

**Important:** Only one bot instance can poll Telegram at a time. Running locally while Railway is active causes a 409 Conflict error. Kill local processes before deploying, or stop Railway before running locally.

## Security
- Telegram: all updates checked against `TELEGRAM_ALLOWED_CHAT_ID`
- Supabase: service_role key kept in `.env` (gitignored) and in Railway Variables — never committed
- Photos stored in private Supabase Storage bucket `meals` (no public URLs)
- Railway: no secrets in `railway.toml` — all secrets injected at runtime via Railway Variables
