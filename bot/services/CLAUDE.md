# bot/services/ — Business Logic

## What This Is
Pure Python business logic, independent of Telegram. Each service is a module of async functions called from handlers.

## Files & Status
| File | Responsibility | Status |
|------|---------------|--------|
| `vision.py` | Meal photo analysis + nutrition label extraction via OpenRouter | ✅ |
| `nutrition.py` | 8,156-food USDA in-memory cache + fuzzy matcher + AI fallback | ✅ |
| `translator.py` | Hebrew → English translation (fast local map + gpt-4o-mini fallback) | ✅ |
| `personal_foods.py` | Per-food history, auto-approve logic, correction logging | ✅ |
| `calibration.py` | BMR/TDEE recalculation (Mifflin-St Jeor), calibration_log | ✅ |
| `daily_summary.py` | Aggregate today's meals + runs + water + weight | ✅ |
| `strava.py` | OAuth2 refresh, fetch activities, MET calorie fallback | 📋 Stage 3 |
| `coach.py` | Weekly AI Coach: 7-day data → OpenRouter → Hebrew report | 📋 Stage 3 |

## vision.py — Two Prompts
**VISION_SYSTEM_PROMPT** (meal photos):
- AI identifies foods by name, estimates weight + confidence
- Returns `calories_per_100g`, `protein_per_100g`, etc. as AI fallback values
- No USDA food list in prompt (was causing 400 errors at 8k+ foods)

**LABEL_SYSTEM_PROMPT** (nutrition labels):
- Extracts per-100g nutrition from package label photo
- Returns single JSON object: `{food_name, calories_per_100g, protein_per_100g, ...}`
- Called by `label.py::handle_label_photo()`

## nutrition.py — Lookup Priority
1. `load_usda_cache()` — paginated startup load of all 8,156 USDA rows
2. `find_usda_match(name)` — word-overlap scoring against USDA descriptions
3. `calculate_nutrition(fdc_id, grams, ai_fallback)` — USDA if matched, else AI values
4. Custom label-scanned foods have fdc_id ≥ 9,000,000 and are in-cache immediately

## translator.py — Translation Strategy
1. `is_hebrew(text)` — checks Unicode range `֐-׿`
2. Fast local replacement: meal types (`ארוחת ערב` → `dinner`), units (`גרם` → `g`)
3. If still Hebrew after fast pass → gpt-4o-mini API call (food-tracking context prompt)
4. Applied in: `/add` args, all text reply inputs (rename, manual weight, add item)

## personal_foods.py — Auto-Approve Criteria
All three must be true:
1. `total_times_logged >= 5` for this `meal_type`
2. `correction_rate < 20%`
3. `weight_std_dev < 30g` across last 5 logs
