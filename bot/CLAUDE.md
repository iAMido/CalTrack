# bot/ — the CalTrack application (WhatsApp only)

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


## What This Is
The core application. Runs as a long-lived Python process (`bot/runner.py`): the WhatsApp listener + the scheduler. Orchestrates all meal logging logic.

## Entry Point
`bot/main.py` — registers all handlers and starts the bot.
Run with: `python -m bot.main`

## Subdirectories
| Dir | Purpose |
|-----|---------|
| `handlers/` | Handlers (once Telegram's), called by the WhatsApp adapter — one file per feature |
| `services/` | Business logic — AI vision, nutrition, translation, learning engine |
| `db/` | Database layer — Supabase client, query helpers |
| `utils/` | Shared utilities — config, message formatters, MET calculator |

## Security
Handlers check `update.effective_chat.id` against `config.allowed_chat_ids` = {OWNER_CHAT_ID}; the WhatsApp adapter always presents that id. Real access control is the gateway + `WA_TOKEN`.

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
