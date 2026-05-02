# bot/utils/ — Shared Utilities

## What This Is
Stateless helper modules used across handlers, services, and scripts.

## Files
| File | Purpose |
|------|---------|
| `config.py` | Pydantic-settings Config class — loads all env vars from `.env`, provides typed access via `config.*` |
| `formatters.py` | Telegram message formatters — builds the meal confirmation keyboard, daily summary text, post-save confirmation, etc. |
| `met_calculator.py` | MET-based calorie burn calculation for runs when device calories aren't available |

## Config Usage
```python
from bot.utils.config import config

token = config.telegram_bot_token
chat_id = config.telegram_allowed_chat_id
```

## Formatters Output
`formatters.py` returns `(text, InlineKeyboardMarkup)` tuples ready to pass directly to `message.reply_text()`.

## MET Values Used (met_calculator.py)
| Pace | MET |
|------|-----|
| < 5:00/km | 11.0 |
| 5:00–6:00/km | 9.8 |
| 6:00–7:00/km | 8.3 |
| > 7:00/km | 7.0 |

Formula: `calories = MET × weight_kg × duration_hours`
