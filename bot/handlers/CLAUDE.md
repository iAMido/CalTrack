# bot/handlers/ — Telegram Update Handlers

## What This Is
One file per category of Telegram update. Handlers apply auth checks, delegate to services, and reply to the user.

## Files & Status
| File | Handles | Status |
|------|---------|--------|
| `photo.py` | Meal photos → vision AI → personal food lookup → keyboard | ✅ Working |
| `commands.py` | `/weight`, `/water`, `/run`, `/summary`, `/status`, `/undo`, `/history`, `/week`, `/help` | ✅ Working |
| `callbacks.py` | Weight buttons, Confirm All, Cancel, Re-analyze, Missing item, meal type change | ✅ Working |
| `admin.py` | `/calibrate`, `/stats` | ✅ Working |

## Pending Commands (Stage 2)
| Command | Description |
|---------|-------------|
| `/label` | Photo a nutrition label → extract macros → save as custom food |
| `/add` | Retroactive text addition: `/add lunch 15g olive oil` |

## Callback Data Format
| Data | Action |
|------|--------|
| `w:{idx}:{grams}` | Set item weight |
| `w:{idx}:m` | Manual weight entry (prompts text reply) |
| `mt:{type}` | Change meal type |
| `ok` | Confirm all + save to DB |
| `no` | Cancel pending meal |
| `re` | Discard + re-analyze |
| `add` | Add missing item (prompts text reply: "name, grams") |
| `undo:{meal_id}` | Mark meal as cancelled |

## Text Input Handler (callbacks.py::handle_text_input)
Handles two awaiting states stored in `context.user_data`:
- `awaiting_manual_weight` → user typed grams for an existing item
- `awaiting_add_item` → user typed "name, grams" for a new item

## Pending Meal State
Stored in `context.user_data['pending_meal']` between photo receipt and confirmation:
```python
{
    "meal_id": "uuid",
    "meal_type": "dinner",
    "photo_path": "2026-05-02/uuid.jpg",  # None if storage bucket missing
    "items": [{
        "ingredient_name": "peach",
        "ingredient_name_he": "אפרסק",
        "fdc_id": 9236,           # from local USDA match
        "ai_fallback": {...},     # AI calorie estimates (used if no USDA match)
        "weight_grams": 150,
        "ai_estimated_grams": 150,
        "calories": 58,
        ...
    }]
}
```
