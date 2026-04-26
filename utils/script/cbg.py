from __future__ import annotations

import asyncio
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

import httpx
import py7zr

from utils import conf
from utils.website.core import build_proxy_transport

RESOURCE_PLACEHOLDER = "{resource-placehold}"
ALLOWED_RANDOM_COUNTS = (5, 10, 15, 20)
CBG_API_HEADERS = {"x-cgs-cbg-flag": "cgs.cbgFlagHea"}


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def unique_paths(paths: Iterable[str | Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = normalize_path(raw_path)
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def canonicalize_random_count(value: object, default: int = 10) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(ALLOWED_RANDOM_COUNTS, key=lambda item: (abs(item - number), item))


ProgressCallback = Callable[[str], None] | None


@dataclass(frozen=True, slots=True)
class _CbgApiBundle:
    target_dir: Path
    archive_name: str
    archive_url: str
    archive_size_bytes: int

    @classmethod
    def from_payload(cls, target_root: Path, payload: object) -> _CbgApiBundle:
        if not isinstance(payload, dict):
            raise TypeError("cbg api payload must be an object")

        relative = PurePosixPath(str(payload["path"]).replace("\\", "/"))
        parts = tuple(part for part in relative.parts if part not in {"", "."})
        if not parts or any(part == ".." or part.endswith(":") for part in parts):
            raise ValueError("invalid relative path")

        archive = payload["archive"]
        if not isinstance(archive, dict):
            raise TypeError("cbg api archive payload must be an object")
        archive_name = PurePosixPath(str(archive["name"]).replace("\\", "/")).name.strip()
        if not archive_name or archive_name in {".", ".."}:
            raise ValueError("invalid archive name")
        if PurePosixPath(archive_name).suffix.lower() != ".7z":
            raise ValueError("archive name must end with .7z")

        archive_size_bytes = int(archive["sizeBytes"])
        if archive_size_bytes <= 0:
            raise ValueError("archive sizeBytes must be positive")

        archive_url = str(archive["url"]).strip()
        if not archive_url:
            raise ValueError("missing archive url")

        target_dir = target_root.joinpath(*parts).resolve()
        target_dir.relative_to(target_root)
        return cls(target_dir=target_dir, archive_name=archive_name, archive_url=archive_url, archive_size_bytes=archive_size_bytes)


class _CbgApiImportSession:
    bundle: _CbgApiBundle
    archive_path: Path

    def __init__(self, api_url: str, output_root: str | Path, *, progress_callback: ProgressCallback = None) -> None:
        self.api_url = str(api_url).strip()
        self.target_root = normalize_path(output_root)
        self.target_root.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback
        self.bytes_downloaded = 0
        self.last_percent = -1
        self.last_progress_at = 0.0

    async def run(self) -> Path:
        if self.progress_callback is not None:
            self.progress_callback("read remote")

        transport, trust_env = build_proxy_transport("proxy", list(getattr(conf, "proxies", None) or []), is_async=True)
        async with httpx.AsyncClient(
            headers=CBG_API_HEADERS,
            follow_redirects=True,
            timeout=20.0,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
            transport=transport,
            trust_env=trust_env,
        ) as client:
            response = await client.get(self.api_url)
            response.raise_for_status()
            self.bundle = _CbgApiBundle.from_payload(self.target_root, response.json())
            self.bundle.target_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(prefix="cbg-import-") as temp_dir:
                self.archive_path = Path(temp_dir).joinpath(self.bundle.archive_name)
                await self._download_archive(client)
                if self.progress_callback is not None:
                    self.progress_callback("extract")
                await self._extract_archive()
        return self.bundle.target_dir

    async def _download_archive(self, client: httpx.AsyncClient) -> None:
        self.bytes_downloaded = 0
        self.last_percent = -1
        self.last_progress_at = 0.0

        if self.progress_callback is not None:
            self.progress_callback(f"downloading 0% (0 B/{self._format_progress_bytes(self.bundle.archive_size_bytes)})")

        async with client.stream("GET", self.bundle.archive_url) as archive_response:
            archive_response.raise_for_status()
            with self.archive_path.open("wb") as archive_file:
                async for chunk in archive_response.aiter_bytes(64 * 1024):
                    if not chunk:
                        continue
                    archive_file.write(chunk)
                    self.bytes_downloaded += len(chunk)
                    self._report_download_progress()

        if self.bytes_downloaded != self.bundle.archive_size_bytes:
            raise ValueError(f"archive size mismatch: expected {self.bundle.archive_size_bytes} bytes, got {self.bytes_downloaded}")

    def _report_download_progress(self) -> None:
        if self.progress_callback is None:
            return
        percent = min(100, int(self.bytes_downloaded * 100 / self.bundle.archive_size_bytes))
        now = time.monotonic()
        if percent == self.last_percent and now - self.last_progress_at < 0.2:
            return
        self.last_percent = percent
        self.last_progress_at = now
        self.progress_callback(
            f"downloading {percent}% "
            f"({self._format_progress_bytes(self.bytes_downloaded)}/{self._format_progress_bytes(self.bundle.archive_size_bytes)})"
        )

    async def _extract_archive(self) -> None:
        def extract_archive() -> None:
            with py7zr.SevenZipFile(self.archive_path, mode="r") as archive:
                archive.extractall(path=self.bundle.target_dir)

        await asyncio.to_thread(extract_archive)

    @staticmethod
    def _format_progress_bytes(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / 1024 / 1024:.2f} MB"


async def import_cbg_api_bundle_async(api_url: str, output_root: str | Path, *, progress_callback: ProgressCallback = None) -> Path:
    return await _CbgApiImportSession(api_url, output_root, progress_callback=progress_callback).run()


def import_cbg_api_bundle(api_url: str, output_root: str | Path, *, progress_callback: ProgressCallback = None) -> Path:
    return asyncio.run(import_cbg_api_bundle_async(api_url, output_root, progress_callback=progress_callback))



@dataclass(frozen=True, slots=True)
class CbgResource:
    path: Path
    resource_name: str

    def to_userscript_line(self) -> str:
        return f"// @resource     {self.resource_name:<12} {self.path.resolve().as_uri()}"


class ResourceNameBuilder:
    def __init__(self) -> None:
        self._used: set[str] = set()

    def build(self, path: Path) -> str:
        parts = [path.parent.name, path.stem]
        name = "_".join(part for part in parts if part).lower()
        name = re.sub(r"[^0-9a-zA-Z_]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name:
            name = "img"
        if not name.startswith("img_"):
            name = f"img_{name}"

        base = name
        index = 2
        while name in self._used:
            name = f"{base}_{index}"
            index += 1
        self._used.add(name)
        return name


def build_resources(paths: Iterable[str | Path]) -> list[CbgResource]:
    builder = ResourceNameBuilder()
    return [CbgResource(path=path, resource_name=builder.build(path)) for path in unique_paths(paths)]


def build_userscript(selected_paths: Iterable[str | Path], template_text: str) -> str:
    if RESOURCE_PLACEHOLDER not in template_text:
        raise ValueError("Cbg userscript template is missing resource placeholder")
    resource_lines = "\n".join(resource.to_userscript_line() for resource in build_resources(selected_paths))
    return template_text.replace(RESOURCE_PLACEHOLDER, resource_lines)


# Cohesive boundary classes for GUI imports
class Api:
    @staticmethod
    def import_bundle(api_url: str, output_root: str | Path, *, progress_callback: ProgressCallback = None) -> Path:
        return import_cbg_api_bundle(api_url, output_root, progress_callback=progress_callback)

    @staticmethod
    async def import_bundle_async(api_url: str, output_root: str | Path, *, progress_callback: ProgressCallback = None) -> Path:
        return await import_cbg_api_bundle_async(api_url, output_root, progress_callback=progress_callback)


class ScriptMgr:
    """Userscript generation manager with stateful workflow"""

    ALLOWED_RANDOM_COUNTS = ALLOWED_RANDOM_COUNTS
    canonicalize_random_count = staticmethod(canonicalize_random_count)

    def __init__(self, template_text: str):
        self.template_text = template_text
        self.selected_paths: list[Path] = []

    def set_selected_paths(self, paths: Iterable[str | Path]) -> None:
        """Set the paths to be included in the userscript"""
        self.selected_paths = unique_paths(paths)

    def build_userscript(self) -> str:
        """Build userscript from current selected paths"""
        if not self.selected_paths:
            raise ValueError("No paths selected for userscript generation")
        return build_userscript(self.selected_paths, self.template_text)


class StaticMgr:
    """Static file path manager with scan state"""

    normalize_path = staticmethod(normalize_path)

    def __init__(self, scan_root: str | Path | None = None):
        self.scan_root: Path | None = normalize_path(scan_root) if scan_root else None
        self.scanned_paths: list[Path] = []
        self.recorded_paths: list[Path] = []

    def set_scan_root(self, root: str | Path) -> None:
        """Set and validate the scan root directory"""
        self.scan_root = normalize_path(root)

    def scan_files(self) -> list[Path]:
        """Scan PNG files from the current scan root"""
        if self.scan_root is None:
            raise ValueError("scan root is not set")
        if not self.scan_root.exists():
            raise FileNotFoundError(f"Cbg PNG directory does not exist: {self.scan_root}")
        if not self.scan_root.is_dir():
            raise NotADirectoryError(f"Cbg PNG path is not a directory: {self.scan_root}")

        self.scanned_paths = sorted(
            (
                path.resolve()
                for path in self.scan_root.rglob("*")
                if path.is_file() and path.suffix.lower() == ".png"
            ),
            key=lambda path: str(path).lower(),
        )
        return self.scanned_paths

    def set_recorded_paths(self, paths: Iterable[str | Path]) -> None:
        """Set the historically recorded paths"""
        self.recorded_paths = unique_paths(paths)

    def pick_random(self, target_count: int, include_recorded: bool, rng: random.Random | None = None) -> list[Path]:
        """Pick random paths from scanned results"""
        ordered_paths = self.scanned_paths
        if not ordered_paths:
            return []
        count = int(target_count)
        if count <= 0:
            return []
        if len(ordered_paths) <= count:
            return ordered_paths

        pool = ordered_paths
        if not include_recorded:
            recorded_set = set(self.recorded_paths)
            fresh_paths = [path for path in ordered_paths if path not in recorded_set]
            if len(fresh_paths) >= count:
                pool = fresh_paths

        randomizer = rng or random
        selected_set = set(randomizer.sample(pool, count))
        return [path for path in ordered_paths if path in selected_set]
