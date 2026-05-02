# bot/services/ — Business Logic

## What This Is
Pure Python business logic, independent of Telegram. Each service is a module of async functions called from handlers or other services.

## Files & Status
| File | Responsibility | Status |
|------|---------------|--------|
| `vision.py` | Send photo to OpenRouter; AI returns food name + macros; no food list in prompt | ✅ Working |
| `nutrition.py` | Load 8k USDA foods into memory; fuzzy name matcher; AI fallback calories | ✅ Working |
| `personal_foods.py` | Learning engine: track per-food history, auto-approve after 5+ logs | ✅ Working |
| `calibration.py` | BMR/TDEE recalculation (Mifflin-St Jeor); logs to calibration_log | ✅ Working |
| `daily_summary.py` | Aggregate today's meals + runs + water + weight → formatted text | ✅ Working |
| `strava.py` | OAuth2 refresh, fetch recent activities, MET-based calorie fallback | 📋 Stage 2 |
| `coach.py` | Weekly AI Coach: 7-day data → OpenRouter → Hebrew report | 📋 Stage 3 |

## Vision AI Contract (vision.py)
`analyze_meal_photo()` returns:
```python
[{
    "ingredient_name": "peach",
    "ingredient_name_he": "אפרסק",
    "estimated_weight_grams": 150,
    "confidence": 0.80,
    "calories_per_100g": 39,
    "protein_per_100g": 0.9,
    "carbs_per_100g": 9.5,
    "fat_per_100g": 0.3,
    "fiber_per_100g": 1.5
}]
```
No fdc_id in AI response — matched locally by `find_usda_match()`.

## Nutrition Lookup Flow (nutrition.py)
1. `load_usda_cache()` — called once on startup, paginates through all 8,156 rows
2. `find_usda_match(name)` — word-overlap scoring against USDA descriptions
3. `calculate_nutrition(fdc_id, grams, ai_fallback)` — USDA if matched, else AI values

## Auto-Approve Criteria (personal_foods.py)
All three conditions must be met:
1. `total_times_logged >= 5` for this `meal_type`
2. `correction_rate < 20%`
3. `weight_std_dev < 30g` across last 5 logs
