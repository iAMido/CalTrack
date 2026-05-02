# bot/services/ — Business Logic

## What This Is
Pure Python business logic, independent of Telegram. Each service is a module of async functions that can be called from handlers or other services.

## Files
| File | Responsibility | Stage |
|------|---------------|-------|
| `vision.py` | Send photo to OpenRouter, parse JSON response with food items + fdc_ids | 1 |
| `nutrition.py` | Load USDA Foundation Foods, calculate calories/macros from fdc_id × weight | 1 |
| `personal_foods.py` | Learning engine: historical weights, auto-approve logic, correction logging | 2 |
| `calibration.py` | BMR/TDEE calculation (Mifflin-St Jeor), weekly recalibration triggers | 3 |
| `daily_summary.py` | Aggregate today's meals + exercise → formatted summary text | 1 |
| `strava.py` | OAuth2 refresh, fetch recent activities, MET-based calorie fallback | 2 |
| `coach.py` | Weekly AI Coach: gather 7-day data, build prompt, call OpenRouter, return Hebrew report | 3 |

## Vision AI Contract
`vision.py::analyze_meal_photo()` returns:
```python
[
    {
        "ingredient_name": str,      # English name
        "ingredient_name_he": str,   # Hebrew name
        "fdc_id": int | None,        # USDA Foundation Foods ID
        "estimated_weight_grams": int,
        "confidence": float          # 0.0–1.0
    }
]
```

## Nutrition Contract
`nutrition.py::calculate_nutrition(fdc_id, weight_grams)` returns:
```python
{
    "calories": int,
    "protein_g": float,
    "carbs_g": float,
    "fat_g": float,
    "fiber_g": float
}
```

## Auto-Approve Criteria (personal_foods.py)
A food item is auto-approved (no keyboard shown) only if ALL three conditions are met:
1. `total_times_logged >= 5` for this `meal_type`
2. `correction_rate < 20%` (corrections / logs)
3. `weight_std_dev < 30g` across last 5 logs
