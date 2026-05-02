"""
One-time script: Imports USDA nutrition data into Supabase.

Supports multiple USDA datasets (all from https://fdc.nal.usda.gov/download-datasets):

  Foundation Foods  (~363 items)  -> data/foundation_food.json
  SR Legacy         (~8,000 items) -> data/sr_legacy_food.json
  FNDDS             (~7,000 items) -> data/fndds_food.json

Run once per dataset. All use upsert on fdc_id so safe to re-run.
Recommended: import all three for best food coverage.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# All supported dataset files, in priority order
DATASET_FILES = [
    os.path.join(DATA_DIR, "foundation_food.json"),   # Foundation Foods
    os.path.join(DATA_DIR, "sr_legacy_food.json"),    # SR Legacy (~8,000 foods)
    os.path.join(DATA_DIR, "fndds_food.json"),        # FNDDS (~7,000 mixed dishes)
]
CSV_PATH = os.path.join(DATA_DIR, "usda_foundation.csv")

BATCH_SIZE = 200


def extract_nutrient(nutrients: list, nutrient_id: int) -> float | None:
    """Extract a specific nutrient value from USDA nutrients list."""
    for n in nutrients:
        if n.get("nutrient", {}).get("id") == nutrient_id:
            return n.get("amount")
    return None


# USDA nutrient IDs
NUTRIENT_IDS = {
    "calories": 1008,      # Energy (kcal)
    "protein": 1003,       # Protein
    "carbs": 1005,         # Carbohydrate, by difference
    "fat": 1004,           # Total lipid (fat)
    "fiber": 1079,         # Fiber, total dietary
    "sodium": 1093,        # Sodium, Na
    "sugar": 2000,         # Sugars, total
}


def parse_json_format(data: dict) -> list[dict]:
    """Parse USDA JSON format — handles Foundation Foods, SR Legacy, and FNDDS."""
    # Each dataset uses a different top-level key
    foods = (
        data.get("FoundationFoods")
        or data.get("SRLegacyFoods")
        or data.get("SurveyFoods")  # FNDDS
        or []
    )
    rows = []

    for food in foods:
        if not food:
            continue
        fdc_id = food.get("fdcId")
        description = food.get("description", "")
        category = food.get("foodCategory", {}).get("description", "") if isinstance(food.get("foodCategory"), dict) else food.get("foodCategory", "")
        nutrients = food.get("foodNutrients", [])

        row = {
            "fdc_id": fdc_id,
            "description": description,
            "food_category": category or None,
            "calories_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["calories"]),
            "protein_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["protein"]),
            "carbs_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["carbs"]),
            "fat_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["fat"]),
            "fiber_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["fiber"]),
            "sodium_mg_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["sodium"]),
            "sugar_per_100g": extract_nutrient(nutrients, NUTRIENT_IDS["sugar"]),
        }

        if fdc_id and description:
            rows.append(row)

    return rows


def parse_csv_format(path: str) -> list[dict]:
    """Parse a simplified CSV with columns: fdc_id,description,category,calories,protein,carbs,fat,fiber"""
    import csv
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "fdc_id": int(row.get("fdc_id", 0)),
                    "description": row.get("description", ""),
                    "food_category": row.get("food_category") or row.get("category") or None,
                    "calories_per_100g": float(row["calories"]) if row.get("calories") else None,
                    "protein_per_100g": float(row["protein"]) if row.get("protein") else None,
                    "carbs_per_100g": float(row["carbs"]) if row.get("carbs") else None,
                    "fat_per_100g": float(row["fat"]) if row.get("fat") else None,
                    "fiber_per_100g": float(row["fiber"]) if row.get("fiber") else None,
                })
            except (ValueError, KeyError):
                continue
    return rows


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")
        sys.exit(1)

    # Collect rows from all available dataset files
    all_rows = []
    found_any = False
    for path in DATASET_FILES:
        if os.path.exists(path):
            found_any = True
            print(f"Loading {os.path.basename(path)}...")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rows = parse_json_format(data)
            print(f"  Parsed {len(rows)} foods.")
            all_rows.extend(rows)

    if not found_any and os.path.exists(CSV_PATH):
        print(f"Loading from {CSV_PATH}...")
        all_rows = parse_csv_format(CSV_PATH)

    if not found_any and not all_rows:
        print("ERROR: No data file found.")
        print("Download datasets from: https://fdc.nal.usda.gov/download-datasets")
        print("  Foundation Foods -> data/foundation_food.json")
        print("  SR Legacy        -> data/sr_legacy_food.json")
        print("  FNDDS            -> data/fndds_food.json")
        sys.exit(1)

    # Deduplicate by fdc_id (Foundation Foods takes priority — highest quality)
    seen = {}
    for row in all_rows:
        fdc_id = row.get("fdc_id")
        if fdc_id and fdc_id not in seen:
            seen[fdc_id] = row
    rows = list(seen.values())

    if not rows:
        print("ERROR: No rows parsed from data files.")
        sys.exit(1)

    print(f"\nTotal unique foods: {len(rows)}. Uploading in batches of {BATCH_SIZE}...")

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    uploaded = 0
    errors = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        try:
            client.table("usda_foundation").upsert(batch, on_conflict="fdc_id").execute()
            uploaded += len(batch)
            print(f"  [OK] {uploaded}/{len(rows)} uploaded...", end="\r")
        except Exception as e:
            errors += len(batch)
            print(f"\n  [ERROR] Batch {i//BATCH_SIZE + 1} failed: {e}")

    print(f"\nImport complete: {uploaded} foods loaded, {errors} errors.")


if __name__ == "__main__":
    main()
