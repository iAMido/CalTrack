# bot/utils/ — Shared Utilities

## What This Is
Stateless helper modules used across handlers, services, and scripts.

## Files
| File | Purpose |
|------|---------|
| `config.py` | pydantic-settings BaseSettings — loads all `.env` vars, typed access via `config.*` |
| `formatters.py` | Builds meal confirmation keyboard and all Telegram message text |
| `met_calculator.py` | MET-based calorie burn for runs when device data unavailable |

## config.py — Key Fields
```python
config.telegram_bot_token
config.telegram_allowed_chat_id
config.allowed_chat_ids           # set with single chat_id
config.openrouter_api_key
config.openrouter_vision_model    # "openai/gpt-4o"
config.openrouter_coach_model     # "anthropic/claude-sonnet-4-5"
config.supabase_url
config.supabase_key               # service_role key
config.user_timezone              # "Asia/Jerusalem"
config.min_calories_male          # 1500
config.min_calories_female        # 1200
```

## formatters.py — Meal Keyboard Layout
Each item renders as:
```
*N. food name* (hebrew name)
   AI estimate: Xg (confidence: Y%)
[ 50g ][ 100g ][ 150g ][ ✏️ ][ 🔄 ]
```
- Weight buttons: from `weight_suggestions` list
- ✏️ → manual gram entry (`w:{idx}:m`)
- 🔄 → rename/correct food (`rename:{idx}`)

Action row:
```
[ ✅ Confirm All ][ ❌ Cancel ]
[ 🔄 Re-analyze  ][ ➕ Missing item? ]
```

**Important**: `cal = item.get("calories") or nutrition_map.get(fdc_id, {}).get("calories", 0)`
— reads calories from item directly so AI-fallback foods display correctly (not zero).

## met_calculator.py — MET Values
| Pace | MET |
|------|-----|
| < 5:00/km | 11.0 |
| 5:00–6:00/km | 9.8 |
| 6:00–7:00/km | 8.3 |
| > 7:00/km | 7.0 |

Formula: `calories = MET × weight_kg × duration_hours`
