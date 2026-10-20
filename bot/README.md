# bot/

> **Current truth (2026-10-20): CalTrack is WhatsApp-only. There is no Telegram bot any more.**
> Ido logs meals in the WhatsApp group "CalTrack". TARS's wa-gateway posts it to `bot/whatsapp/server.py`
> (127.0.0.1:8093). `bot/runner.py` runs the scheduler (nudges 11:00/14:00/19:30, calibration Sun 20:00,
> coach Sat 22:00) and the listener. `python-telegram-bot` is removed (CalTrack #18–#21); the handlers
> use `bot/ui.py` for buttons, which `bot/whatsapp/shim.py` turns into WhatsApp polls.
> Anything below that says Telegram, `/commands` via BotFather, `TELEGRAM_*` or polling is **history**.
> QA after any change (run in the image on the VPS, nothing is sent and nothing is written):
> `scripts/wa_smoke.py` (quick, vs a baseline) · `scripts/wa_deep_qa.py` (every command and flow, every DB write
> intercepted and listed) · `scripts/db_fingerprint.py` before/after (proves the real DB is unchanged).
> **Never send `שבוע` or save a meal through a raw test**: those write (coach_reports, personal_foods).


The CalTrack application (WhatsApp only since 2026-10-20).

## Entry Point

```bash
python -m bot.main
```

## Directory Structure

```
bot/
├── main.py          # Application entry point — registers all handlers and starts polling
├── handlers/        # feature handlers, called by the WhatsApp adapter
├── services/        # Business logic (AI, nutrition, learning engine)
├── db/              # Database layer (Supabase client + queries)
└── utils/           # Shared utilities (config, formatters, calculators)
```

## handlers/

| File | Handles |
|------|---------|
| `photo.py` | Meal photo flow: vision AI → inline keyboard → save |
| `commands.py` | `/weight`, `/water`, `/run`, `/summary`, `/status`, `/undo`, `/history`, `/add`, `/help` |
| `callbacks.py` | Inline keyboard button presses (weight confirmation, corrections) |
| `admin.py` | `/calibrate`, admin-only commands |
| `label.py` | `/label` — scan nutrition label → save as personal food |

## services/

| File | Responsibility |
|------|---------------|
| `vision.py` | OpenRouter vision AI — sends photo, receives food item JSON |
| `nutrition.py` | USDA lookup cache + fuzzy matcher + AI fallback for unknown foods |
| `personal_foods.py` | Learning engine — historical weights, auto-approve logic |
| `translator.py` | Hebrew → English translation (local map + gpt-4o-mini fallback) |
| `daily_summary.py` | Compute and format daily totals |
| `calibration.py` | BMR/TDEE recalculation |

## db/

| File | Responsibility |
|------|---------------|
| `supabase_client.py` | Low-level Supabase helpers: `insert`, `upsert`, `select`, `update`, `delete_row`, `upload_photo`, `get_photo_url` |
| `queries.py` | Higher-level queries: `get_user_profile`, `get_last_n_meals`, `refresh_daily_summary`, USDA pagination |
| `models.py` | Pydantic models matching the database schema |

## utils/

| File | Responsibility |
|------|---------------|
| `config.py` | All settings loaded from `.env` via pydantic-settings |
| `formatters.py` | Message formatting helpers (bot/ui.py buttons), `detect_meal_type` |
| `met_calculator.py` | MET-based calorie burn calculation for runs |
