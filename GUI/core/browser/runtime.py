from __future__ import annotations

import contextlib
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

_browser_debug_event_sink_lock = threading.Lock()
_browser_debug_event_sink: Optional[Callable[[dict], None]] = None


def set_browser_debug_event_sink(sink: Optional[Callable[[dict], None]]) -> None:
    global _browser_debug_event_sink
    with _browser_debug_event_sink_lock:
        _browser_debug_event_sink = sink


def append_browser_debug_event(stage: str, **payload) -> dict:
    event = {
        "stage": str(stage or "").strip() or "unknown",
        "time": time.time(),
        **payload,
    }
    with _browser_debug_event_sink_lock:
        sink = _browser_debug_event_sink
    if sink is None:
        return event
    sink(dict(event))
    return event


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


class BrowserRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.referer_url = None
        self._capture_lock = threading.Lock()
        self._capture_host = ""
        self._capture_paths = ()
        self._capture_debug_pickle_path = ""
        self._captured_requests = []
        self._capture_limit = 8

    def _logger(self):
        browser = self.parent()
        gui = getattr(browser, "gui", None)
        return getattr(gui, "log", None)

    def _log_debug(self, message: str):
        logger = self._logger()
        if logger:
            logger.debug(f"[browser.capture] {message}")

    def set_referer_url(self, referer_url):
        self.referer_url = referer_url

    @staticmethod
    def _normalize_capture_host(host_filter: str) -> str:
        raw = str(host_filter or "").strip()
        if not raw:
            return ""
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        return str(parsed.hostname or raw).strip().casefold()

    @staticmethod
    def _decode_header_bytes(payload) -> str:
        try:
            return bytes(payload).decode("utf-8", errors="ignore")
        except Exception:
            return str(payload or "")

    def configure_request_capture(self, *, host_filter: str = "", path_filters=(), debug_pickle_path: str = "", limit: int = 8):
        normalized_paths = tuple(
            str(path or "").strip()
            for path in (path_filters or ())
            if str(path or "").strip()
        )
        with self._capture_lock:
            self._capture_host = self._normalize_capture_host(host_filter)
            self._capture_paths = normalized_paths
            self._capture_debug_pickle_path = str(debug_pickle_path or "").strip()
            self._captured_requests.clear()
            self._capture_limit = max(1, int(limit or 1))
        append_browser_debug_event(
            "request_capture.configured",
            host_filter=host_filter,
            path_filters=normalized_paths,
            debug_pickle_path=debug_pickle_path,
            limit=self._capture_limit,
        )

    def clear_request_capture(self):
        with self._capture_lock:
            self._captured_requests.clear()
            self._capture_host = ""
            self._capture_paths = ()
            self._capture_debug_pickle_path = ""

    def latest_captured_request(self, *, path_suffix: str = "") -> dict:
        normalized_path = str(path_suffix or "").strip()
        with self._capture_lock:
            captured = list(self._captured_requests)
        if not normalized_path:
            return dict(captured[-1]) if captured else {}
        for item in reversed(captured):
            if str(item.get("path", "")) == normalized_path:
                return dict(item)
        return {}

    def _should_capture_request(self, request_url: QUrl) -> bool:
        host = str(request_url.host() or "").strip().casefold()
        path = str(request_url.path() or "").strip()
        with self._capture_lock:
            capture_host = self._capture_host
            capture_paths = self._capture_paths
        if not capture_host:
            return False
        if host != capture_host:
            return False
        if not capture_paths:
            return True
        return any(path == candidate for candidate in capture_paths)

    def _write_capture_pickle(self, requests_snapshot):
        with self._capture_lock:
            debug_pickle_path = self._capture_debug_pickle_path
        if not debug_pickle_path:
            return
        target = Path(debug_pickle_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            pickle.dump(requests_snapshot, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def _capture_request(self, info):
        request_url = info.requestUrl()
        if not self._should_capture_request(request_url):
            return
        headers = {
            self._decode_header_bytes(name): self._decode_header_bytes(value)
            for name, value in dict(info.httpHeaders() or {}).items()
        }
        record = {
            "time": time.time(),
            "url": request_url.toString(),
            "path": request_url.path(),
            "method": self._decode_header_bytes(info.requestMethod()),
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
        with self._capture_lock:
            self._captured_requests.append(record)
            if len(self._captured_requests) > self._capture_limit:
                self._captured_requests = self._captured_requests[-self._capture_limit:]
            requests_snapshot = list(self._captured_requests)
            debug_pickle_path = self._capture_debug_pickle_path
        self._write_capture_pickle(requests_snapshot)
        self._log_debug(
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

    def interceptRequest(self, info):
        if self.referer_url and info.requestUrl().toString().endswith(("png", "jpg", "jpeg", "webp", "avif")):
            info.setHttpHeader(b"referer", str(self.referer_url).encode())
        self._capture_request(info)


class BrowserCookieSnapshotCollector(QObject):
    snapshot_ready = Signal(object)

    def __init__(
        self,
        cookie_store,
        domain_filter: str,
        source_url: str = "",
        debug_pickle_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._cookie_store = cookie_store
        self._domain_filters = _build_domain_filters(domain_filter)
        self._source_url = QUrl(str(source_url or ""))
        self._source_host = self._source_url.host().strip().casefold()
        self._debug_pickle_path = str(debug_pickle_path or "").strip()
        self._cookies = {}
        self._started_at = time.time()
        self._on_cookie_added_calls = 0
        self._accepted_cookie_count = 0
        self._event_trace = []
        self._exceptions = []
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._finish)
        append_browser_debug_event(
            "cookie.collector.constructed",
            source_url=self._source_url.toString(),
            source_host=self._source_host,
            domain_filters=self._domain_filters,
            debug_pickle_path=self._debug_pickle_path,
            thread_id=threading.get_ident(),
        )
        self._log_debug(
            f"constructed source_url={self._source_url.toString() or '<unknown>'} "
            f"thread_id={threading.get_ident()} debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )

    def _logger(self):
        browser = self.parent()
        gui = getattr(browser, "gui", None)
        return getattr(gui, "log", None)

    def _log_debug(self, message: str):
        logger = self._logger()
        if logger:
            logger.debug(f"[browser.cookie] {message}")

    def _matches_domain_filter(self, normalized_domain: str) -> bool:
        if not self._domain_filters:
            return True
        return any(
            normalized_domain == domain_filter or normalized_domain.endswith(f".{domain_filter}")
            for domain_filter in self._domain_filters
        )

    def start(self):
        append_browser_debug_event(
            "cookie.collector.start",
            source_url=self._source_url.toString(),
            source_host=self._source_host,
            domain_filters=self._domain_filters,
            debug_pickle_path=self._debug_pickle_path,
            thread_id=threading.get_ident(),
        )
        self._log_debug(
            f"start source_url={self._source_url.toString() or '<unknown>'} "
            f"domain_filters={self._domain_filters} debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )
        self._cookie_store.cookieAdded.connect(self._on_cookie_added)
        self._idle_timer.start(180)
        self._cookie_store.loadAllCookies()

    def _append_event_trace(self, payload: dict):
        if len(self._event_trace) >= 64:
            return
        self._event_trace.append(payload)

    def _on_cookie_added(self, cookie):
        self._on_cookie_added_calls += 1
        try:
            if hasattr(cookie, "normalize") and self._source_url.isValid():
                cookie.normalize(self._source_url)
            name = bytes(cookie.name()).decode("utf-8", errors="ignore").strip()
            domain = str(cookie.domain() or "").strip()
            path = str(cookie.path() or "/").strip() or "/"
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
        except Exception as exc:
            self._exceptions.append(repr(exc))
            self._idle_timer.start(180)
            return
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
        self._append_event_trace(event)
        if self._on_cookie_added_calls <= 16:
            append_browser_debug_event(
                "cookie.collector.signal",
                source_url=self._source_url.toString(),
                source_host=self._source_host,
                domain_filters=self._domain_filters,
                call=self._on_cookie_added_calls,
                **event,
            )
            self._log_debug(
                f"signal call={self._on_cookie_added_calls} name={name or '<empty>'} "
                f"domain={domain or '<empty>'} normalized_domain={normalized_domain or '<empty>'} "
                f"accepted={accepted}"
            )
        if not accepted:
            self._idle_timer.start(180)
            return
        self._cookies[(name, domain, path)] = {
            "name": name,
            "value": value,
            "domain": domain or self._source_host,
            "path": path,
        }
        self._accepted_cookie_count += 1
        self._idle_timer.start(180)

    def _build_debug_snapshot(self) -> dict:
        return {
            "started_at": self._started_at,
            "finished_at": time.time(),
            "source_url": self._source_url.toString(),
            "source_host": self._source_host,
            "domain_filters": self._domain_filters,
            "on_cookie_added_calls": self._on_cookie_added_calls,
            "accepted_cookie_count": self._accepted_cookie_count,
            "emitted_cookie_count": len(self._cookies),
            "emitted_cookies": list(self._cookies.values()),
            "event_trace": list(self._event_trace),
            "exceptions": list(self._exceptions),
        }

    def _write_debug_pickle(self):
        if not self._debug_pickle_path:
            return
        payload = self._build_debug_snapshot()
        target = Path(self._debug_pickle_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def _finish(self):
        with contextlib.suppress(TypeError):
            self._cookie_store.cookieAdded.disconnect(self._on_cookie_added)
        with contextlib.suppress(Exception):
            self._write_debug_pickle()
        snapshot = self._build_debug_snapshot()
        append_browser_debug_event(
            "cookie.collector.finish",
            source_url=self._source_url.toString(),
            source_host=self._source_host,
            domain_filters=self._domain_filters,
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
        self.snapshot_ready.emit(list(self._cookies.values()))
        self.deleteLater()


class BrowserLiveCookieTracker(QObject):
    def __init__(
        self,
        cookie_store,
        domain_filter: str,
        *,
        source_url: str = "",
        debug_pickle_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._cookie_store = cookie_store
        self._domain_filters = _build_domain_filters(domain_filter)
        self._source_url = QUrl(str(source_url or ""))
        self._source_host = self._source_url.host().strip().casefold()
        self._debug_pickle_path = str(debug_pickle_path or "").strip()
        self._cookies = {}
        self._started_at = time.time()
        self._on_cookie_added_calls = 0
        self._accepted_cookie_count = 0
        self._event_trace = []
        self._exceptions = []
        self._active = False

    def _logger(self):
        browser = self.parent()
        gui = getattr(browser, "gui", None)
        return getattr(gui, "log", None)

    def _log_debug(self, message: str):
        logger = self._logger()
        if logger:
            logger.debug(f"[browser.live_cookie] {message}")

    def _matches_domain_filter(self, normalized_domain: str) -> bool:
        if not self._domain_filters:
            return True
        return any(
            normalized_domain == domain_filter or normalized_domain.endswith(f".{domain_filter}")
            for domain_filter in self._domain_filters
        )

    def start(self):
        if self._active:
            self.stop()
        self._cookie_store.cookieAdded.connect(self._on_cookie_added)
        self._active = True
        append_browser_debug_event(
            "live_cookie.start",
            source_url=self._source_url.toString(),
            source_host=self._source_host,
            domain_filters=self._domain_filters,
            emitted_cookie_count=len(self._cookies),
            debug_pickle_path=self._debug_pickle_path,
            thread_id=threading.get_ident(),
        )
        self._log_debug(
            f"start source_url={self._source_url.toString() or '<unknown>'} "
            f"domain_filters={self._domain_filters} debug_pickle_path={self._debug_pickle_path or '<none>'}"
        )
        self._write_debug_pickle()

    def stop(self):
        if not self._active:
            return
        with contextlib.suppress(TypeError):
            self._cookie_store.cookieAdded.disconnect(self._on_cookie_added)
        self._active = False
        snapshot = self._build_debug_snapshot()
        append_browser_debug_event(
            "live_cookie.stop",
            source_url=self._source_url.toString(),
            source_host=self._source_host,
            domain_filters=self._domain_filters,
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
        self._write_debug_pickle()

    def snapshot(self):
        return list(self._cookies.values())

    def _append_event_trace(self, payload: dict):
        if len(self._event_trace) >= 128:
            return
        self._event_trace.append(payload)

    def _build_debug_snapshot(self) -> dict:
        return {
            "started_at": self._started_at,
            "finished_at": time.time(),
            "source_url": self._source_url.toString(),
            "source_host": self._source_host,
            "domain_filters": self._domain_filters,
            "on_cookie_added_calls": self._on_cookie_added_calls,
            "accepted_cookie_count": self._accepted_cookie_count,
            "emitted_cookie_count": len(self._cookies),
            "emitted_cookies": list(self._cookies.values()),
            "event_trace": list(self._event_trace),
            "exceptions": list(self._exceptions),
            "active": self._active,
        }

    def _write_debug_pickle(self):
        if not self._debug_pickle_path:
            return
        target = Path(self._debug_pickle_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            pickle.dump(self._build_debug_snapshot(), fh, protocol=pickle.HIGHEST_PROTOCOL)

    def _on_cookie_added(self, cookie):
        self._on_cookie_added_calls += 1
        try:
            if hasattr(cookie, "normalize") and self._source_url.isValid():
                cookie.normalize(self._source_url)
            name = bytes(cookie.name()).decode("utf-8", errors="ignore").strip()
            domain = str(cookie.domain() or "").strip()
            path = str(cookie.path() or "/").strip() or "/"
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
        except Exception as exc:
            self._exceptions.append(repr(exc))
            self._write_debug_pickle()
            return
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
        self._append_event_trace(event)
        if self._on_cookie_added_calls <= 24:
            append_browser_debug_event(
                "live_cookie.signal",
                source_url=self._source_url.toString(),
                source_host=self._source_host,
                domain_filters=self._domain_filters,
                call=self._on_cookie_added_calls,
                **event,
            )
            self._log_debug(
                f"signal call={self._on_cookie_added_calls} name={name or '<empty>'} "
                f"domain={domain or '<empty>'} normalized_domain={normalized_domain or '<empty>'} "
                f"accepted={accepted}"
            )
        if not accepted:
            self._write_debug_pickle()
            return
        self._cookies[(name, domain, path)] = {
            "name": name,
            "value": value,
            "domain": domain or self._source_host,
            "path": path,
        }
        self._accepted_cookie_count += 1
        self._write_debug_pickle()
