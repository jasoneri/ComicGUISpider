from __future__ import annotations

import asyncio
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

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


def scan_png_files(root: str | Path) -> list[Path]:
    target_dir = normalize_path(root)
    if not target_dir.exists():
        raise FileNotFoundError(f"Cbg PNG directory does not exist: {target_dir}")
    if not target_dir.is_dir():
        raise NotADirectoryError(f"Cbg PNG path is not a directory: {target_dir}")
    return sorted(
        (
            path.resolve()
            for path in target_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".png"
        ),
        key=lambda path: str(path).lower(),
    )


def _resolve_bundle_path(root: Path, raw_path: object) -> Path:
    relative = PurePosixPath(str(raw_path).replace("\\", "/"))
    parts = tuple(part for part in relative.parts if part not in {"", "."})
    if not parts or any(part == ".." or part.endswith(":") for part in parts):
        raise ValueError("invalid relative path")
    target = root.joinpath(*parts).resolve()
    target.relative_to(root)
    return target


def _resolve_archive_name(raw_name: object) -> str:
    archive_name = PurePosixPath(str(raw_name).replace("\\", "/")).name.strip()
    if not archive_name or archive_name in {".", ".."}:
        raise ValueError("invalid archive name")
    if PurePosixPath(archive_name).suffix.lower() != ".7z":
        raise ValueError("archive name must end with .7z")
    return archive_name


def _extract_7z_archive(archive_path: Path, target_dir: Path) -> None:
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        archive.extractall(path=target_dir)


def _build_cbg_http_client_kwargs() -> dict:
    transport, trust_env = build_proxy_transport(
        "proxy",
        list(getattr(conf, "proxies", None) or []),
        is_async=True,
    )
    return {
        "transport": transport,
        "trust_env": trust_env,
    }


def _resolve_archive_size_bytes(raw_value: object) -> int:
    size_bytes = int(raw_value)
    if size_bytes <= 0:
        raise ValueError("archive sizeBytes must be positive")
    return size_bytes


def _format_progress_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.2f} MB"


async def _stream_archive_download(
    client: httpx.AsyncClient,
    archive_url: str,
    archive_path: Path,
    *,
    expected_size_bytes: int,
    progress_callback=None,
) -> None:
    bytes_downloaded = 0
    last_percent = -1
    last_progress_at = 0.0
    chunk_size = 64 * 1024

    async with client.stream("GET", archive_url) as archive_response:
        archive_response.raise_for_status()
        with archive_path.open("wb") as archive_file:
            async for chunk in archive_response.aiter_bytes(chunk_size):
                if not chunk:
                    continue
                archive_file.write(chunk)
                bytes_downloaded += len(chunk)
                if progress_callback is None:
                    continue
                percent = min(100, int(bytes_downloaded * 100 / expected_size_bytes))
                now = time.monotonic()
                if percent == last_percent and now - last_progress_at < 0.2:
                    continue
                last_percent = percent
                last_progress_at = now
                progress_callback(
                    f"downloading {percent}% ({_format_progress_bytes(bytes_downloaded)}/{_format_progress_bytes(expected_size_bytes)})"
                )

    if bytes_downloaded != expected_size_bytes:
        raise ValueError(
            f"archive size mismatch: expected {expected_size_bytes} bytes, got {bytes_downloaded}"
        )


async def import_cbg_api_bundle_async(
    api_url: str,
    output_root: str | Path,
    *,
    progress_callback=None,
) -> Path:
    target_root = normalize_path(output_root)
    target_root.mkdir(parents=True, exist_ok=True)

    if progress_callback is not None:
        progress_callback("read remote")

    async with httpx.AsyncClient(
        headers=CBG_API_HEADERS,
        follow_redirects=True,
        timeout=20.0,
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        **_build_cbg_http_client_kwargs(),
    ) as client:
        response = await client.get(str(api_url).strip())
        response.raise_for_status()
        payload = response.json()
        target_dir = _resolve_bundle_path(target_root, payload["path"])
        archive = payload["archive"]
        archive_name = _resolve_archive_name(archive["name"])
        archive_size_bytes = _resolve_archive_size_bytes(archive["sizeBytes"])
        archive_url = str(archive["url"]).strip()
        if not archive_url:
            raise ValueError("missing archive url")
        target_dir.mkdir(parents=True, exist_ok=True)
        if progress_callback is not None:
            progress_callback(f"downloading 0% (0 B/{_format_progress_bytes(archive_size_bytes)})")
        with tempfile.TemporaryDirectory(prefix="cbg-import-") as temp_dir:
            archive_path = Path(temp_dir).joinpath(archive_name)
            await _stream_archive_download(
                client,
                archive_url,
                archive_path,
                expected_size_bytes=archive_size_bytes,
                progress_callback=progress_callback,
            )
            if progress_callback is not None:
                progress_callback("extract")
            await asyncio.to_thread(_extract_7z_archive, archive_path, target_dir)

    return target_dir


def import_cbg_api_bundle(
    api_url: str,
    output_root: str | Path,
    *,
    progress_callback=None,
) -> Path:
    return asyncio.run(
        import_cbg_api_bundle_async(
            api_url,
            output_root,
            progress_callback=progress_callback,
        )
    )


def pick_random_paths(
    scan_paths: Iterable[str | Path],
    recorded_paths: Iterable[str | Path],
    target_count: int,
    include_recorded: bool,
    rng: random.Random | None = None,
) -> list[Path]:
    ordered_paths = unique_paths(scan_paths)
    if not ordered_paths:
        return []

    count = int(target_count)
    if count <= 0:
        return []
    if len(ordered_paths) < count:
        return ordered_paths

    pool = ordered_paths
    if not include_recorded:
        recorded_set = set(unique_paths(recorded_paths))
        fresh_paths = [path for path in ordered_paths if path not in recorded_set]
        if len(fresh_paths) >= count:
            pool = fresh_paths

    randomizer = rng or random
    selected_set = set(randomizer.sample(pool, count))
    return [path for path in ordered_paths if path in selected_set]


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
