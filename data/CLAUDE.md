# data/ — Local Nutrition Data Files

## What This Is
Stores large USDA dataset files downloaded once and imported into Supabase. All data files are gitignored.

## Files
| File | Foods | Source | Status |
|------|-------|--------|--------|
| `foundation_food.json` | ~363 | USDA Foundation Foods | Imported |
| `sr_legacy_food.json` | ~7,793 | USDA SR Legacy | Imported |
| `fndds_food.json` | ~7,000 | USDA FNDDS (mixed dishes) | Optional |

## Current State
8,156 foods imported into Supabase `usda_foundation` table (Foundation + SR Legacy merged, deduplicated by fdc_id).

## How to Download More Datasets
All from: https://fdc.nal.usda.gov/download-datasets
- **Foundation Foods** → save as `data/foundation_food.json`
- **SR Legacy** → save as `data/sr_legacy_food.json`
- **FNDDS** → save as `data/fndds_food.json`

Then run: `python scripts/import_usda.py` — handles all three automatically.

## Why Local?
The import script merges datasets and deduplicates by fdc_id. Foundation Foods takes priority (highest accuracy). The bot loads all foods into memory on startup for fast lookup without per-request DB queries.

## Nutrition Matching Strategy
1. Vision AI identifies food by name and provides its own calorie estimates
2. `nutrition.py::find_usda_match()` does local word-overlap matching against 8k+ USDA descriptions
3. If USDA match found → use USDA nutrition values (authoritative)
4. If no match → use AI-provided `calories_per_100g` etc. as fallback
