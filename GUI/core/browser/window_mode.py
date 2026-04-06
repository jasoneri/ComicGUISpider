from __future__ import annotations

from PySide6 import QtNetwork
from PySide6.QtCore import QUrl

from utils.network.extra import ensure_doh_webengine_proxy_started
from .runtime import (
    BrowserCookieSnapshotCollector,
    BrowserLiveCookieTracker,
    append_browser_debug_event,
)
from .types import BrowserChallengeResult, BrowserChallengeSpec


class BrowserDoHProxyRuntime:
    def __init__(self, browser):
        self._browser = browser
        self._managed_proxy = False
        self._previous_application_proxy = None

    def apply(self, doh_url: str) -> None:
        proxy_str = ensure_doh_webengine_proxy_started(doh_url)
        if not self._managed_proxy:
            self._previous_application_proxy = QtNetwork.QNetworkProxy.applicationProxy()
        self._managed_proxy = True
        if proxy_str:
            self._browser.set_proxies(proxy_str)
            return
        self._browser.clear_proxies()

    def restore(self) -> None:
        if not self._managed_proxy:
            return
        previous = self._previous_application_proxy or QtNetwork.QNetworkProxy(QtNetwork.QNetworkProxy.NoProxy)
        QtNetwork.QNetworkProxy.setApplicationProxy(previous)
        self._previous_application_proxy = None
        self._managed_proxy = False


class BrowserWindowModeController:
    def __init__(self, browser, interceptor):
        self._browser = browser
        self._interceptor = interceptor
        self._ensure_callback = browser.gui.next
        self._ensure_result_kind = "checked_ids"
        self._close_handler = None
        self._uses_page_scan = True
        self._doh_proxy_runtime = BrowserDoHProxyRuntime(browser)
        self._cookie_collector = None
        self._live_cookie_tracker = None

    @property
    def ensure_callback(self):
        return self._ensure_callback

    @property
    def close_handler(self):
        return self._close_handler

    @property
    def ensure_result_kind(self) -> str:
        return self._ensure_result_kind

    @property
    def uses_page_scan(self) -> bool:
        return self._uses_page_scan

    def set_ensure_handler(self, callback=None, *, result_kind: str = "checked_ids") -> None:
        self._ensure_callback = callback or self._browser.gui.next
        self._ensure_result_kind = result_kind

    def set_close_handler(self, callback=None) -> None:
        self._close_handler = callback

    def reset_standard_mode(self, *, window_title: str, ensure_tooltip: str) -> None:
        self._uses_page_scan = True
        self._ensure_result_kind = "checked_ids"
        self.stop_cookie_watch()
        self._interceptor.clear_request_capture()
        self._doh_proxy_runtime.restore()
        self._browser.copyBtn.show()
        self._browser.ensureBtn.setToolTip(ensure_tooltip)
        self._browser.setWindowTitle(window_title)

    def enter_challenge_mode(
        self,
        spec: BrowserChallengeSpec,
        *,
        ensure_handler=None,
        close_handler=None,
    ) -> None:
        self._uses_page_scan = False
        self._ensure_callback = ensure_handler or (lambda: None)
        self._ensure_result_kind = "checked_ids"
        self._close_handler = close_handler
        self._browser.home_url = QUrl(str(spec.verify_url))
        if spec.doh_url:
            self._doh_proxy_runtime.apply(spec.doh_url)
        else:
            self._doh_proxy_runtime.restore()
        if spec.window_title:
            self._browser.setWindowTitle(spec.window_title)
        self._browser.ensureBtn.setToolTip("继续请求")
        self._browser.copyBtn.hide()
        if spec.window_size is not None:
            self._browser.resize(spec.window_size)
        if spec.request_capture is not None:
            self._interceptor.configure_request_capture(
                host_filter=spec.request_capture.host_filter,
                path_filters=spec.request_capture.path_filters,
                debug_pickle_path=spec.request_capture.debug_pickle_path,
                limit=spec.request_capture.limit,
            )
        else:
            self._interceptor.clear_request_capture()
        self._start_cookie_watch(
            domain_filter=spec.domain_filter,
            source_url=spec.source_url or spec.verify_url,
            debug_pickle_path=spec.debug_pickle_path,
        )
        if self._browser.isVisible():
            self._browser.load_home()

    def collect_challenge_result(
        self,
        spec: BrowserChallengeSpec,
        callback,
        *,
        current_url: str = "",
        trigger: str = "manual",
    ) -> None:
        active_url = current_url or self._browser.view.url().toString()
        source_url = spec.source_url or active_url or spec.verify_url
        append_browser_debug_event(
            "browser.collect_cookies",
            current_url=self._browser.view.url().toString(),
            source_url=source_url,
            domain_filter=spec.domain_filter,
            debug_pickle_path=spec.debug_pickle_path,
            trigger=trigger,
        )

        def on_snapshot_ready(cookies):
            headers = {}
            if spec.request_capture is not None:
                headers = dict(self._interceptor.latest_captured_request().get("headers") or {})
            callback(BrowserChallengeResult(
                snapshot_cookies=tuple(cookies or ()),
                live_cookies=tuple(self._live_cookies()),
                headers=headers,
                user_agent=self._current_user_agent(),
                current_url=active_url,
                source_url=source_url,
                trigger=trigger,
            ))

        collector = BrowserCookieSnapshotCollector(
            self._browser.view.page().profile().cookieStore(),
            domain_filter=spec.domain_filter,
            source_url=source_url,
            debug_pickle_path=spec.debug_pickle_path,
            parent=self._browser,
        )
        append_browser_debug_event(
            "browser.collect_cookies.collector_created",
            current_url=self._browser.view.url().toString(),
            source_url=source_url,
            domain_filter=spec.domain_filter,
            debug_pickle_path=spec.debug_pickle_path,
            trigger=trigger,
        )
        self._cookie_collector = collector
        collector.snapshot_ready.connect(on_snapshot_ready)
        collector.snapshot_ready.connect(lambda *_args: setattr(self, "_cookie_collector", None))
        collector.start()
        append_browser_debug_event(
            "browser.collect_cookies.start_returned",
            current_url=self._browser.view.url().toString(),
            source_url=source_url,
            domain_filter=spec.domain_filter,
            debug_pickle_path=spec.debug_pickle_path,
            trigger=trigger,
        )

    def invoke_close_handler(self, event) -> None:
        if self._close_handler:
            self._close_handler(self._browser, event)
            self._close_handler = None

    def shutdown(self) -> None:
        self.stop_cookie_watch()
        self._interceptor.clear_request_capture()
        self._doh_proxy_runtime.restore()

    def _current_user_agent(self) -> str:
        return self._browser.profile.httpUserAgent()

    def _start_cookie_watch(
        self,
        *,
        domain_filter: str,
        source_url: str = "",
        debug_pickle_path: str = "",
    ) -> None:
        self.stop_cookie_watch()
        tracker = BrowserLiveCookieTracker(
            self._browser.view.page().profile().cookieStore(),
            domain_filter=domain_filter,
            source_url=source_url,
            debug_pickle_path=debug_pickle_path,
            parent=self._browser,
        )
        self._live_cookie_tracker = tracker
        append_browser_debug_event(
            "browser.live_cookie.configured",
            current_url=self._browser.view.url().toString(),
            source_url=source_url,
            domain_filter=domain_filter,
            debug_pickle_path=debug_pickle_path,
        )
        tracker.start()

    def _live_cookies(self):
        if self._live_cookie_tracker is None:
            return []
        cookies = self._live_cookie_tracker.snapshot()
        append_browser_debug_event(
            "browser.live_cookie.snapshot",
            current_url=self._browser.view.url().toString(),
            cookie_count=len(cookies),
            cookie_names=sorted({cookie.get("name", "") for cookie in cookies if isinstance(cookie, dict)}),
        )
        return cookies

    def stop_cookie_watch(self) -> None:
        if self._live_cookie_tracker is None:
            return
        self._live_cookie_tracker.stop()
        self._live_cookie_tracker.deleteLater()
        self._live_cookie_tracker = None
