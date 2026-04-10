from __future__ import annotations

import pickle
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

from .types import BrowserCookieSet

class _BrowserDebugEventHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._sink: Optional[Callable[[dict], None]] = None

    def set_sink(self, sink: Optional[Callable[[dict], None]]) -> None:
        with self._lock:
            self._sink = sink

    def append(self, stage: str, **payload) -> dict:
        event = {
            "stage": str(stage or "").strip() or "unknown",
            "time": time.time(),
            **payload,
        }
        with self._lock:
            sink = self._sink
        if sink is not None:
            sink(dict(event))
        return event


_BROWSER_DEBUG_EVENTS = _BrowserDebugEventHub()
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".avif"})
_MONITOR_VOTE_REQUEST_PATH = "/api/monitor/vote"


def set_browser_debug_event_sink(sink: Optional[Callable[[dict], None]]) -> None:
    _BROWSER_DEBUG_EVENTS.set_sink(sink)


def append_browser_debug_event(stage: str, **payload) -> dict:
    return _BROWSER_DEBUG_EVENTS.append(stage, **payload)


def apply_cookie_sets(cookie_store, cookie_sets: tuple[BrowserCookieSet, ...]) -> None:
    for cookie_set in cookie_sets:
        for key, value in cookie_set.values.items():
            cookie = QNetworkCookie()
            cookie.setName(str(key).encode())
            cookie.setValue(str(value).encode())
            cookie.setDomain(cookie_set.domain)
            cookie_store.setCookie(cookie, QUrl(cookie_set.url))


def _build_domain_filters(domain_filter: str) -> tuple[str, ...]:
    raw_filter = str(domain_filter or "").strip().casefold()
    if not raw_filter:
        return ()
    parsed = urlsplit(raw_filter if "://" in raw_filter else f"https://{raw_filter}")
    host = (parsed.hostname or raw_filter).lstrip(".").casefold()
    if not host:
        return ()
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return (host,)
    filters: list[str] = []
    for start_index in range(len(labels) - 1):
        candidate = ".".join(labels[start_index:])
        if candidate not in filters:
            filters.append(candidate)
    return tuple(filters)


def _cookie_names_from_header(header_value: str) -> list[str]:
    cookie_names: list[str] = []
    for chunk in str(header_value or "").split(";"):
        name = chunk.split("=", 1)[0].strip()
        if name:
            cookie_names.append(name)
    return sorted(set(cookie_names))


def _decode_browser_bytes(payload) -> str:
    return bytes(payload).decode("utf-8", errors="ignore")


def _normalize_browser_origin(url_or_origin: str) -> str:
    raw = str(url_or_origin or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    scheme = (parsed.scheme or "https").casefold()
    host = str(parsed.hostname or "").strip().casefold()
    if not host:
        return ""
    port = parsed.port
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    if port is None or port == default_port:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _normalize_browser_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized.endswith(".html"):
        normalized = normalized[:-5]
    normalized = normalized.rstrip("/")
    return normalized or "/"


def _browser_logger(owner):
    gui = getattr(owner, "gui", None)
    return getattr(gui, "log", None)


def _log_browser_debug(owner, channel: str, message: str) -> None:
    logger = _browser_logger(owner)
    if logger:
        logger.debug(f"[{channel}] {message}")


class _RequestCaptureStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._host = ""
        self._paths: tuple[str, ...] = ()
        self._debug_pickle_path = ""
        self._records: list[dict] = []
        self._limit = 8

    @staticmethod
    def _normalize_host(host_filter: str) -> str:
        raw = str(host_filter or "").strip()
        if not raw:
            return ""
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        return str(parsed.hostname or raw).strip().casefold()

    def configure(
        self,
        *,
        host_filter: str = "",
        path_filters=(),
        debug_pickle_path: str = "",
        limit: int = 8,
    ) -> tuple[tuple[str, ...], int]:
        normalized_paths = tuple(
            str(path or "").strip()
            for path in (path_filters or ())
            if str(path or "").strip()
        )
        capture_limit = max(1, int(limit or 1))
        with self._lock:
            self._host = self._normalize_host(host_filter)
            self._paths = normalized_paths
            self._debug_pickle_path = str(debug_pickle_path or "").strip()
            self._records.clear()
            self._limit = capture_limit
        return normalized_paths, capture_limit

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._host = ""
            self._paths = ()
            self._debug_pickle_path = ""

    def latest(self, *, url: str = "", path_suffix: str = "") -> dict:
        normalized_url = str(url or "").strip()
        normalized_path = str(path_suffix or "").strip()
        with self._lock:
            records = list(self._records)
        if normalized_url:
            for item in reversed(records):
                if str(item.get("url", "")).strip() == normalized_url:
                    return dict(item)
        if normalized_path:
            for item in reversed(records):
                if str(item.get("path", "")) == normalized_path:
                    return dict(item)
        if not normalized_url and not normalized_path:
            return dict(records[-1]) if records else {}
        return {}

    def should_capture(self, request_url: QUrl) -> bool:
        host = str(request_url.host() or "").strip().casefold()
        path = str(request_url.path() or "").strip()
        with self._lock:
            capture_host = self._host
            capture_paths = self._paths
        if not capture_host or host != capture_host:
            return False
        if not capture_paths:
            return True
        return any(path == candidate for candidate in capture_paths)

    def capture(self, record: dict) -> str:
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._limit:
                self._records = self._records[-self._limit:]
            snapshot = list(self._records)
            debug_pickle_path = self._debug_pickle_path
        if debug_pickle_path:
            target = Path(debug_pickle_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as fh:
                pickle.dump(snapshot, fh, protocol=pickle.HIGHEST_PROTOCOL)
        return debug_pickle_path


class _BrowserCookieObserver(QObject):
    def __init__(
        self,
        cookie_store,
        domain_filter: str,
        *,
        source_url: str = "",
        debug_pickle_path: str = "",
        log_channel: str,
        event_trace_limit: int,
        parent=None,
    ):
        super().__init__(parent)
        self._cookie_store = cookie_store
        self._domain_filters = _build_domain_filters(domain_filter)
        self._source_url = QUrl(str(source_url or ""))
        self._source_host = self._source_url.host().strip().casefold()
        self._debug_pickle_path = str(debug_pickle_path or "").strip()
        self._cookies: dict[tuple[str, str, str], dict] = {}
        self._started_at = time.time()
        self._on_cookie_added_calls = 0
        self._accepted_cookie_count = 0
        self._event_trace: list[dict] = []
        self._event_trace_limit = max(1, int(event_trace_limit or 1))
        self._exceptions: list[str] = []
        self._log_channel = log_channel
        self._cookie_added_connected = False

    def _emit_event(self, stage: str, **payload) -> None:
        append_browser_debug_event(
            stage,
            source_url=self._source_url.toString(),
            source_host=self._source_host,
            domain_filters=self._domain_filters,
            **payload,
        )

    def _log_debug(self, message: str) -> None:
        _log_browser_debug(self.parent(), self._log_channel, message)

    def _set_cookie_subscription(self, active: bool, slot) -> None:
        if active:
            if not self._cookie_added_connected:
                self._cookie_store.cookieAdded.connect(slot)
                self._cookie_added_connected = True
            return
        if self._cookie_added_connected:
            self._cookie_store.cookieAdded.disconnect(slot)
            self._cookie_added_connected = False

    def _matches_domain_filter(self, normalized_domain: str) -> bool:
        if not self._domain_filters:
            return True
        return any(
            normalized_domain == domain_filter or normalized_domain.endswith(f".{domain_filter}")
            for domain_filter in self._domain_filters
        )

    def observe_cookie(self, cookie, *, signal_stage: str, signal_limit: int) -> None:
        self._on_cookie_added_calls += 1
        if hasattr(cookie, "normalize") and self._source_url.isValid():
            cookie.normalize(self._source_url)
        name = _decode_browser_bytes(cookie.name()).strip()
        domain = str(cookie.domain() or "").strip()
        path = str(cookie.path() or "/").strip() or "/"
        value = _decode_browser_bytes(cookie.value())
        normalized_domain = domain.lstrip(".").casefold() or self._source_host
        accepted = bool(name) and self._matches_domain_filter(normalized_domain)
        event = {
            "name": name,
            "domain": domain,
            "path": path,
            "normalized_domain": normalized_domain,
            "accepted": accepted,
            "stored_domain": domain or self._source_host,
            "value_length": len(value),
        }
        if len(self._event_trace) < self._event_trace_limit:
            self._event_trace.append(event)
        if self._on_cookie_added_calls <= signal_limit:
            self._emit_event(signal_stage, call=self._on_cookie_added_calls, **event)
            self._log_debug(
                f"signal call={self._on_cookie_added_calls} name={name or '<empty>'} "
                f"domain={domain or '<empty>'} normalized_domain={normalized_domain or '<empty>'} "
                f"accepted={accepted}"
            )
        if not accepted:
            return
        self._cookies[(name, domain, path)] = {
            "name": name,
            "value": value,
            "domain": domain or self._source_host,
            "path": path,
        }
        self._accepted_cookie_count += 1

    def snapshot(self):
        return list(self._cookies.values())

    def build_debug_snapshot(self, **extra) -> dict:
        emitted_cookies = self.snapshot()
        snapshot = {
            "started_at": self._started_at,
            "finished_at": time.time(),
            "source_url": self._source_url.toString(),
            "source_host": self._source_host,
            "domain_filters": self._domain_filters,
            "on_cookie_added_calls": self._on_cookie_added_calls,
            "accepted_cookie_count": self._accepted_cookie_count,
            "emitted_cookie_count": len(emitted_cookies),
            "emitted_cookies": emitted_cookies,
            "event_trace": list(self._event_trace),
            "exceptions": list(self._exceptions),
        }
        snapshot.update(extra)
        return snapshot

    def write_debug_pickle(self, **extra) -> None:
        if not self._debug_pickle_path:
            return
        target = Path(self._debug_pickle_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fh:
            pickle.dump(self.build_debug_snapshot(**extra), fh, protocol=pickle.HIGHEST_PROTOCOL)


class BrowserRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.referer_url = None
        self._capture = _RequestCaptureStore()
        self._recent_image_requests = _RequestCaptureStore()
        self._recent_image_requests.configure(limit=16)
        self._monitor_vote_header_name = b""
        self._monitor_vote_header_value = b""
        self._monitor_vote_allowed_origins: tuple[str, ...] = ()
        self._monitor_vote_page_path = ""

    def set_referer_url(self, referer_url):
        self.referer_url = str(referer_url or "").strip() or None

    def configure_monitor_vote_header(
        self, *,
        allowed_origins=(), page_path: str = "", header_name: str = "", header_value: str = "",
    ) -> None:
        normalized_origins = []
        for origin in allowed_origins or ():
            normalized = _normalize_browser_origin(origin)
            if normalized and normalized not in normalized_origins:
                normalized_origins.append(normalized)
        self._monitor_vote_allowed_origins = tuple(normalized_origins)
        self._monitor_vote_page_path = _normalize_browser_path(page_path)
        self._monitor_vote_header_name = str(header_name or "").strip().encode("utf-8")
        self._monitor_vote_header_value = str(header_value or "").strip().encode("utf-8")

    @staticmethod
    def _is_image_request(request_url: QUrl) -> bool:
        path = str(request_url.path() or "").strip()
        return Path(path).suffix.casefold() in _IMAGE_SUFFIXES

    def _should_inject_monitor_vote_header(self, info) -> bool:
        def _current_page_context_url() -> str:
            parent = self.parent()
            view = getattr(parent, "view", None)
            url_getter = getattr(view, "url", None)
            if not callable(url_getter):
                return ""
            current_url = url_getter()
            return current_url.toString() if hasattr(current_url, "toString") else str(current_url or "")
        def _matches_monitor_vote_page_context(url_value: str) -> bool:
            if not self._monitor_vote_allowed_origins or not self._monitor_vote_page_path:
                return False
            raw = str(url_value or "").strip()
            if not raw:
                return False
            parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
            return (
                _normalize_browser_origin(raw) in self._monitor_vote_allowed_origins
                and _normalize_browser_path(parsed.path) == self._monitor_vote_page_path
            )
        if not self._monitor_vote_header_name or not self._monitor_vote_header_value:
            return False
        request_path = _normalize_browser_path(info.requestUrl().path())
        request_method = _decode_browser_bytes(info.requestMethod()).upper()
        if request_method != "POST" or request_path != _MONITOR_VOTE_REQUEST_PATH:
            return False
        return any(
            _matches_monitor_vote_page_context(candidate)
            for candidate in (
                info.firstPartyUrl().toString(), info.initiator().toString(),
                _current_page_context_url(),
            )
        )

    def configure_request_capture(
        self,
        *,
        host_filter: str = "",
        path_filters=(),
        debug_pickle_path: str = "",
        limit: int = 8,
    ):
        normalized_paths, capture_limit = self._capture.configure(
            host_filter=host_filter,
            path_filters=path_filters,
            debug_pickle_path=debug_pickle_path,
            limit=limit,
        )
        append_browser_debug_event(
            "request_capture.configured",
            host_filter=host_filter,
            path_filters=normalized_paths,
            debug_pickle_path=debug_pickle_path,
            limit=capture_limit,
        )

    def clear_request_capture(self):
        self._capture.clear()

    def latest_captured_request(self, *, url: str = "", path_suffix: str = "") -> dict:
        return self._capture.latest(url=url, path_suffix=path_suffix)

    def latest_image_request(self, *, url: str = "", path_suffix: str = "") -> dict:
        return self._recent_image_requests.latest(url=url, path_suffix=path_suffix)

    def interceptRequest(self, info):
        request_url = info.requestUrl()
        image_request = self._is_image_request(request_url)
        if self.referer_url and image_request:
            info.setHttpHeader(b"referer", self.referer_url.encode())
        if self._should_inject_monitor_vote_header(info):
            info.setHttpHeader(self._monitor_vote_header_name, self._monitor_vote_header_value)
        should_capture = self._capture.should_capture(request_url)
        if not image_request and not should_capture:
            return
        headers = {
            _decode_browser_bytes(name): _decode_browser_bytes(value)
            for name, value in dict(info.httpHeaders() or {}).items()
        }
        record = {
            "time": time.time(),
            "url": request_url.toString(),
            "path": request_url.path(),
            "method": _decode_browser_bytes(info.requestMethod()),
            "first_party_url": info.firstPartyUrl().toString(),
            "initiator": info.initiator().toString(),
            "resource_type": getattr(info.resourceType(), "name", str(info.resourceType())),
            "navigation_type": getattr(info.navigationType(), "name", str(info.navigationType())),
            "headers": headers,
            "header_names": sorted(headers.keys()),
            "cookie_header_names": _cookie_names_from_header(
                headers.get("Cookie") or headers.get("cookie") or ""
            ),
        }
        if image_request:
            self._recent_image_requests.capture(record)
        if not should_capture:
            return
        debug_pickle_path = self._capture.capture(record)
        _log_browser_debug(
            self.parent(),
            "browser.capture",
            f"captured url={record['url']} method={record['method']} "
            f"cookies={record['cookie_header_names']} debug_pickle_path={debug_pickle_path or '<none>'}"
        )
        append_browser_debug_event(
            "request_capture.signal",
            url=record["url"],
            path=record["path"],
            method=record["method"],
            first_party_url=record["first_party_url"],
            initiator=record["initiator"],
            resource_type=record["resource_type"],
            navigation_type=record["navigation_type"],
            header_names=record["header_names"],
            cookie_header_names=record["cookie_header_names"],
            debug_pickle_path=debug_pickle_path,
        )


class BrowserCookieSnapshotCollector(_BrowserCookieObserver):
    snapshot_ready = Signal(object)

    def __init__(
        self,
        cookie_store,
        domain_filter: str,
        source_url: str = "",
        debug_pickle_path: str = "",
        parent=None,
    ):
        super().__init__(
            cookie_store,
            domain_filter,
            source_url=source_url,
            debug_pickle_path=debug_pickle_path,
            log_channel="browser.cookie",
            event_trace_limit=64,
            parent=parent,
        )
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._finish)
        self._emit_event(
            "cookie.collector.constructed",
            debug_pickle_path=self._debug_pickle_path,
            thread_id=threading.get_ident(),
        )
        self._log_debug(
            f"constructed source_url={self._source_url.toString() or '<unknown>'} "
            f"thread_id={threading.get_ident()} debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )

    def start(self):
        self._emit_event(
            "cookie.collector.start",
            debug_pickle_path=self._debug_pickle_path,
            thread_id=threading.get_ident(),
        )
        self._log_debug(
            f"start source_url={self._source_url.toString() or '<unknown>'} "
            f"domain_filters={self._domain_filters} debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )
        self._set_cookie_subscription(True, self._on_cookie_added)
        self._idle_timer.start(180)
        self._cookie_store.loadAllCookies()

    def _on_cookie_added(self, cookie):
        try:
            self.observe_cookie(cookie, signal_stage="cookie.collector.signal", signal_limit=16)
        except Exception as exc:
            self._exceptions.append(repr(exc))
            raise
        finally:
            self._idle_timer.start(180)

    def _finish(self):
        self._set_cookie_subscription(False, self._on_cookie_added)
        self.write_debug_pickle()
        snapshot = self.build_debug_snapshot()
        self._emit_event(
            "cookie.collector.finish",
            on_cookie_added_calls=snapshot["on_cookie_added_calls"],
            accepted_cookie_count=snapshot["accepted_cookie_count"],
            emitted_cookie_count=snapshot["emitted_cookie_count"],
            emitted_cookies=snapshot["emitted_cookies"],
            exceptions=snapshot["exceptions"],
            event_trace=snapshot["event_trace"],
            debug_pickle_path=self._debug_pickle_path,
        )
        self._log_debug(
            f"finish on_cookie_added_calls={snapshot['on_cookie_added_calls']} "
            f"accepted={snapshot['accepted_cookie_count']} emitted={snapshot['emitted_cookie_count']} "
            f"debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )
        self.snapshot_ready.emit(snapshot["emitted_cookies"])
        self.deleteLater()


class BrowserLiveCookieTracker(_BrowserCookieObserver):
    def __init__(
        self,
        cookie_store,
        domain_filter: str,
        *,
        source_url: str = "",
        debug_pickle_path: str = "",
        parent=None,
    ):
        super().__init__(
            cookie_store,
            domain_filter,
            source_url=source_url,
            debug_pickle_path=debug_pickle_path,
            log_channel="browser.live_cookie",
            event_trace_limit=128,
            parent=parent,
        )
        self._active = False

    def start(self):
        if self._active:
            self.stop()
        self._set_cookie_subscription(True, self._on_cookie_added)
        self._active = True
        cookies = self.snapshot()
        self._emit_event(
            "live_cookie.start",
            emitted_cookie_count=len(cookies),
            debug_pickle_path=self._debug_pickle_path,
            thread_id=threading.get_ident(),
        )
        self._log_debug(
            f"start source_url={self._source_url.toString() or '<unknown>'} "
            f"domain_filters={self._domain_filters} debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )
        self.write_debug_pickle(active=self._active)

    def stop(self):
        if not self._active:
            return
        self._set_cookie_subscription(False, self._on_cookie_added)
        self._active = False
        snapshot = self.build_debug_snapshot(active=self._active)
        self._emit_event(
            "live_cookie.stop",
            on_cookie_added_calls=snapshot["on_cookie_added_calls"],
            accepted_cookie_count=snapshot["accepted_cookie_count"],
            emitted_cookie_count=snapshot["emitted_cookie_count"],
            emitted_cookies=snapshot["emitted_cookies"],
            exceptions=snapshot["exceptions"],
            event_trace=snapshot["event_trace"],
            debug_pickle_path=self._debug_pickle_path,
        )
        self._log_debug(
            f"stop on_cookie_added_calls={snapshot['on_cookie_added_calls']} "
            f"accepted={snapshot['accepted_cookie_count']} emitted={snapshot['emitted_cookie_count']} "
            f"debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )
        self.write_debug_pickle(active=self._active)

    def _on_cookie_added(self, cookie):
        try:
            self.observe_cookie(cookie, signal_stage="live_cookie.signal", signal_limit=24)
        except Exception as exc:
            self._exceptions.append(repr(exc))
            raise
        finally:
            self.write_debug_pickle(active=self._active)
