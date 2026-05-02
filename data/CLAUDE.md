# data/ — Local Data Files

## What This Is
Stores large data files that are downloaded once and used locally. All files in this directory (except this CLAUDE.md) are gitignored.

## Files
| File | Size | Source | Used By |
|------|------|--------|---------|
| `usda_foundation.csv` | ~5 MB | USDA FoodData Central | `scripts/import_usda.py` |
| `foundation_food.json` | ~8 MB | USDA FoodData Central (alt format) | `scripts/import_usda.py` |

## How to Get the USDA Data
1. Go to https://fdc.nal.usda.gov/download-datasets
2. Download **Foundation Foods** (JSON or CSV format)
3. Place the file here as `usda_foundation.csv` or `foundation_food.json`
4. Run: `python scripts/import_usda.py`

## Why Local?
The USDA FoodData Central API returns hundreds of results for any search (brands, raw vs. cooked, different countries). The local Foundation Foods table has ~2,000 curated base ingredients with unambiguous fdc_ids — the Vision AI can match directly to these IDs, eliminating search ambiguity and API latency.
