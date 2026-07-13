from __future__ import annotations

import typing as t

from PySide6 import QtCore

from GUI.browser_window import BrowserWindow
from GUI.core.browser import (
    BrowserChallengeCoordinator,
    BrowserChallengeResult,
    BrowserChallengeSpec,
    BrowserRequestCaptureConfig,
)
from utils.config.qc import cgs_cfg
from utils.script.image.danbooru.constants import DANBOORU_BASE_URL
from utils.script.image.danbooru.http import DanbooruChallengeRequired, DanbooruResponseInspector
from utils.script.image.danbooru.session import DanbooruBrowserSession, danbooru_browser_session_store

if t.TYPE_CHECKING:
    from .interface import DanbooruInterface

DANBOORU_HTTPX_VERIFY_LIMIT = 3
DANBOORU_HTTPX_VERIFY_TIMEOUT = 20.0


class DanbooruHttpxSessionVerification:
    def __init__(self, interface: "DanbooruInterface", tab_ids: list[str], retry_callbacks: list[t.Callable[[], None]]):
        self.interface = interface
        self.tab_ids = tuple(tab_ids)
        self.retry_callbacks = tuple(retry_callbacks)

    def submit(self) -> None:
        for tab_id in self.tab_ids:
            self.interface.tab_mgr.set_httpx_status(tab_id, "httpx verifying", cls="theme-tip")
        self.interface.task_mgr.execute_simple_task(
            self.run,
            success_callback=self.accept, error_callback=self.reject, show_success_info=False,
            show_error_info=False, show_tooltip=False, task_id=f"danbooru-httpx-verify-{','.join(self.tab_ids)}-{id(self)}",
        )

    def run(self):
        return self.interface.request_client.search_posts(
            "",
            page=1, limit=DANBOORU_HTTPX_VERIFY_LIMIT, timeout=DANBOORU_HTTPX_VERIFY_TIMEOUT,
        )

    def accept(self, posts) -> None:
        for tab_id in self.tab_ids:
            self.interface.tab_mgr.set_httpx_status(tab_id, f"httpx 200/{len(posts or [])}", cls="theme-success")
        for retry_callback in self.retry_callbacks:
            retry_callback()

    def reject(self, error: str) -> None:
        self.interface.gui.log.warning(f"[Danbooru] browser session did not pass Python httpx verification: {error}")
        for tab_id in self.tab_ids:
            self.interface.tab_mgr.set_httpx_status(tab_id, "httpx blocked", cls="theme-err")


class DanbooruChallengeController(QtCore.QObject):
    def __init__(self, interface: "DanbooruInterface"):
        super().__init__(interface)
        self.interface = interface
        self.gui = interface.gui
        self.coordinator = BrowserChallengeCoordinator(
            # CGS002: BrowserWindow starts WebEngine DoH synchronously on the GUI thread.
            window_factory=lambda spec: BrowserWindow(
                self.interface.gui,
                skip_env_mode=True,
                persistent_profile=False,
            ),
            on_success=self._handle_success, on_missing=self._handle_missing, parent=self,
        )

    def submit(self, tab_id: str, challenge: DanbooruChallengeRequired, retry_callback: t.Callable[[], None], retry_key: str) -> None:
        self.interface.tab_mgr.set_httpx_status(tab_id, "httpx blocked", cls="theme-tip")
        self.coordinator.submit(
            self._build_spec(challenge),
            tab_id=tab_id,
            retry_key=str(retry_key),
            retry_callback=retry_callback,
        )

    def _build_spec(self, challenge: DanbooruChallengeRequired) -> BrowserChallengeSpec:
        return BrowserChallengeSpec(
            challenge.verify_url,
            domain_filter="danbooru.donmai.us", source_url=challenge.verify_url, doh_url=cgs_cfg.doh.get_url(),
            window_size=QtCore.QSize(980, 760), window_title="Danbooru Verification",
            completion_detector=DanbooruResponseInspector.is_verification_completion_url,
            request_capture=BrowserRequestCaptureConfig(host_filter="danbooru.donmai.us"), poll_interval_ms=500,
            result_validator=self._has_syncable_session,
        )

    @staticmethod
    def _build_session(result: BrowserChallengeResult) -> DanbooruBrowserSession:
        merged_cookies = DanbooruBrowserSession.merge_cookies(list(result.live_cookies), list(result.snapshot_cookies))
        headers = dict(result.headers or {})
        effective_source_url = result.source_url or result.current_url or DANBOORU_BASE_URL
        if effective_source_url and "referer" not in {name.casefold() for name in headers}:
            headers["Referer"] = effective_source_url
        return DanbooruBrowserSession.from_browser_capture(
            cookies=merged_cookies,
            user_agent=result.user_agent, headers=headers, source_url=effective_source_url,
        )

    def _has_syncable_session(self, result: BrowserChallengeResult) -> bool:
        return self._build_session(result).has_clearance_cookie

    def _handle_missing(self, result: BrowserChallengeResult, tab_ids: list[str]) -> None:
        self.gui.log.warning(
            f"[Danbooru] browser verification transfer missing trigger={result.trigger} "
            f"current_url={result.current_url or '<unknown>'}"
        )
        for tab_id in tab_ids:
            self.interface.tab_mgr.set_httpx_status(tab_id, "httpx blocked", cls="theme-err")

    def _handle_success(self, result: BrowserChallengeResult, retry_callbacks: list[t.Callable[[], None]], tab_ids: list[str]) -> None:
        browser_session = self._build_session(result)
        session = danbooru_browser_session_store.update(
            cookies=browser_session.cookies,
            user_agent=browser_session.user_agent, headers=browser_session.headers, source_url=browser_session.source_url,
        )
        self.gui.log.info(
            f"[Danbooru] browser verification session synced cookies={len(session.cookies)} "
            f"headers={len(session.headers)} retries={len(retry_callbacks)} "
            f"current_url={result.current_url or '<unknown>'}"
        )
        DanbooruHttpxSessionVerification(self.interface, tab_ids, retry_callbacks).submit()
