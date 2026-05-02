# bot/handlers/ — Telegram Update Handlers

## What This Is
One file per category of Telegram update. Handlers receive raw Telegram updates, apply security checks, delegate to services, and send responses back to the user.

## Files
| File | Handles |
|------|---------|
| `photo.py` | Incoming meal photos — the main logging flow |
| `commands.py` | All slash commands: `/weight`, `/water`, `/run`, `/summary`, `/status`, `/undo`, `/history`, `/help` |
| `callbacks.py` | Inline keyboard button presses — weight selection, confirm all, cancel, re-analyze |
| `admin.py` | Admin commands: `/calibrate`, `/stats`, `/export` |

## Callback Data Format
Inline button callbacks use a compact format to stay under Telegram's 64-byte limit:
- `w:{idx}:{grams}` — set item `idx` weight to `grams` (e.g., `w:0:150`)
- `w:{idx}:m` — trigger manual weight entry for item `idx`
- `mt:{type}` — override meal type (e.g., `mt:dinner`)
- `ok` — confirm all items and save meal
- `no` — cancel pending meal
- `re` — discard and re-analyze the photo
- `add` — add a missing item manually

## Pending Meal State
When a photo is processed, the pending meal dict is stored in `context.user_data['pending_meal']`:
```python
{
    'meal_type': 'lunch',
    'photo_path': 'meals/2026-04-28/uuid.jpg',
    'photo_file_id': 'telegram_file_id',
    'items': [
        {
            'ingredient_name': 'grilled chicken breast',
            'ingredient_name_he': 'חזה עוף צלוי',
            'fdc_id': 171077,
            'weight_grams': 150,       # current confirmed/adjusted weight
            'ai_estimated_grams': 150, # original AI estimate (never changes)
            'ai_confidence': 0.72,
            'weight_source': 'ai_estimate',  # updated when user confirms
            'auto_approved': False
        }
    ]
}
```
