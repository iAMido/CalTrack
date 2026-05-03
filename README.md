# CalTrack

A single-user, privacy-first calorie tracker. Photograph meals via Telegram → AI identifies the food → confirm weights → calories and macros are logged automatically. Weekly AI coaching reports in Hebrew.

## How It Works

1. Send a meal photo to the Telegram bot
2. The bot uses vision AI (GPT-4o) to identify food items and estimate weights
3. Confirm or correct each item via inline keyboard buttons
4. The system logs nutrition data and shows remaining calories for the day
5. Use `/add`, `/weight`, `/water`, `/run` for manual entries

## Commands

| Command | Action |
|---------|--------|
| 📷 Send photo | Log a meal |
| `/add lunch 150g chicken breast` | Manually add a food item |
| `/weight 87.3` | Log body weight |
| `/water 500` | Log water intake (ml) |
| `/run 5.2 28:30 152` | Log a run (km, time, heart rate) |
| `/summary` or `/s` | Today's full summary |
| `/status` | Remaining calories today |
| `/history 5` | Last N meals |
| `/undo` | Cancel last meal |
| `/label` | Scan a nutrition label → save custom food |
| `/help` | All commands |

Hebrew input is supported everywhere.

---

## Deployment (Railway — Production)

The bot runs 24/7 on [Railway](https://railway.app). Every `git push` to `master` triggers an automatic redeploy.

### Initial Railway Setup

1. Create a new Railway project and link it to this GitHub repo
2. Set all environment variables in the Railway dashboard (Settings → Variables) — see list below
3. Railway uses `railway.toml` + `Dockerfile` automatically — no manual config needed

### Git Workflow

```bash
# Make changes locally
git add <files>
git commit -m "description of change"
git push origin master   # triggers automatic Railway redeploy
```

Railway will build and redeploy within ~2 minutes. Monitor progress in the Railway dashboard under Deployments.

### Environment Variables (Railway Dashboard)

Set these in Railway → Service → Variables. **Never put secrets in any file.**

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_ID` | Your Telegram user ID |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENROUTER_VISION_MODEL` | e.g. `openai/gpt-4o` |
| `OPENROUTER_COACH_MODEL` | e.g. `anthropic/claude-sonnet-4-5` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service_role key |
| `USER_TIMEZONE` | e.g. `Asia/Jerusalem` |

### Railway Files (safe to commit)

| File | Purpose |
|------|---------|
| `railway.toml` | Build and start command config |
| `Dockerfile` | Container definition |
| `Procfile` | Process type definition (fallback) |

---

## Local Development

```bash
# 1. Clone and install dependencies
pip install -r requirements.txt

# 2. Copy .env template and fill in your values
cp .env.example .env

# 3. Run Supabase schema (one-time, in Supabase SQL editor):
#    scripts/schema_part1.sql → schema_part2.sql → schema_part3.sql → schema_grants.sql

# 4. Seed your user profile (one-time):
python scripts/seed_profile.py

# 5. Import USDA nutrition data (one-time):
#    Download data/foundation_food.json and data/sr_legacy_food.json from USDA
python scripts/import_usda.py

# 6. Start the bot
python -m bot.main
```

---

## Project Structure

```
caltrack/
├── bot/            # Telegram bot — core application
│   ├── handlers/   # photo.py, commands.py, callbacks.py, admin.py, label.py
│   ├── services/   # vision.py, nutrition.py, personal_foods.py, daily_summary.py
│   ├── db/         # supabase_client.py, queries.py, models.py
│   └── utils/      # config.py, formatters.py, met_calculator.py
├── dashboard/      # Streamlit analytics dashboard (Stage 3, not yet built)
├── data/           # USDA JSON files (gitignored — download separately)
├── scripts/        # One-time setup scripts
├── Dockerfile      # Railway / Docker deployment
├── railway.toml    # Railway build config
├── Procfile        # Process definition
├── requirements.txt
├── .env.example    # Environment variable template
└── .env            # Local secrets (gitignored — never commit)
```

---

## Security

- **Secrets**: All API keys and tokens are in `.env` locally and in Railway Variables for production. Neither is committed to git.
- **Telegram**: Every incoming message is checked against `TELEGRAM_ALLOWED_CHAT_ID`. Unauthorized users get no response.
- **Supabase**: Uses `service_role` key (kept private). Photos stored in a private storage bucket with no public URLs.
- **Railway**: No secrets in `railway.toml` or any committed file. The `.railway/` local CLI folder is gitignored.

---

## Development Stages

| Stage | Features | Status |
|-------|----------|--------|
| 1 — MVP | Photo logging, inline confirmation, daily summary, /run /weight /water /undo | ✅ Complete |
| 2 — Learning | /label, /add, Hebrew input, personal food history, auto-approve | ✅ Complete |
| 3 — AI Coach | Weekly Hebrew report, Streamlit dashboard, BMR calibration, Strava sync | 📋 Planned |
| 4 — Extras | Barcode scan, Garmin, reminders, Next.js dashboard | 📋 Future |

See [caltrack-architecture.md](caltrack-architecture.md) for the full technical blueprint.
