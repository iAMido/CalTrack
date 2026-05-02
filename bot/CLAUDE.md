# bot/ — Telegram Bot Application

## What This Is
The core application. Runs as a long-lived Python process, listens for Telegram updates via polling, and orchestrates all meal logging logic.

## Entry Point
`bot/main.py` — registers all handlers and starts the bot.
Run with: `python -m bot.main`

## Subdirectories
| Dir | Purpose |
|-----|---------|
| `handlers/` | Telegram update handlers — one file per update type |
| `services/` | Business logic — AI vision, nutrition, translation, learning engine |
| `db/` | Database layer — Supabase client, query helpers |
| `utils/` | Shared utilities — config, message formatters, MET calculator |

## Security
Every handler checks `update.effective_chat.id` against `TELEGRAM_ALLOWED_CHAT_ID`. Unauthorized users get no response.

## State Management
Pending meal data lives in `context.user_data['pending_meal']` (in-memory, cleared on restart).

Awaiting states (set in `context.user_data`):
| Key | Set by | Cleared by |
|-----|--------|------------|
| `awaiting_label_photo` | `/label` command | photo handler |
| `awaiting_manual_weight` | ✏️ button | text input handler |
| `awaiting_add_item` | ➕ Missing item button | text input handler |
| `awaiting_rename_item` | 🔄 rename button | text input handler |

## Key Data Flow
```
Photo received
  → label.py::handle_label_photo()   if awaiting_label_photo
  → handlers/photo.py                otherwise
      → services/vision.py           (OpenRouter: identify foods + estimate calories)
      → services/nutrition.py        (USDA fuzzy match + AI fallback)
      → services/personal_foods.py   (history lookup, auto-approve check)
      → utils/formatters.py          (build inline keyboard)
  → User taps weight / 🔄 rename / ➕ missing item
      → handlers/callbacks.py
  → User taps Confirm All
      → db/supabase_client.py        (save meal + items)
      → db/queries.py                (refresh daily_summary)

Text message received
  → services/translator.py           (Hebrew → English if needed)
  → handlers/callbacks.py            (route by awaiting_* state)
```
