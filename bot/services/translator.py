import httpx
import logging
import re
from bot.utils.config import config

logger = logging.getLogger(__name__)

_HEBREW = re.compile(r'[֐-׿יִ-ﭏ]')

# Map Hebrew meal-type words to English (fast path, no API call needed)
_MEAL_TYPE_MAP = {
    "ארוחת בוקר": "breakfast", "בוקר": "breakfast",
    "ארוחת צהריים": "lunch", "צהריים": "lunch",
    "ארוחת ערב": "dinner", "ערב": "dinner",
    "חטיף": "snack", "נשנוש": "snack",
}

# Hebrew unit words → English
_UNIT_MAP = {
    "גרם": "g", "גר": "g", "גר'": "g",
    "מ\"ל": "ml", "מיליליטר": "ml",
    "כוס": "cup", "כפית": "tsp", "כף": "tbsp",
}


def is_hebrew(text: str) -> bool:
    return bool(_HEBREW.search(text))


def _fast_replace(text: str) -> str:
    """Replace known Hebrew meal-type and unit words before API call."""
    result = text
    for he, en in _MEAL_TYPE_MAP.items():
        result = re.sub(re.escape(he), en, result, flags=re.IGNORECASE)
    for he, en in _UNIT_MAP.items():
        result = re.sub(re.escape(he), en, result, flags=re.IGNORECASE)
    return result


async def translate(text: str) -> str:
    """
    Translate Hebrew text to English.
    Returns original text unchanged if no Hebrew detected.
    Optimised for food/calorie tracking context.
    """
    if not is_hebrew(text):
        return text

    # Try fast local replacement first (saves API call for simple cases)
    quick = _fast_replace(text)
    if not is_hebrew(quick):
        logger.debug(f"Fast-translated: '{text}' -> '{quick}'")
        return quick.strip()

    # Fall back to cheap AI model
    try:
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a translator for a calorie tracking app. "
                        "Translate the user's Hebrew message to English. "
                        "Keep numbers, units (g, ml, kg), and meal types (breakfast/lunch/dinner/snack) in English. "
                        "Return ONLY the translated text, nothing else."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 150,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{config.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
        translated = r.json()["choices"][0]["message"]["content"].strip()
        logger.info(f"Translated: '{text}' -> '{translated}'")
        return translated
    except Exception as e:
        logger.warning(f"Translation failed, using original: {e}")
        return text
