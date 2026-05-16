import io
import logging
import httpx
from PIL import Image
from pyzbar.pyzbar import decode

logger = logging.getLogger(__name__)


def decode_barcode(image_bytes: bytes) -> str | None:
    """Decode EAN/UPC barcode from image bytes. Returns barcode string or None."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        decoded = decode(img)
        if decoded:
            return decoded[0].data.decode("utf-8")
    except Exception as e:
        logger.warning(f"Barcode decode error: {e}")
    return None


async def lookup_product(barcode: str) -> dict | None:
    """Query Open Food Facts API. Returns product dict or None if not found."""
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers={"User-Agent": "CalTrack/1.0"})
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == 1:
                    return data.get("product")
    except Exception as e:
        logger.warning(f"Open Food Facts lookup error: {e}")
    return None


def extract_nutrition(product: dict) -> dict | None:
    """Extract per-100g nutrition from an Open Food Facts product dict.
    Returns a clean dict or None if calorie data is missing."""
    n = product.get("nutriments", {})

    kcal = n.get("energy-kcal_100g")
    if kcal is None:
        kj = n.get("energy_100g")
        kcal = round(kj / 4.184) if kj else None
    if not kcal:
        return None

    name = (
        product.get("product_name_en")
        or product.get("product_name")
        or "Unknown product"
    )

    return {
        "name": name.strip(),
        "barcode": product.get("code", barcode if "barcode" in dir() else ""),
        "calories_per_100g": round(kcal),
        "protein_per_100g": round(n.get("proteins_100g", 0) * 10) / 10,
        "carbs_per_100g": round(n.get("carbohydrates_100g", 0) * 10) / 10,
        "fat_per_100g": round(n.get("fat_100g", 0) * 10) / 10,
        "fiber_per_100g": round(n.get("fiber_100g", 0) * 10) / 10,
    }
