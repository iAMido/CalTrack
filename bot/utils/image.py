"""Image resizing helper for meal photos.

Phone photos arrive at 2-4 MB. We don't need that for either:
  - storage   (cheaper + faster dashboard loads)
  - vision AI (1280px is more than enough to ID food items)

A single resize step happens at the top of the photo flow; the same
bytes feed both upload_photo() and analyze_meal_photo().
"""

import io
import logging
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Default upload caps. 1280px wide @ JPEG q85 typically lands at 200-500 KB
# for a phone meal photo, vs 2-4 MB raw — roughly 10x smaller with no
# visible quality loss for food identification.
DEFAULT_MAX_DIM = 1280
DEFAULT_JPEG_QUALITY = 85


def resize_for_upload(
    raw_bytes: bytes,
    max_dim: int = DEFAULT_MAX_DIM,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> bytes:
    """Re-encode a meal photo as a smaller JPEG. Returns raw bytes on failure.

    - Honours EXIF orientation so portrait phone shots aren't sideways.
    - Caps the longest edge at `max_dim` (default 1280).
    - Strips EXIF + ICC profiles to keep the file lean.
    - Always returns JPEG even if the input was PNG/WebP.
    """
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            # Rotate per EXIF before stripping metadata
            im = ImageOps.exif_transpose(im)
            # Convert to RGB so PNG/WebP/transparent inputs are JPEG-safe
            if im.mode != "RGB":
                im = im.convert("RGB")
            w, h = im.size
            longest = max(w, h)
            if longest > max_dim:
                scale = max_dim / longest
                new_size = (int(w * scale), int(h * scale))
                im = im.resize(new_size, Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            resized = out.getvalue()
            logger.info(
                f"Photo resized: {len(raw_bytes)/1024:.0f} KB "
                f"({w}x{h}) → {len(resized)/1024:.0f} KB "
                f"({im.size[0]}x{im.size[1]})"
            )
            return resized
    except Exception as e:
        logger.warning(
            f"Photo resize failed ({type(e).__name__}: {e}); using raw bytes"
        )
        return raw_bytes
