"""Resolve managed preset download URLs from variables constants (no Qt).

Primary: GitHub ``GITHUB_PRESET_BASE`` / logical name.
Fallback: ``ASSETS_FALLBACK`` / ``IMGBED_ASSET_OBJECTS[logical_name]`` when mapped.
"""
from __future__ import annotations

from variables import ASSETS_FALLBACK, GITHUB_PRESET_BASE, IMGBED_ASSET_OBJECTS


def github_preset_url(logical_name: str) -> str:
    return f"{GITHUB_PRESET_BASE.rstrip('/')}/{str(logical_name).lstrip('/')}"


def assets_fallback_url(logical_name: str) -> str | None:
    object_name = IMGBED_ASSET_OBJECTS.get(str(logical_name).strip())
    if not object_name:
        return None
    return f"{ASSETS_FALLBACK.rstrip('/')}/{str(object_name).lstrip('/')}"


def managed_asset_urls(logical_name: str) -> tuple[str, ...]:
    """Ordered download URLs: GitHub preset first, ImgBed assets fallback when mapped."""
    urls = [github_preset_url(logical_name)]
    fallback_url = assets_fallback_url(logical_name)
    if fallback_url:
        urls.append(fallback_url)
    return tuple(urls)


def managed_asset_sources(logical_name: str) -> tuple[dict[str, str], ...]:
    """Ordered (id, url) sources for bootstrap-style failover loops."""
    sources: list[dict[str, str]] = [{"id": "github", "url": github_preset_url(logical_name)}]
    fallback_url = assets_fallback_url(logical_name)
    if fallback_url:
        sources.append({"id": "imgbed", "url": fallback_url})
    return tuple(sources)
