from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image

_COVER_MAX_WIDTH = 512
_COVER_MAX_HEIGHT = 768
_JPEG_QUALITY = 85
_COVER_EXTS = ("jpg", "jpeg", "png", "webp", "avif", "gif")


def iter_local_cover_candidates(book):
    seen = set()
    local_path = getattr(book, "local_path", None)
    if local_path:
        local_dir = Path(local_path)
        page_count = int(getattr(book, "pages", 0) or 0)
        digit_widths = {1, len(str(page_count or 1)), 2, 3}
        for width in sorted(digit_widths, reverse=True):
            stem = str(1).zfill(width)
            for ext in _COVER_EXTS:
                candidate = local_dir / f"{stem}.{ext}"
                key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                yield candidate
        for candidate in sorted(local_dir.iterdir()) if local_dir.exists() else ():
            if not candidate.is_file() or candidate.suffix.lower().lstrip(".") not in _COVER_EXTS:
                continue
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            yield candidate
    preview_path = getattr(book, "img_preview", None)
    if isinstance(preview_path, str) and preview_path and not preview_path.startswith("http"):
        candidate = Path(preview_path)
        key = str(candidate)
        if key not in seen:
            yield candidate


def resolve_local_cover_path(book) -> Path | None:
    for candidate in iter_local_cover_candidates(book):
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def _open_cover(book) -> Image.Image | None:
    candidate = resolve_local_cover_path(book)
    if candidate is None:
        return None
    try:
        return Image.open(candidate).convert("RGB")
    except OSError:
        return None


def _fit_cover(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("cover image has invalid size")
    scale = min(_COVER_MAX_WIDTH / width, _COVER_MAX_HEIGHT / height, 1.0)
    if scale >= 1.0:
        return image
    target_size = (max(1, math.floor(width * scale)), max(1, math.floor(height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def build_cover_bytes(book) -> bytes:
    cover = _open_cover(book)
    if cover is None:
        raise FileNotFoundError(f"cover not found for book: {getattr(book, 'name', '?')}")
    fitted = _fit_cover(cover)
    output = io.BytesIO()
    fitted.save(output, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return output.getvalue()
