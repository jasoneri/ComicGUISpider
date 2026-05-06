from __future__ import annotations

import logging
import math
import secrets
import tempfile
import threading
import typing as t
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PySide6 import QtCore

from utils.network.socket_errors import is_client_disconnect_error
from utils.script.image.danbooru.client import DanbooruClient
from utils.script.image.danbooru.http import DanbooruChallengeRequired
from utils.script.image.danbooru.models import DanbooruPost

_LOG = logging.getLogger(__name__)
_PROXY_PATH_PREFIX = "/player/video/"
_STREAM_TIMEOUT = 90.0
_STREAM_CHUNK_SIZE = 64 * 1024
_SEGMENT_COUNT = 3
_FIRST_SEGMENT_FALLBACK_BYTES = 2 * 1024 * 1024
_TAIL_METADATA_WINDOW_BYTES = 512 * 1024
_DEFAULT_CONTENT_TYPE = "application/octet-stream"
_RANGE_PROBE_HEADER = "bytes=0-0"


@dataclass(frozen=True, slots=True)
class VideoCacheProgress:
    post_id: int
    cached_bytes: int
    total_bytes: int
    active_segment_index: int
    ready_to_play: bool
    complete: bool

    @property
    def cached_ratio(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return max(0.0, min(1.0, self.cached_bytes / self.total_bytes))


@dataclass(frozen=True, slots=True)
class _VideoRoute:
    post_id: int
    source_url: str
    cache: "_CacheSession"


class _ClientDisconnected(Exception):
    pass


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DanbooruVideoProxy/1.0"

    def do_GET(self):
        self.server.proxy.handle_http_request(self, include_body=True)

    def do_HEAD(self):
        self.server.proxy.handle_http_request(self, include_body=False)

    def log_message(self, _format: str, *_args):
        return


class _ProxyServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], proxy: "VideoProxy"):
        self.proxy = proxy
        super().__init__(server_address, _ProxyHandler)


class _CacheSession:
    def __init__(self, *, post_id: int, source_url: str, request_client: DanbooruClient):
        self.post_id = int(post_id)
        self.source_url = str(source_url)
        self._request_client = request_client
        self._condition = threading.Condition()
        self._closed = False
        self._complete = False
        self._error: BaseException | None = None
        self._content_type = _DEFAULT_CONTENT_TYPE
        self._total_bytes = 0
        self._cached_bytes = 0
        self._cached_ranges: list[tuple[int, int]] = []
        self._metadata_required_ranges: list[tuple[int, int]] = []
        self._ready_to_play = False
        self._last_emitted: VideoCacheProgress | None = None
        cache_file = tempfile.NamedTemporaryFile(prefix=f"danbooru-video-{self.post_id}-", suffix=".cache", delete=False)
        self._cache_path = Path(cache_file.name)
        cache_file.close()
        self._thread = threading.Thread(target=self._download_loop, name=f"DanbooruVideoCache-{self.post_id}", daemon=True)
        self._thread.start()

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._thread.join(timeout=2.0)
        try:
            self._cache_path.unlink(missing_ok=True)
        except OSError:
            _LOG.debug("failed to remove Danbooru video cache file %s", self._cache_path, exc_info=True)

    def progress(self) -> VideoCacheProgress:
        with self._condition:
            return self._progress_locked()

    def next_progress_event(self) -> VideoCacheProgress | None:
        with self._condition:
            progress = self._progress_locked()
            if progress == self._last_emitted:
                return None
            self._last_emitted = progress
            return progress

    def wait_until_ready(self, *, timeout: float = 30.0) -> bool:
        with self._condition:
            return self._condition.wait_for(lambda: self._closed or self._ready_to_play or self._error is not None, timeout=timeout)

    def wait_until_described(self, *, timeout: float = 30.0) -> bool:
        with self._condition:
            return self._condition.wait_for(
                lambda: self._closed or self._error is not None or self._total_bytes > 0 or self._complete,
                timeout=timeout,
            )

    def describe(self) -> tuple[int, str]:
        with self._condition:
            if self._error is not None:
                raise self._error
            return self._total_bytes, self._content_type

    def wait_for_range(self, start: int, end: int, *, timeout: float = _STREAM_TIMEOUT) -> bool:
        expected_start = max(0, int(start))
        expected_end = max(expected_start, int(end))
        with self._condition:
            return self._condition.wait_for(
                lambda: self._closed
                or self._error is not None
                or self._complete
                or self._is_range_cached_locked(expected_start, expected_end + 1),
                timeout=timeout,
            )

    def read_range(self, start: int, end: int) -> bytes:
        request_start = max(0, int(start))
        request_end = max(request_start, int(end))
        with self._condition:
            if self._error is not None:
                raise self._error
            available_end_exclusive = min(request_end + 1, self._covered_end_for_offset_locked(request_start))
            if available_end_exclusive <= request_start:
                return b""
        with self._cache_path.open("rb") as handle:
            handle.seek(request_start)
            return handle.read(available_end_exclusive - request_start)

    def _download_loop(self):
        try:
            self._probe_metadata()
            with self._condition:
                total_bytes = self._total_bytes
            if total_bytes > 0:
                self._download_range_segments(total_bytes)
            else:
                self._download_full_stream()
        except BaseException as exc:
            with self._condition:
                self._error = exc
                self._condition.notify_all()

    def _probe_metadata(self):
        try:
            headers = {"Accept": "*/*"}
            with self._request_client.stream_remote(self.source_url, method="HEAD", headers=headers, timeout=_STREAM_TIMEOUT) as response:
                self._apply_response_metadata(response)
                return
        except httpx.HTTPStatusError as exc:
            status_code = int(exc.response.status_code) if exc.response is not None else 0
            if status_code != int(HTTPStatus.METHOD_NOT_ALLOWED):
                raise
        self._probe_range_metadata()

    def _probe_range_metadata(self):
        with self._request_client.stream_remote(
            self.source_url, method="GET", headers={"Accept": "*/*", "Range": _RANGE_PROBE_HEADER}, timeout=_STREAM_TIMEOUT,
        ) as response:
            total_bytes = self._resolve_total_bytes(response)
            if total_bytes <= 0:
                self._download_response_body(response, start=0, total_bytes=0, complete_when_done=True)
                return
            self._apply_response_metadata(response, total_bytes=total_bytes)
            if int(response.status_code) == int(HTTPStatus.PARTIAL_CONTENT):
                self._download_response_body(response, start=0, total_bytes=total_bytes, complete_when_done=False)
                return
            self._download_response_body(response, start=0, total_bytes=total_bytes, complete_when_done=True)

    def _download_range_segments(self, total_bytes: int):
        for start, end in self._priority_ranges(total_bytes):
            with self._condition:
                if self._closed:
                    return
                if self._complete:
                    return
                if self._is_range_cached_locked(start, end + 1):
                    continue
            with self._request_client.stream_remote(
                self.source_url, method="GET", headers={"Accept": "*/*", "Range": f"bytes={start}-{end}"}, timeout=_STREAM_TIMEOUT,
            ) as response:
                if int(response.status_code) != int(HTTPStatus.PARTIAL_CONTENT):
                    self._download_response_body(response, start=0, total_bytes=total_bytes, complete_when_done=True)
                    return
                self._apply_response_metadata(response, total_bytes=total_bytes)
                self._download_response_body(response, start=start, total_bytes=total_bytes, complete_when_done=False)
        with self._condition:
            fully_cached = self._is_range_cached_locked(0, total_bytes)
        if fully_cached:
            self._mark_complete(total_bytes, total_bytes=total_bytes)

    def _download_full_stream(self):
        headers = {"Accept": "*/*"}
        with self._request_client.stream_remote(self.source_url, method="GET", headers=headers, timeout=_STREAM_TIMEOUT) as response:
            total_bytes = self._resolve_total_bytes(response)
            self._apply_response_metadata(response, total_bytes=total_bytes)
            self._download_response_body(response, start=0, total_bytes=total_bytes, complete_when_done=True)

    def _download_response_body(self, response, *, start: int, total_bytes: int, complete_when_done: bool):
        offset = int(start)
        with self._cache_path.open("r+b") as handle:
            if total_bytes > 0:
                handle.truncate(total_bytes)
            for chunk in response.iter_bytes(chunk_size=_STREAM_CHUNK_SIZE):
                if not chunk:
                    continue
                with self._condition:
                    if self._closed:
                        return
                chunk_start = offset
                handle.seek(offset)
                handle.write(chunk)
                handle.flush()
                offset += len(chunk)
                self._mark_cached_range(chunk_start, offset)
        if complete_when_done:
            self._mark_complete(offset, total_bytes=total_bytes)

    def _apply_response_metadata(self, response, *, total_bytes: int | None = None):
        resolved_total = self._resolve_total_bytes(response) if total_bytes is None else int(total_bytes)
        content_type = response.headers.get("content-type") or _DEFAULT_CONTENT_TYPE
        with self._condition:
            if resolved_total > 0:
                self._total_bytes = resolved_total
                self._metadata_required_ranges = self._build_metadata_required_ranges_locked(resolved_total)
                self._ready_to_play = self._is_ready_to_play_locked()
            self._content_type = content_type
            self._condition.notify_all()

    def _mark_cached_range(self, start: int, end_exclusive: int):
        with self._condition:
            self._add_cached_range_locked(int(start), int(end_exclusive))
            self._ready_to_play = self._is_ready_to_play_locked()
            self._condition.notify_all()

    def _mark_complete(self, offset: int, *, total_bytes: int):
        with self._condition:
            resolved_total = int(total_bytes) if int(total_bytes) > 0 else int(offset)
            if self._total_bytes <= 0 and resolved_total > 0:
                self._total_bytes = resolved_total
                self._metadata_required_ranges = self._build_metadata_required_ranges_locked(self._total_bytes)
            if self._total_bytes > 0:
                self._complete = self._is_range_cached_locked(0, self._total_bytes)
            else:
                self._complete = True
            self._ready_to_play = self._is_ready_to_play_locked()
            self._condition.notify_all()

    def _progress_locked(self) -> VideoCacheProgress:
        return VideoCacheProgress(
            post_id=self.post_id, cached_bytes=self._cached_bytes, total_bytes=self._total_bytes,
            active_segment_index=self._active_segment_index_locked(), ready_to_play=self._ready_to_play, complete=self._complete,
        )

    def _startup_threshold_locked(self) -> int:
        if self._total_bytes > 0:
            return max(1, math.ceil(self._total_bytes / _SEGMENT_COUNT))
        return _FIRST_SEGMENT_FALLBACK_BYTES

    def _active_segment_index_locked(self) -> int:
        if self._total_bytes <= 0:
            return 0
        segment_size = max(1, math.ceil(self._total_bytes / _SEGMENT_COUNT))
        front_cached_bytes = self._front_cached_bytes_locked()
        if front_cached_bytes <= 0:
            return 0
        return min(_SEGMENT_COUNT - 1, max(0, (front_cached_bytes - 1) // segment_size))

    def _priority_ranges(self, total_bytes: int) -> list[tuple[int, int]]:
        segment_size = max(1, math.ceil(total_bytes / _SEGMENT_COUNT))
        ranges: list[tuple[int, int]] = []
        startup_end = min(total_bytes, self._startup_threshold_locked())
        if startup_end > 0:
            ranges.append((0, startup_end - 1))
        with self._condition:
            metadata_ranges = list(self._metadata_required_ranges or self._build_metadata_required_ranges_locked(total_bytes))
        ranges.extend((start, end - 1) for start, end in metadata_ranges)
        for start in range(0, total_bytes, segment_size):
            end_exclusive = min(total_bytes, start + segment_size)
            ranges.append((start, end_exclusive - 1))
        return self._dedupe_ranges(ranges)

    def _add_cached_range_locked(self, start: int, end_exclusive: int):
        if end_exclusive <= start:
            return
        normalized_start = max(0, int(start))
        normalized_end = int(end_exclusive)
        if self._total_bytes > 0:
            normalized_end = min(normalized_end, self._total_bytes)
        if normalized_end <= normalized_start:
            return
        merged: list[tuple[int, int]] = []
        left = normalized_start
        right = normalized_end
        inserted = False
        for current_start, current_end in self._cached_ranges:
            if current_end < left:
                merged.append((current_start, current_end))
                continue
            if right < current_start:
                if not inserted:
                    merged.append((left, right))
                    inserted = True
                merged.append((current_start, current_end))
                continue
            left = min(left, current_start)
            right = max(right, current_end)
        if not inserted:
            merged.append((left, right))
        self._cached_ranges = merged
        self._cached_bytes = sum(max(0, range_end - range_start) for range_start, range_end in self._cached_ranges)
        if self._total_bytes > 0:
            self._cached_bytes = min(self._cached_bytes, self._total_bytes)

    def _is_range_cached_locked(self, start: int, end_exclusive: int) -> bool:
        if end_exclusive <= start:
            return True
        target_start = max(0, int(start))
        target_end = int(end_exclusive)
        for current_start, current_end in self._cached_ranges:
            if current_end <= target_start:
                continue
            if current_start > target_start:
                return False
            return current_end >= target_end
        return False

    def _covered_end_for_offset_locked(self, offset: int) -> int:
        normalized_offset = max(0, int(offset))
        for current_start, current_end in self._cached_ranges:
            if current_end <= normalized_offset:
                continue
            if current_start > normalized_offset:
                return normalized_offset
            return current_end
        return normalized_offset

    def _front_cached_bytes_locked(self) -> int:
        if not self._cached_ranges:
            return 0
        first_start, first_end = self._cached_ranges[0]
        if first_start > 0:
            return 0
        return max(0, first_end)

    def _build_metadata_required_ranges_locked(self, total_bytes: int) -> list[tuple[int, int]]:
        if total_bytes <= 0:
            return []
        threshold = self._startup_threshold_locked()
        tail_window = min(total_bytes, max(1, _TAIL_METADATA_WINDOW_BYTES))
        tail_start = max(0, total_bytes - tail_window)
        if tail_start < threshold:
            tail_start = threshold
        if tail_start >= total_bytes:
            return []
        return [(tail_start, total_bytes)]

    def _is_ready_to_play_locked(self) -> bool:
        if self._total_bytes <= 0:
            return self._complete
        startup_threshold = self._startup_threshold_locked()
        if not self._is_range_cached_locked(0, startup_threshold):
            return False
        for metadata_start, metadata_end in self._metadata_required_ranges:
            if not self._is_range_cached_locked(metadata_start, metadata_end):
                return False
        return True

    @staticmethod
    def _dedupe_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        deduped: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for start, end in ranges:
            normalized_start = max(0, int(start))
            normalized_end = int(end)
            if normalized_end < normalized_start:
                continue
            key = (normalized_start, normalized_end)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped

    @staticmethod
    def _resolve_total_bytes(response) -> int:
        content_range = str(response.headers.get("content-range") or "")
        if "/" in content_range:
            tail = content_range.rsplit("/", 1)[-1].strip()
            if tail.isdigit():
                return int(tail)
        content_length = str(response.headers.get("content-length") or "").strip()
        return int(content_length) if content_length.isdigit() else 0


class VideoProxy(QtCore.QObject):
    challenge_detected = QtCore.Signal(int, object)
    request_failed = QtCore.Signal(int, str)
    cache_progress = QtCore.Signal(object)
    cache_ready = QtCore.Signal(int)

    def __init__(self, request_client: DanbooruClient, parent: t.Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._request_client = request_client
        self._lock = threading.Lock()
        self._closed = False
        self._routes: dict[str, _VideoRoute] = {}
        self._post_tokens: dict[int, str] = {}
        self._ready_post_ids: set[int] = set()
        self._server = _ProxyServer(("127.0.0.1", 0), self)
        self._thread = threading.Thread(target=self._server.serve_forever, name="DanbooruVideoProxy", daemon=True)
        self._progress_thread = threading.Thread(target=self._progress_loop, name="VideoCacheProgress", daemon=True)
        self._thread.start()
        self._progress_thread.start()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            routes = list(self._routes.values())
            self._routes.clear()
            self._post_tokens.clear()
            self._ready_post_ids.clear()
        for route in routes:
            route.cache.close()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)
        self._progress_thread.join(timeout=2.0)

    def register_post(self, post: DanbooruPost) -> str:
        source_url = post.large_file_url or post.file_url or post.preview_file_url
        if not source_url:
            raise ValueError(f"Danbooru video source url is required: post_id={post.post_id}")
        with self._lock:
            self._ensure_open()
            token = self._post_tokens.get(post.post_id)
            route = self._routes.get(token) if token is not None else None
            if route is not None and route.source_url == source_url:
                return self._build_local_url(token)
            if route is not None:
                route.cache.close()
                self._ready_post_ids.discard(route.post_id)
            if token is not None:
                self._routes.pop(token, None)
            token = secrets.token_urlsafe(24)
            cache = _CacheSession(post_id=post.post_id, source_url=source_url, request_client=self._request_client)
            self._post_tokens[post.post_id] = token
            self._routes[token] = _VideoRoute(post_id=post.post_id, source_url=source_url, cache=cache)
            return self._build_local_url(token)

    def progress_for_post(self, post_id: int) -> VideoCacheProgress | None:
        with self._lock:
            token = self._post_tokens.get(int(post_id))
            route = self._routes.get(token) if token is not None else None
        return None if route is None else route.cache.progress()

    def handle_http_request(self, handler: _ProxyHandler, *, include_body: bool):
        route = self._route_for_path(handler.path)
        if route is None:
            self._send_error_response(handler, HTTPStatus.NOT_FOUND, "unknown Danbooru video token")
            return
        try:
            if include_body:
                if not route.cache.wait_until_ready():
                    raise TimeoutError(f"Danbooru video cache was not ready within 30s: post_id={route.post_id}")
            elif not route.cache.wait_until_described():
                raise TimeoutError(f"Danbooru video metadata was not available within 30s: post_id={route.post_id}")
            total_bytes, content_type = route.cache.describe()
            range_header = str(handler.headers.get("Range") or "").strip()
            try:
                start, end, status = self._resolve_response_range(range_header, total_bytes)
            except IndexError as exc:
                self._send_range_not_satisfiable_response(handler, total_bytes, str(exc))
                return
            self._send_cache_response_headers(handler, status, start, end, total_bytes, content_type)
            if include_body:
                self._forward_cache_range(handler, route.cache, start, end)
        except DanbooruChallengeRequired as exc:
            self.challenge_detected.emit(route.post_id, exc)
            try:
                self._send_error_response(handler, HTTPStatus.BAD_GATEWAY, str(exc))
            except _ClientDisconnected:
                return
        except _ClientDisconnected:
            return
        except OSError as exc:
            if str(exc).strip():
                self.request_failed.emit(route.post_id, str(exc))
            return
        except Exception as exc:
            self.request_failed.emit(route.post_id, str(exc))
            try:
                self._send_error_response(handler, HTTPStatus.BAD_GATEWAY, str(exc))
            except _ClientDisconnected:
                return
            _LOG.exception("Danbooru video proxy request failed post_id=%s source_url=%s", route.post_id, route.source_url)

    def _progress_loop(self):
        while True:
            with self._lock:
                if self._closed:
                    return
                routes = list(self._routes.values())
            for route in routes:
                progress = route.cache.next_progress_event()
                if progress is None:
                    continue
                self.cache_progress.emit(progress)
                if progress.ready_to_play and progress.post_id not in self._ready_post_ids:
                    self._ready_post_ids.add(progress.post_id)
                    self.cache_ready.emit(progress.post_id)
            QtCore.QThread.msleep(120)

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("Danbooru video proxy is already closed")

    def _build_local_url(self, token: str) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}{_PROXY_PATH_PREFIX}{token}"

    def _route_for_path(self, raw_path: str) -> t.Optional[_VideoRoute]:
        path = urlsplit(str(raw_path or "")).path
        if not path.startswith(_PROXY_PATH_PREFIX):
            return None
        token = path.removeprefix(_PROXY_PATH_PREFIX).strip("/")
        if not token:
            return None
        with self._lock:
            return self._routes.get(token)

    @staticmethod
    def _resolve_response_range(range_header: str, total_bytes: int) -> tuple[int, int, HTTPStatus]:
        if total_bytes <= 0:
            return 0, 0, HTTPStatus.OK
        if not range_header:
            return 0, total_bytes - 1, HTTPStatus.OK
        if not range_header.lower().startswith("bytes="):
            raise ValueError(f"unsupported range header: {range_header}")
        raw_range = range_header.split("=", 1)[1].split(",", 1)[0].strip()
        start_raw, _, end_raw = raw_range.partition("-")
        if start_raw:
            start = int(start_raw)
            end = int(end_raw) if end_raw else total_bytes - 1
        else:
            suffix_size = int(end_raw)
            start = max(0, total_bytes - suffix_size)
            end = total_bytes - 1
        if start < 0 or start >= total_bytes or end < start:
            raise IndexError(f"range not satisfiable: {range_header}")
        return start, min(end, total_bytes - 1), HTTPStatus.PARTIAL_CONTENT

    def _send_range_not_satisfiable_response(self, handler: _ProxyHandler, total_bytes: int, message: str):
        payload = str(message or HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE.phrase).encode("utf-8", "replace")
        handler.send_response(int(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE))
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Range", f"bytes */{max(0, total_bytes)}")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        if handler.command != "HEAD":
            self._write_response_payload(handler, payload)

    def _send_error_response(self, handler: _ProxyHandler, status: HTTPStatus, message: str):
        payload = str(message or status.phrase).encode("utf-8", "replace")
        handler.send_response(int(status))
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        if handler.command == "HEAD":
            return
        self._write_response_payload(handler, payload)

    def _write_response_payload(self, handler: _ProxyHandler, payload: bytes):
        try:
            handler.wfile.write(payload)
            handler.wfile.flush()
        except OSError as exc:
            if self._is_client_disconnect(exc):
                raise _ClientDisconnected() from exc
            raise

    @staticmethod
    def _send_cache_response_headers(
        handler: _ProxyHandler,
        status: HTTPStatus,
        start: int,
        end: int,
        total_bytes: int,
        content_type: str,
    ):
        content_length = max(0, end - start + 1) if total_bytes > 0 else 0
        handler.send_response(int(status))
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Type", content_type or _DEFAULT_CONTENT_TYPE)
        handler.send_header("Content-Length", str(content_length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{total_bytes}")
        handler.send_header("Connection", "close")
        handler.end_headers()

    def _forward_cache_range(self, handler: _ProxyHandler, cache: _CacheSession, start: int, end: int):
        offset = start
        while offset <= end:
            chunk_end = min(end, offset + _STREAM_CHUNK_SIZE - 1)
            if not cache.wait_for_range(offset, chunk_end):
                raise TimeoutError(f"Danbooru video cache range wait timed out: start={offset} end={chunk_end}")
            chunk = cache.read_range(offset, chunk_end)
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except OSError as exc:
                if self._is_client_disconnect(exc):
                    raise _ClientDisconnected() from exc
                raise
            offset += len(chunk)
        try:
            handler.wfile.flush()
        except OSError as exc:
            if self._is_client_disconnect(exc):
                raise _ClientDisconnected() from exc
            raise

    @staticmethod
    def _is_client_disconnect(exc: OSError) -> bool:
        return is_client_disconnect_error(exc)
