"""Image preparation before the model sees a photo."""
from __future__ import annotations

import io

from PIL import Image, ImageOps


def prepare_image(data: bytes, max_side: int = 1600, quality: int = 90) -> bytes:
    """Fix phone rotation, convert to RGB JPEG, shrink the long side to max_side. Drops EXIF (incl. location)."""
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)
    return out.getvalue()
