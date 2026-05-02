# bot/ — Telegram Bot Application

## What This Is
The core application. Runs as a long-lived Python process, listens for Telegram updates via polling (dev) or webhooks (production), and orchestrates all meal logging logic.

## Entry Point
`bot/main.py` — registers all handlers and starts the bot.
Run with: `python -m bot.main`

## Subdirectories
| Dir | Purpose |
|-----|---------|
| `handlers/` | Telegram update handlers — one file per update type |
| `services/` | Business logic — AI, nutrition, learning engine, strava, coach |
| `db/` | Database layer — Supabase client, Pydantic models, query helpers |
| `utils/` | Shared utilities — config, message formatters, MET calculator |

## Security
Every handler verifies `update.effective_chat.id` against `TELEGRAM_ALLOWED_CHAT_ID` from config. Unauthorized users receive ⛔ and no further processing occurs.

## State Management
Pending meal data (between photo receipt and user confirmation) is stored in `context.user_data['pending_meal']`. This is in-memory; restarting the bot clears any unconfirmed meals.

## Key Data Flow
```
Photo received
  → handlers/photo.py
    → services/vision.py      (OpenRouter: identify food items)
    → services/nutrition.py   (USDA lookup: get calories per item)
    → services/personal_foods.py (check history, maybe auto-approve)
    → utils/formatters.py     (build inline keyboard message)
  → User confirms/corrects via callbacks
    → handlers/callbacks.py
      → db/supabase_client.py (save meal + items)
      → services/daily_summary.py (update daily totals)
```
