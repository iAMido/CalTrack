import logging
from bot.db import queries as db_queries
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

# In-memory cache: {fdc_id: usda_row_dict}
_usda_cache: dict[int, dict] = {}


async def load_usda_cache() -> None:
    """Load all USDA Foundation Foods into memory. Call once on startup."""
    global _usda_cache
    foods = await db_queries.get_all_usda_foods()
    for f in foods:
        if f.get("fdc_id"):
            _usda_cache[f["fdc_id"]] = f
    logger.info(f"USDA cache loaded: {len(_usda_cache)} foods")


def get_usda_food_sync(fdc_id: int) -> dict | None:
    return _usda_cache.get(fdc_id)


def calculate_nutrition(fdc_id: int | None, weight_grams: int) -> dict:
    """
    Calculate nutrition for weight_grams of fdc_id food.
    Returns zeros if fdc_id is unknown.
    """
    empty = {"calories": 0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fiber_g": 0.0}

    if fdc_id is None:
        return empty

    food = get_usda_food_sync(fdc_id)
    if not food:
        return empty

    factor = weight_grams / 100.0
    return {
        "calories": round((food.get("calories_per_100g") or 0) * factor),
        "protein_g": round((food.get("protein_per_100g") or 0) * factor, 2),
        "carbs_g": round((food.get("carbs_per_100g") or 0) * factor, 2),
        "fat_g": round((food.get("fat_per_100g") or 0) * factor, 2),
        "fiber_g": round((food.get("fiber_per_100g") or 0) * factor, 2),
    }


def build_food_list_for_prompt() -> list[dict]:
    """Return all cached USDA foods for the vision prompt."""
    return list(_usda_cache.values())


def calculate_meal_totals(items: list[dict]) -> dict:
    """Sum nutrition across all confirmed meal items."""
    totals = {"total_calories": 0, "total_protein_g": 0.0, "total_carbs_g": 0.0, "total_fat_g": 0.0, "total_fiber_g": 0.0}
    for item in items:
        totals["total_calories"] += item.get("calories") or 0
        totals["total_protein_g"] += item.get("protein_g") or 0
        totals["total_carbs_g"] += item.get("carbs_g") or 0
        totals["total_fat_g"] += item.get("fat_g") or 0
        totals["total_fiber_g"] += item.get("fiber_g") or 0
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()}
