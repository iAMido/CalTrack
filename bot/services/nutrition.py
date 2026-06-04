import logging
import os
import time
import httpx
import json as _json
from bot.db import queries as db_queries
from bot.db import supabase_client as db
from bot.utils.config import config

logger = logging.getLogger(__name__)

# In-memory cache: {fdc_id: usda_row_dict}
_usda_cache: dict[int, dict] = {}

# Disk cache for the USDA load. The dataset doesn't change between deploys,
# so we skip the 8 paginated Supabase round trips on cold start when the
# file is fresh. Override with USDA_CACHE_DISABLED=1 to force a re-fetch.
USDA_DISK_CACHE_PATH = os.environ.get(
    "USDA_DISK_CACHE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "usda_cache.json"),
)
USDA_DISK_CACHE_TTL_SECS = 60 * 60 * 24 * 7  # 7 days

# Minimum USDA fuzzy-match score required before we trust the USDA row
# over the AI-provided per-100g values. Below this we use the AI fallback.
# Score tiers (see find_usda_match):
#   exact desc match          -> 1000
#   first-comma segment equal -> 500
#   description starts with   -> 200+
#   substring                 -> 100+
#   weak overlap              -> < 100
USDA_MIN_SCORE = 200


def _load_usda_from_disk() -> list[dict] | None:
    """Return cached USDA rows from disk if fresh, else None."""
    if os.environ.get("USDA_CACHE_DISABLED") == "1":
        return None
    try:
        mtime = os.path.getmtime(USDA_DISK_CACHE_PATH)
        if time.time() - mtime > USDA_DISK_CACHE_TTL_SECS:
            return None
        with open(USDA_DISK_CACHE_PATH, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if isinstance(data, list) and len(data) > 100:
            return data
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"USDA disk cache read failed: {e}")
    return None


def _save_usda_to_disk(rows: list[dict]) -> None:
    """Persist USDA rows to disk for the next cold start."""
    try:
        os.makedirs(os.path.dirname(USDA_DISK_CACHE_PATH), exist_ok=True)
        with open(USDA_DISK_CACHE_PATH, "w", encoding="utf-8") as f:
            _json.dump(rows, f)
        logger.info(f"USDA disk cache written ({len(rows)} rows)")
    except Exception as e:
        logger.warning(f"USDA disk cache write failed: {e}")


async def load_usda_cache() -> None:
    """Load all USDA Foundation Foods into memory.
    Prefers a fresh on-disk JSON snapshot to avoid the 8-page Supabase fetch
    on every cold boot. Falls back to the DB if no fresh snapshot exists.
    """
    global _usda_cache
    cached = _load_usda_from_disk()
    if cached:
        for f in cached:
            if f.get("fdc_id"):
                _usda_cache[f["fdc_id"]] = f
        logger.info(f"USDA cache loaded from disk: {len(_usda_cache)} foods")
        return

    foods = await db_queries.get_all_usda_foods()
    for f in foods:
        if f.get("fdc_id"):
            _usda_cache[f["fdc_id"]] = f
    logger.info(f"USDA cache loaded from DB: {len(_usda_cache)} foods")

    # Best-effort write so the next boot is fast
    _save_usda_to_disk(foods)


def get_usda_food_sync(fdc_id: int) -> dict | None:
    return _usda_cache.get(fdc_id)


def calculate_nutrition(fdc_id: int | None, weight_grams: int, ai_fallback: dict | None = None) -> dict:
    """
    Calculate nutrition for weight_grams of fdc_id food.
    Falls back to ai_fallback values (from vision AI) if no USDA match.
    Callers must apply USDA_MIN_SCORE filtering before passing fdc_id here.
    """
    empty = {"calories": 0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fiber_g": 0.0}

    food = _usda_cache.get(fdc_id) if fdc_id else None

    # If USDA match has no calorie data, fall through to AI values
    if food and not food.get("calories_per_100g"):
        food = None

    if not food and ai_fallback:
        food = ai_fallback

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


def find_usda_match(ingredient_name: str) -> tuple[int | None, float]:
    """
    Find the best (fdc_id, score) for an ingredient name.
    Score tiers:
      1000 — desc exactly equals name
       500 — first segment before comma exactly equals name
      200+ — desc starts with name
      100+ — name is substring of desc
       <100 — weak word overlap (caller should ignore)
    Returns (None, 0.0) if no candidate has any overlap.
    """
    if not ingredient_name or not _usda_cache:
        return None, 0.0
    name_lower = ingredient_name.lower().strip()
    name_words = set(name_lower.split())

    best_fdc_id: int | None = None
    best_score = 0.0

    for fdc_id, food in _usda_cache.items():
        if not food.get("calories_per_100g"):
            continue
        desc = (food.get("description") or "").lower()
        desc_clean = desc.split(",")[0].strip()
        desc_words = set(w.strip(",()") for w in desc.split())

        overlap = name_words & desc_words
        if not overlap:
            continue

        # Tier 1: exact description match
        if desc == name_lower:
            score = 1000.0
        # Tier 2: first comma segment exactly equals query
        elif desc_clean == name_lower:
            score = 500.0
        # Tier 3: description starts with query
        elif desc_clean.startswith(name_lower) or desc.startswith(name_lower):
            score = 200.0 + len(name_lower)
        # Tier 4: query is substring of description
        elif name_lower in desc:
            score = 100.0 + len(name_lower)
        # Tier 5: word overlap
        else:
            score = float(len(overlap))

        # Reward shorter / simpler descriptions (less risk of wrong modifier)
        if len(desc_words) > 0:
            score += (len(overlap) / len(desc_words)) * 20

        # Penalty for descriptions containing modifier words the user did not ask for
        for unwanted in ("dried", "powdered", "powder", "dehydrated", "freeze-dried"):
            if unwanted in desc and unwanted not in name_lower:
                score -= 250  # strong penalty — usually wrong default
                break

        if score > best_score:
            best_score = score
            best_fdc_id = fdc_id

    return best_fdc_id, best_score


def find_usda_match_strict(ingredient_name: str) -> int | None:
    """Convenience wrapper: returns fdc_id only when score >= USDA_MIN_SCORE."""
    fdc_id, score = find_usda_match(ingredient_name)
    if fdc_id is not None and score >= USDA_MIN_SCORE:
        return fdc_id
    return None


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


async def estimate_nutrition_text(food_name: str) -> dict | None:
    """
    Ask OpenRouter for nutrition per 100g via text (no image).
    Returns dict with keys calories_per_100g, protein_per_100g, carbs_per_100g,
    fat_per_100g, fiber_per_100g — or None on failure.

    Shared by /add precise mode and the "➕ Missing item" callback flow.
    """
    if not config.openrouter_api_key:
        return None
    try:
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": (
                    "Return ONLY a JSON object with nutrition per 100g for the food. "
                    "Keys: calories_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, fiber_per_100g. "
                    "Values must be realistic — never return 0 for real food. "
                    "No explanation, no markdown."
                )},
                {"role": "user", "content": food_name},
            ],
            "temperature": 0.1,
            "max_tokens": 100,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{config.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1].lstrip("json").strip()
        return _json.loads(content)
    except Exception as e:
        logger.warning(f"Text nutrition estimate failed for '{food_name}': {e}")
        return None
