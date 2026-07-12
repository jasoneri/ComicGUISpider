from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from utils import ori_path, temp_p

PREVIEW_DIR_NAME = "jsoneri_previews"
STATIC_PREVIEW_DIR = ori_path.joinpath("assets/jsoneri/previews")
META_SUFFIX = ".meta.json"
CAPTURE_SETTLE_MS = 350


def default_cache_root() -> Path:
    root = temp_p.joinpath(PREVIEW_DIR_NAME)
    root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_route_url(url: str | None) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    return text.rstrip("/")


def url_hash(url: str) -> str:
    normalized = normalize_route_url(url)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _safe_service_token(service_name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", str(service_name or "").strip())
    return token or "service"


class JsoneriPreviewCache:
    """Resolve site preview images: open-cache > static asset > None."""

    def __init__(self, cache_root: Path | None = None, static_root: Path | None = None):
        self.cache_root = Path(cache_root) if cache_root is not None else default_cache_root()
        self.static_root = Path(static_root) if static_root is not None else STATIC_PREVIEW_DIR
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def resolve(
        self,
        service_name: str,
        route_url: str | None,
        *,
        can_open: bool,
        success: bool,
    ) -> Path | None:
        if not success or not can_open:
            return None
        cached = self._resolve_open_cache(service_name, route_url)
        if cached is not None:
            return cached
        return self._resolve_static(service_name)

    def cache_path_for(self, service_name: str, route_url: str) -> Path:
        service_token = _safe_service_token(service_name)
        digest = url_hash(route_url)
        return self.cache_root.joinpath(f"{service_token}__{digest}.png")

    def meta_path_for(self, image_path: Path) -> Path:
        return image_path.with_suffix(image_path.suffix + META_SUFFIX)

    def save_pixmap(self, service_name: str, route_url: str, pixmap) -> bool:
        from PySide6.QtGui import QPixmap

        if not isinstance(pixmap, QPixmap) or pixmap.isNull():
            return False
        if is_blank_pixmap(pixmap):
            return False
        normalized_url = normalize_route_url(route_url)
        if not normalized_url:
            return False
        target = self.cache_path_for(service_name, normalized_url)
        self._remove_stale_for_service(service_name, keep=target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not pixmap.save(str(target), "PNG"):
            return False
        meta = {"service": str(service_name or "").strip(), "url": normalized_url}
        self.meta_path_for(target).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return True

    def _resolve_open_cache(self, service_name: str, route_url: str | None) -> Path | None:
        normalized_url = normalize_route_url(route_url)
        if not normalized_url:
            return None
        path = self.cache_path_for(service_name, normalized_url)
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        meta_path = self.meta_path_for(path)
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if normalize_route_url(meta.get("url")) != normalized_url:
                return None
        return path

    def _resolve_static(self, service_name: str) -> Path | None:
        service_token = _safe_service_token(service_name)
        for candidate in (
            self.static_root.joinpath(f"{service_token}.png"),
            self.static_root.joinpath(f"{service_token}.jpg"),
            self.static_root.joinpath(f"{service_token}.webp"),
        ):
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        return None

    def _remove_stale_for_service(self, service_name: str, *, keep: Path) -> None:
        prefix = f"{_safe_service_token(service_name)}__"
        for path in self.cache_root.glob(f"{prefix}*.png"):
            if path.resolve() == keep.resolve():
                continue
            path.unlink(missing_ok=True)
            self.meta_path_for(path).unlink(missing_ok=True)


def is_blank_pixmap(pixmap) -> bool:
    """Reject near-empty captures so failed loads do not overwrite good cache."""
    from PySide6.QtGui import QColor, QImage

    if pixmap is None or pixmap.isNull():
        return True
    width = pixmap.width()
    height = pixmap.height()
    if width < 8 or height < 8:
        return True
    image: QImage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
    sample_points = (
        (width // 2, height // 2),
        (width // 4, height // 4),
        (3 * width // 4, height // 4),
        (width // 4, 3 * height // 4),
        (3 * width // 4, 3 * height // 4),
        (width // 2, height // 5),
        (width // 2, 4 * height // 5),
        (width // 5, height // 2),
        (4 * width // 5, height // 2),
    )
    luminances: list[float] = []
    for sample_x, sample_y in sample_points:
        color = QColor(image.pixel(sample_x, sample_y))
        luminances.append(0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue())
    if not luminances:
        return True
    average = sum(luminances) / len(luminances)
    spread = max(luminances) - min(luminances)
    # Near-uniform white/black/gray frames are treated as blank.
    if spread < 8.0 and (average > 245 or average < 12 or 118 < average < 138):
        return True
    # Extremely flat mid-gray also rejected.
    if spread < 4.0:
        return True
    return False


def load_preview_pixmap(path: Path | None):
    from PySide6.QtGui import QPixmap

    if path is None or not path.is_file():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap
