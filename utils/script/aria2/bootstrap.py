from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from deploy import curr_os
from utils.config import conf_dir
from utils.preset_assets import managed_asset_sources

ARIA2_MANIFEST_NAME = "aria2-manifest.json"
# Single aria2 home for every mode/OS (source tree, green package, win, mac).
ARIA2_DIRNAME = "cgs-aria2"
# The managed aria2c lives one level down so work files stay separate from payload.
ARIA2_BIN_DIRNAME = "bin"
ARIA2_CONF_NAME = "aria2.conf"
ARIA2_SESSION_NAME = "download.session"
ARIA2_PID_NAME = "engine.pid"
# Binary payload may be multi‑MB; keep a longer ceiling.
BINARY_DOWNLOAD_TIMEOUT_S = 120
# Manifest is tiny JSON. MUST NOT reuse binary timeout — a hung GitHub TCP
# with 120s would freeze Script preprocess for the binary ceiling when the
# manifest alone is unreadable.
MANIFEST_FETCH_TIMEOUT_S = 3
DOWNLOAD_CHUNK_SIZE = 8192
ARIA2_BINARY_PROGRESS_LABEL = "aria2"
# Optional comma-separated full URLs for manifest only (download sim / mirror).
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


@dataclass(frozen=True, slots=True)
class Aria2Layout:
    """The one filesystem layout for managed aria2 (conf_dir/cgs-aria2).

    Every consumer reads its paths from here, so "where does aria2 live" is
    answered in exactly one place: this object. Source tree, green package,
    Windows and macOS all resolve to the same shape.
    """

    work_dir: Path
    bin_dir: Path

    @property
    def binary_path(self) -> Path:
        return self.bin_dir.joinpath(curr_os.aira2_binary_name)

    @property
    def conf_path(self) -> Path:
        return self.work_dir.joinpath(ARIA2_CONF_NAME)

    @property
    def session_path(self) -> Path:
        return self.work_dir.joinpath(ARIA2_SESSION_NAME)

    @property
    def pid_path(self) -> Path:
        return self.work_dir.joinpath(ARIA2_PID_NAME)


def resolve_aria2_layout() -> Aria2Layout:
    """Pure path resolution — no platform probing, safe at import time."""
    aria2_root = conf_dir.joinpath(ARIA2_DIRNAME)
    return Aria2Layout(work_dir=aria2_root, bin_dir=aria2_root.joinpath(ARIA2_BIN_DIRNAME))


def verify_aria2_host_platform() -> str:
    """Return the host platform id, rejecting unsupported or mismatched hosts."""
    host_platform_id = detect_aira2_platform_id()
    declared_platform_id = getattr(curr_os, "aira2_platform_id", None)
    if declared_platform_id and declared_platform_id != host_platform_id:
        raise UnsupportedAria2PlatformError(
            f"curr_os.aira2_platform_id={declared_platform_id!r} does not match host {host_platform_id!r}"
        )
    return host_platform_id


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_preset_asset_sources(logical_name: str) -> list[dict[str, str]]:
    """Ordered download sources: GitHub preset primary, ImgBed ASSETS_FALLBACK secondary.

    Env ``CGS_ARIA2_PRESET_BASE`` may supply comma-separated absolute URLs that
    replace the default chain (download sim / offline mirror only).
    """
    env_bases = (os.environ.get(PRESET_BASE_ENV) or "").strip()
    if env_bases:
        sources: list[dict[str, str]] = []
        raw_parts = [part.strip() for part in env_bases.split(",") if part.strip()]
        for index, part in enumerate(raw_parts):
            # Absolute file URL, or base URL that still needs the logical name joined.
            if part.rstrip("/").endswith((".json", ".exe")) or part.endswith(logical_name):
                url = part
            else:
                url = f"{part.rstrip('/')}/{logical_name.lstrip('/')}"
            sources.append({"id": f"env-{index}", "url": url})
        return sources
    return [dict(item) for item in managed_asset_sources(logical_name)]


def _emit_progress_status(progress_callback, message: str) -> None:
    """Push a plain status line into AsyncTask tooltip (callable or __call__)."""
    if progress_callback is None:
        return
    if callable(progress_callback):
        progress_callback(message)


def _http_get_bytes(url: str, *, timeout_s: float = MANIFEST_FETCH_TIMEOUT_S) -> bytes:
    """Tiny metadata GET (manifest JSON). MUST stay whole-body; no AsyncTask progress (CGS011)."""
    request = urllib.request.Request(url, headers={"User-Agent": "ComicGUISpider-aira2-bootstrap"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read()


def _emit_legacy_download_start(progress_callback, *, label: str) -> None:
    progress_start = getattr(progress_callback, "download_start", None)
    if callable(progress_callback) and not callable(progress_start):
        progress_callback(f"{label} dling...")


def _download_url_to_path(url: str, staging_path: Path, *, progress_callback=None, label: str = ARIA2_BINARY_PROGRESS_LABEL) -> None:
    """Stream one HTTP GET into staging_path; optional AsyncTask-compatible progress hooks."""
    request = urllib.request.Request(url, headers={"User-Agent": "ComicGUISpider-aira2-bootstrap"})
    progress_reset = getattr(progress_callback, "download_reset", None)
    progress_start = getattr(progress_callback, "download_start", None)
    progress_advance = getattr(progress_callback, "download_advance", None)
    progress_finish = getattr(progress_callback, "download_finish", None)
    if callable(progress_reset):
        progress_reset(label=label)
    with urllib.request.urlopen(request, timeout=BINARY_DOWNLOAD_TIMEOUT_S) as response:
        total_header = (response.headers.get("Content-Length") or "").strip()
        # 0 = unknown size (no/invalid Content-Length). AsyncTaskProgressReporter
        # treats total_bytes <= 0 the same as missing length (byte-count mode).
        # Prefer 0 over None so naive int-only callbacks do not TypeError.
        total_bytes = int(total_header) if total_header.isdigit() else 0
        if callable(progress_start):
            progress_start(label=label, total_bytes=total_bytes)
        with staging_path.open("wb") as file_handle:
            while True:
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                file_handle.write(chunk)
                if callable(progress_advance):
                    progress_advance(len(chunk), label=label, total_bytes=total_bytes)
    if callable(progress_finish):
        progress_finish(label=label)


def fetch_aria2_manifest() -> dict[str, Any]:
    errors: list[str] = []
    for source in resolve_preset_asset_sources(ARIA2_MANIFEST_NAME):
        manifest_url = str(source.get("url") or "").strip()
        if not manifest_url:
            continue
        try:
            payload = _http_get_bytes(manifest_url)
            manifest = json.loads(payload.decode("utf-8"))
            if not isinstance(manifest, dict):
                raise Aria2BinaryBootstrapError(f"invalid manifest JSON at {manifest_url}")
            # Live source chain owns failover; ignore stale sources inside remote JSON.
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


def _ensure_executable(path: Path) -> None:
    if os.name == "nt":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@dataclass(frozen=True, slots=True)
class ManagedAria2Binary:
    """The managed aria2c payload and everything about its on-disk state.

    Owns "is it present", "does it match the manifest digest", and "install it".
    Callers hand over no paths: they ask this object, which answers against the
    layout it was built from.
    """

    layout: Aria2Layout

    @property
    def path(self) -> Path:
        return self.layout.binary_path

    def is_present(self) -> bool:
        """Cheap on-disk presence check. No hashing, no network, no chmod."""
        try:
            return self.path.stat().st_size > 0
        except OSError:
            return False

    def matches_manifest(self, expected_sha256: str) -> bool:
        if not self.is_present():
            return False
        return file_sha256(self.path) == expected_sha256.lower()

    def reuse_or_install(self, *, progress_callback=None, force_refresh: bool = False) -> Path:
        """Return the managed binary path, downloading only when it is absent.

        Local-first (critical for Script preprocess latency): an existing file is
        returned with **zero** network, so the second Script open never waits on
        the GitHub/ImgBed manifest. The manifest digest is enforced at download
        time; it is not re-verified on every start.
        """
        if not force_refresh and self.is_present():
            _ensure_executable(self.path)
            logger.debug(f"[CgsAria2] reusing local binary (skip network): {self.path}")
            return self.path

        platform_id = verify_aria2_host_platform()
        _emit_progress_status(progress_callback, f"{ARIA2_BINARY_PROGRESS_LABEL} checking...")
        try:
            manifest = fetch_aria2_manifest()
        except Aria2BinaryBootstrapError:
            if self.is_present():
                _ensure_executable(self.path)
                logger.warning(
                    f"[CgsAria2] preset manifest unavailable; reusing existing binary at {self.path}"
                )
                return self.path
            raise

        platform_entry = _platform_entry(manifest, platform_id)
        expected_sha256 = str(platform_entry["sha256"]).strip().lower()
        asset_name = str(platform_entry["name"]).strip()

        if self.matches_manifest(expected_sha256):
            _ensure_executable(self.path)
            return self.path

        self._download_asset(asset_name, expected_sha256, progress_callback=progress_callback)
        if not self.matches_manifest(expected_sha256):
            raise Aria2BinaryBootstrapError(f"post-download verify failed: {self.path}")
        return self.path

    def copy_from(self, source_binary: Path) -> Path:
        """Dev/CI helper: place a pre-fetched binary without touching the network."""
        if not source_binary.is_file():
            raise FileNotFoundError(source_binary)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_binary, self.path)
        _ensure_executable(self.path)
        return self.path

    def _download_asset(self, file_name: str, expected_sha256: str, *, progress_callback=None) -> None:
        target_path = self.path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path = target_path.with_suffix(target_path.suffix + ".part")
        errors: list[str] = []
        _emit_legacy_download_start(progress_callback, label=ARIA2_BINARY_PROGRESS_LABEL)
        for source in resolve_preset_asset_sources(file_name):
            asset_url = str(source.get("url") or "").strip()
            if not asset_url:
                continue
            try:
                _download_url_to_path(asset_url, staging_path, progress_callback=progress_callback)
                actual_sha256 = file_sha256(staging_path)
                if actual_sha256 != expected_sha256.lower():
                    staging_path.unlink(missing_ok=True)
                    raise Aria2BinaryBootstrapError(
                        f"sha256 mismatch for {file_name}: expected {expected_sha256}, got {actual_sha256}"
                    )
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


def ensure_aira2_binary(*, progress_callback=None, force_refresh: bool = False) -> Path:
    """Public entry: ensure the managed aria2c exists, downloading only if missing."""
    managed_binary = ManagedAria2Binary(resolve_aria2_layout())
    return managed_binary.reuse_or_install(progress_callback=progress_callback, force_refresh=force_refresh)


def copy_local_preset_asset_into_tree(source_binary: Path) -> Path:
    """Dev/CI helper: place a pre-fetched binary at conf_dir/cgs-aria2/bin without network."""
    return ManagedAria2Binary(resolve_aria2_layout()).copy_from(source_binary)
