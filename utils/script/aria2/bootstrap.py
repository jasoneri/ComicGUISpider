from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from loguru import logger

from deploy import curr_os

ARIA2_MANIFEST_NAME = "aria2-manifest.json"
SUPPORTED_PLATFORM_IDS = frozenset({"win-amd64", "macos-arm"})
DEFAULT_MANIFEST_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "id": "github",
        "priority": 10,
        "base_url": "https://github.com/jasoneri/ComicGUISpider/releases/download/preset",
    },
    {
        "id": "gitee",
        "priority": 20,
        "base_url": "https://gitee.com/json_eri/ComicGUISpider/releases/download/preset",
    },
)
DOWNLOAD_TIMEOUT_S = 120
# Optional comma-separated preset base URLs (download sim / mirror only; not a binary PATH fallback).
PRESET_BASE_ENV = "CGS_ARIA2_PRESET_BASE"


class UnsupportedAria2PlatformError(RuntimeError):
    """Host platform is outside v1 matrix (win-amd64, macos-arm only)."""


class Aria2BinaryBootstrapError(RuntimeError):
    """preset download or integrity check failed."""


def detect_aira2_platform_id() -> str:
    system_name = platform.system()
    machine_name = platform.machine().lower()
    if system_name == "Windows" and machine_name in ("amd64", "x86_64"):
        return "win-amd64"
    if system_name == "Darwin" and machine_name in ("arm64", "aarch64"):
        return "macos-arm"
    raise UnsupportedAria2PlatformError(
        f"CGS aria2 supports only win-amd64 and macos-arm; got system={system_name!r} machine={machine_name!r}"
    )


def aira2_install_dir() -> Path:
    return Path(curr_os.aira2).parent


def resolve_aira2_target_path() -> Path:
    return Path(curr_os.aira2)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_manifest_sources() -> list[dict[str, Any]]:
    env_bases = (os.environ.get(PRESET_BASE_ENV) or "").strip()
    if env_bases:
        sources: list[dict[str, Any]] = []
        base_urls = [part.strip() for part in env_bases.split(",") if part.strip()]
        for index, base_url in enumerate(base_urls):
            sources.append({"id": f"env-{index}", "priority": index + 1, "base_url": base_url})
        return sources
    return [dict(item) for item in DEFAULT_MANIFEST_SOURCES]


def _sorted_sources(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if manifest and manifest.get("sources"):
        sources = list(manifest["sources"])
    else:
        sources = default_manifest_sources()
    return sorted(sources, key=lambda item: int(item.get("priority") or 100))


def _join_preset_url(base_url: str, file_name: str) -> str:
    return f"{base_url.rstrip('/')}/{file_name.lstrip('/')}"


def _http_get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ComicGUISpider-aira2-bootstrap"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as response:
        return response.read()


def fetch_aria2_manifest() -> dict[str, Any]:
    errors: list[str] = []
    bootstrap_sources = default_manifest_sources()
    for source in _sorted_sources({"sources": bootstrap_sources}):
        base_url = str(source.get("base_url") or "").strip()
        if not base_url:
            continue
        manifest_url = _join_preset_url(base_url, ARIA2_MANIFEST_NAME)
        try:
            payload = _http_get_bytes(manifest_url)
            manifest = json.loads(payload.decode("utf-8"))
            if not isinstance(manifest, dict):
                raise Aria2BinaryBootstrapError(f"invalid manifest JSON at {manifest_url}")
            # Prefer live bootstrap sources (env / defaults) over stale absolute URLs inside manifest.
            manifest["sources"] = bootstrap_sources
            return manifest
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            errors.append(f"{source.get('id')}: {exc}")
            logger.warning(f"[CgsAria2] manifest fetch failed {manifest_url}: {exc}")
    raise Aria2BinaryBootstrapError(
        "failed to download aria2-manifest.json from preset sources: " + "; ".join(errors)
    )


def _platform_entry(manifest: dict[str, Any], platform_id: str) -> dict[str, Any]:
    platforms = manifest.get("platforms") or {}
    entry = platforms.get(platform_id)
    if not isinstance(entry, dict):
        raise Aria2BinaryBootstrapError(f"aria2-manifest.json missing platforms[{platform_id!r}]")
    file_name = str(entry.get("name") or "").strip()
    sha256_hex = str(entry.get("sha256") or "").strip().lower()
    if not file_name or not sha256_hex:
        raise Aria2BinaryBootstrapError(f"platforms[{platform_id!r}] requires name and sha256")
    return entry


def _download_asset_to(target_path: Path, file_name: str, expected_sha256: str, manifest: dict[str, Any]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = target_path.with_suffix(target_path.suffix + ".part")
    errors: list[str] = []
    for source in _sorted_sources(manifest):
        base_url = str(source.get("base_url") or "").strip()
        if not base_url:
            continue
        asset_url = _join_preset_url(base_url, file_name)
        try:
            payload = _http_get_bytes(asset_url)
            staging_path.write_bytes(payload)
            actual_sha256 = file_sha256(staging_path)
            if actual_sha256 != expected_sha256.lower():
                staging_path.unlink(missing_ok=True)
                raise Aria2BinaryBootstrapError(
                    f"sha256 mismatch for {file_name}: expected {expected_sha256}, got {actual_sha256}"
                )
            if target_path.exists():
                target_path.unlink()
            staging_path.replace(target_path)
            _ensure_executable(target_path)
            logger.info(f"[CgsAria2] installed binary from {source.get('id')} → {target_path}")
            return
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, Aria2BinaryBootstrapError) as exc:
            errors.append(f"{source.get('id')}: {exc}")
            staging_path.unlink(missing_ok=True)
            logger.warning(f"[CgsAria2] asset fetch failed {asset_url}: {exc}")
    raise Aria2BinaryBootstrapError(
        f"failed to download {file_name} from preset sources: " + "; ".join(errors)
    )


def _ensure_executable(path: Path) -> None:
    if os.name == "nt":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def local_binary_matches_manifest(target_path: Path, expected_sha256: str) -> bool:
    if not target_path.is_file():
        return False
    return file_sha256(target_path) == expected_sha256.lower()


def ensure_aira2_binary() -> Path:
    """Ensure curr_os.aira2 exists and matches preset manifest. No PATH/uv/runtime fallback.

    If preset network is unavailable but ``curr_os.aira2`` already exists (prior install),
    reuse that binary instead of failing closed on manifest 404.
    """
    platform_id = detect_aira2_platform_id()
    env_platform_id = getattr(curr_os, "aira2_platform_id", None)
    if env_platform_id and env_platform_id != platform_id:
        raise UnsupportedAria2PlatformError(
            f"curr_os.aira2_platform_id={env_platform_id!r} does not match host {platform_id!r}"
        )
    if platform_id not in SUPPORTED_PLATFORM_IDS:
        raise UnsupportedAria2PlatformError(f"unsupported platform_id={platform_id!r}")

    target_path = resolve_aira2_target_path()
    try:
        manifest = fetch_aria2_manifest()
    except Aria2BinaryBootstrapError:
        if target_path.is_file() and target_path.stat().st_size > 0:
            _ensure_executable(target_path)
            logger.warning(
                f"[CgsAria2] preset manifest unavailable; reusing existing binary at {target_path}"
            )
            return target_path
        raise

    platform_entry = _platform_entry(manifest, platform_id)
    expected_sha256 = str(platform_entry["sha256"]).strip().lower()
    asset_name = str(platform_entry["name"]).strip()

    if local_binary_matches_manifest(target_path, expected_sha256):
        _ensure_executable(target_path)
        return target_path

    _download_asset_to(target_path, asset_name, expected_sha256, manifest)
    if not local_binary_matches_manifest(target_path, expected_sha256):
        raise Aria2BinaryBootstrapError(f"post-download verify failed: {target_path}")
    return target_path


def copy_local_preset_asset_into_tree(source_binary: Path, *, platform_id: str | None = None) -> Path:
    """Dev/CI helper: place a pre-fetched binary at curr_os.aira2 without network (still no PATH)."""
    resolved_platform = platform_id or detect_aira2_platform_id()
    if resolved_platform not in SUPPORTED_PLATFORM_IDS:
        raise UnsupportedAria2PlatformError(resolved_platform)
    if not source_binary.is_file():
        raise FileNotFoundError(source_binary)
    target_path = resolve_aira2_target_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_binary, target_path)
    _ensure_executable(target_path)
    return target_path
