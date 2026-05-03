# bot/

The core Telegram bot application.

## Entry Point

```bash
python -m bot.main
```

## Directory Structure

```
bot/
├── main.py          # Application entry point — registers all handlers and starts polling
├── handlers/        # Telegram update handlers (one file per feature area)
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
| `formatters.py` | Telegram message formatting helpers, `detect_meal_type` |
| `met_calculator.py` | MET-based calorie burn calculation for runs |
