# bot/handlers/ — feature handlers (called by the WhatsApp adapter)

> **Current truth (2026-10-20): CalTrack is WhatsApp-only. There is no Telegram bot any more.**
> Ido logs meals in the WhatsApp group "CalTrack". TARS's wa-gateway posts it to `bot/whatsapp/server.py`
> (127.0.0.1:8093). `bot/runner.py` runs the scheduler (nudges 11:00/14:00/19:30, calibration Sun 20:00,
> coach Sat 22:00) and the listener. `python-telegram-bot` is removed (CalTrack #18–#21); the handlers
> use `bot/ui.py` for buttons, which `bot/whatsapp/shim.py` turns into WhatsApp polls.
> Anything below that says Telegram, `/commands` via BotFather, `TELEGRAM_*` or polling is **history**.
> Smoke test after any change: `scripts/wa_smoke.py` (fake gateway, never writes).


## What This Is
One file per feature (written for Telegram; since 2026-10-20 called only through `bot/whatsapp/shim.py`). Handlers apply auth checks, delegate to services, and reply to the user.

## Files & Status
| File | Handles | Status |
|------|---------|--------|
| `photo.py` | Meal photos — checks label state first, then full meal flow | ✅ |
| `label.py` | `/label` command + label photo processing | ✅ |
| `commands.py` | All slash commands | ✅ |
| `callbacks.py` | All inline keyboard callbacks + text input routing | ✅ |
| `admin.py` | `/calibrate`, `/stats` | ✅ |

## Commands (commands.py)
| Command | Usage | Notes |
|---------|-------|-------|
| `/weight` | `/weight 87.3` | Logs body weight, updates profile |
| `/water` | `/water 500` | Logs water in ml |
| `/run` | `/run 5.2 28:30 152` | km, MM:SS, optional HR |
| `/add` | `/add lunch 15g olive oil` | Retroactive item; Hebrew supported |
| `/label` | `/label` then send photo | Scan nutrition label → custom food |
| `/summary` / `/s` | | Full day breakdown |
| `/status` | | Remaining calories |
| `/history` | `/history 5` | Last N meals |
| `/undo` | | Cancel last meal |
| `/week` / `/w` | | Weekly AI report (Stage 3) |
| `/calibrate` | | Recalculate BMR/TDEE |
| `/help` | | Command list |

## Callback Data Format
| Data | Action |
|------|--------|
| `w:{idx}:{grams}` | Set item weight |
| `w:{idx}:m` | Manual weight entry (awaiting_manual_weight) |
| `rename:{idx}` | Rename item (awaiting_rename_item) |
| `mt:{type}` | Change meal type |
| `ok` | Confirm all + save |
| `no` | Cancel |
| `re` | Re-analyze |
| `add` | Add missing item (awaiting_add_item) |
| `undo:{meal_id}` | Mark meal cancelled |

## Text Input Routing (handle_text_input)
All plain text messages go through translator.py first (Hebrew → English), then routed by `context.user_data` state:
1. `awaiting_rename_item` → rename food, re-match USDA, recalculate
2. `awaiting_manual_weight` → update weight, recalculate nutrition
3. `awaiting_add_item` → parse "name, grams", append new item

## /label Flow
1. `/label` → sets `awaiting_label_photo = True`
2. Next photo → `label.py::handle_label_photo()` intercepts before meal flow
3. Vision AI extracts macros (LABEL_SYSTEM_PROMPT, different from meal prompt)
4. Saved to `usda_foundation` (fdc_id ≥ 9,000,000 for custom foods) + `personal_foods`
5. Added to in-memory `_usda_cache` immediately

## Pending Meal State
```python
context.user_data["pending_meal"] = {
    "meal_id": "uuid",
    "meal_type": "snack",
    "photo_path": "2026-05-02/uuid.jpg",
    "items": [{
        "ingredient_name": "tuna",
        "ingredient_name_he": "טונה",
        "fdc_id": 175159,         # from local USDA fuzzy match
        "ai_fallback": {...},     # AI calorie estimates (fallback only)
        "weight_grams": 100,
        "ai_estimated_grams": 100,
        "weight_suggestions": [50, 100, 150],
        "calories": 116,
        "protein_g": 25.5, ...
    }]
}
```
