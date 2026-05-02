import httpx
import json
import base64
import logging
from bot.utils.config import config

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """You are a food identification specialist. Analyze the meal photo and identify every distinct food item visible.

RULES:
1. Identify each food item separately (e.g., rice and chicken are two items).
2. Estimate weight in grams. Be CONSERVATIVE — round down when uncertain.
3. Match each item to the closest entry from the FOOD DATABASE provided. Return the fdc_id from the database.
   If no close match exists, return fdc_id as null.
4. ALWAYS provide calories_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g using your nutritional knowledge.
   These are used as fallback when no USDA match exists.
5. Include a confidence score (0.0 to 1.0) for your weight estimate.
   If you cannot see the depth/thickness of the food, confidence should be below 0.5.
6. Provide the Hebrew name for each item.
7. Return ONLY valid JSON array. No explanations, no markdown, no code blocks.

OUTPUT FORMAT:
[
  {
    "ingredient_name": "grilled chicken breast",
    "ingredient_name_he": "חזה עוף צלוי",
    "fdc_id": 171077,
    "estimated_weight_grams": 150,
    "confidence": 0.65,
    "calories_per_100g": 165,
    "protein_per_100g": 31.0,
    "carbs_per_100g": 0.0,
    "fat_per_100g": 3.6
  }
]"""


def _build_food_list(usda_foods: list[dict]) -> str:
    """Build a condensed food list string for the vision prompt."""
    lines = []
    for food in usda_foods:
        fdc_id = food.get("fdc_id")
        desc = food.get("description", "")
        category = food.get("food_category", "")
        lines.append(f"{fdc_id}: {desc}" + (f" [{category}]" if category else ""))
    return "\n".join(lines)


def _build_corrections_text(corrections: list[dict]) -> str:
    """Format correction history as few-shot examples for the prompt."""
    if not corrections:
        return ""
    lines = ["USER'S COMMON CORRECTIONS (adjust your estimates based on these):"]
    for c in corrections:
        lines.append(
            f"- {c['ingredient_name']} at {c['meal_type']}: "
            f"you estimated ~{c['avg_ai_estimate']}g but user corrects to "
            f"~{c['avg_user_correction']}g ({c['times_corrected']} corrections). "
            f"Adjust your estimate accordingly."
        )
    return "\n".join(lines)


async def analyze_meal_photo(
    image_bytes: bytes,
    usda_foods: list[dict],
    corrections: list[dict] | None = None,
) -> list[dict]:
    """
    Send photo to OpenRouter vision model and return identified food items.

    Returns list of dicts with keys:
        ingredient_name, ingredient_name_he, fdc_id, estimated_weight_grams, confidence
    """
    if not config.openrouter_api_key:
        logger.warning("OPENROUTER_API_KEY not set — returning mock data")
        return _mock_response()

    food_list = _build_food_list(usda_foods)
    corrections_text = _build_corrections_text(corrections or [])

    system_content = VISION_SYSTEM_PROMPT
    if food_list:
        system_content += f"\n\nFOOD DATABASE:\n{food_list}"
    if corrections_text:
        system_content += f"\n\n{corrections_text}"

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "model": config.openrouter_vision_model,
        "messages": [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    }
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{config.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://caltrack.app",
                "X-Title": "CalTrack",
            },
            json=payload,
        )
        response.raise_for_status()

    raw = response.json()
    content = raw["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    items = json.loads(content)
    if not isinstance(items, list):
        raise ValueError(f"Expected JSON array, got: {type(items)}")

    return items


def _mock_response() -> list[dict]:
    """Fallback mock for development without an API key."""
    return [
        {
            "ingredient_name": "grilled chicken breast",
            "ingredient_name_he": "חזה עוף צלוי",
            "fdc_id": 171077,
            "estimated_weight_grams": 150,
            "confidence": 0.70,
        },
        {
            "ingredient_name": "white rice, cooked",
            "ingredient_name_he": "אורז לבן מבושל",
            "fdc_id": 168880,
            "estimated_weight_grams": 200,
            "confidence": 0.60,
        },
    ]
