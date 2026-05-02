# bot/utils/ — Shared Utilities

## What This Is
Stateless helper modules used across handlers, services, and scripts.

## Files
| File | Purpose |
|------|---------|
| `config.py` | pydantic-settings BaseSettings — loads all `.env` vars, typed access via `config.*` |
| `formatters.py` | Builds meal confirmation keyboard and all Telegram message text |
| `met_calculator.py` | MET-based calorie burn for runs when device data unavailable |

## Config Usage
```python
from bot.utils.config import config

config.telegram_bot_token
config.telegram_allowed_chat_id
config.openrouter_api_key
config.supabase_url / config.supabase_key
config.user_timezone          # "Asia/Jerusalem"
config.min_calories_male      # 1500
config.min_calories_female    # 1200
```

## formatters.py Key Functions
- `build_meal_keyboard(pending_meal, nutrition_map)` → `(text, InlineKeyboardMarkup)`
  - Uses `item.get("calories")` directly (not nutrition_map lookup) so AI-fallback calories display correctly
- `format_post_save(daily)` → post-confirmation message with daily totals
- `format_daily_summary(date, daily, meals)` → full `/summary` output
- `detect_meal_type()` → breakfast/lunch/snack/dinner based on local time

## MET Values (met_calculator.py)
| Pace | MET |
|------|-----|
| < 5:00/km | 11.0 |
| 5:00–6:00/km | 9.8 |
| 6:00–7:00/km | 8.3 |
| > 7:00/km | 7.0 |

Formula: `calories = MET × weight_kg × duration_hours`
