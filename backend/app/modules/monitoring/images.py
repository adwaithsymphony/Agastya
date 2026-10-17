"""Upload validation: size limit, real format detection (not the filename), integrity, dimensions.

The stored copy is re-encoded from decoded pixels, which drops EXIF/GPS metadata and any
non-image payload appended to the file.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import AppError

ALLOWED = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
MIN_SIDE, MAX_SIDE, MAX_PIXELS = 64, 8000, 40_000_000


class InvalidImage(AppError):
    status_code = 422
    code = "invalid_image"


@dataclass
class ValidatedImage:
    data: bytes
    content_type: str
    ext: str
    width: int
    height: int
    sha256: str


def validate_image(raw: bytes) -> ValidatedImage:
    limit = get_settings().max_upload_mb * 1024 * 1024
    if not raw:
        raise InvalidImage("The file is empty.")
    if len(raw) > limit:
        raise InvalidImage(f"The image is larger than {get_settings().max_upload_mb} MB.")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            w, h = probe.size
            if fmt not in ALLOWED:
                raise InvalidImage("Only JPEG, PNG or WebP photographs are accepted.")
            if w * h > MAX_PIXELS:
                raise InvalidImage("The image resolution is too large.")
            probe.verify()
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = ImageOps.exif_transpose(img).convert("RGB")
    except InvalidImage:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, ValueError):
        raise InvalidImage("The file could not be read as an image. It may be damaged or not a photograph.")
    w, h = img.size
    if min(w, h) < MIN_SIDE:
        raise InvalidImage(f"The image is too small; use at least {MIN_SIDE}×{MIN_SIDE} pixels.")
    if max(w, h) > MAX_SIDE:
        raise InvalidImage("The image dimensions are too large.")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    data = out.getvalue()
    return ValidatedImage(data=data, content_type="image/jpeg", ext="jpg", width=w, height=h,
                          sha256=hashlib.sha256(data).hexdigest())
