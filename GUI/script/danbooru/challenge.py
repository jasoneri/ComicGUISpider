from __future__ import annotations

import typing as t

from PySide6 import QtCore
from qfluentwidgets import InfoBar

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


class DanbooruChallengeController(QtCore.QObject):
    def __init__(self, interface: "DanbooruInterface"):
        super().__init__(interface)
        self.interface = interface
        self.coordinator = BrowserChallengeCoordinator(
            window_factory=lambda: BrowserWindow(self.interface._host_gui(), skip_env_mode=True),
            on_success=self._handle_success,
            on_missing=self._handle_missing,
            parent=self,
        )

    def submit(
        self,
        tab_id: str,
        challenge: DanbooruChallengeRequired,
        retry_callback: t.Callable[[], None],
        *,
        reason: str,
        retry_key: str,
    ) -> None:
        normalized_reason = str(reason or "请求").strip() or "请求"
        self.interface._set_tab_tip(tab_id, f"Danbooru {normalized_reason}需要网页验证，完成后会自动重试", cls="theme-tip")
        self.coordinator.submit(
            self._build_spec(challenge),
            tab_id=tab_id,
            retry_key=str(retry_key or f"{tab_id}:{normalized_reason}"),
            retry_callback=retry_callback,
        )

    def _build_spec(self, challenge: DanbooruChallengeRequired) -> BrowserChallengeSpec:
        return BrowserChallengeSpec(
            challenge.verify_url,
            domain_filter="danbooru.donmai.us",
            source_url=challenge.verify_url,
            doh_url=cgs_cfg.get_doh_url(),
            window_size=QtCore.QSize(980, 760),
            window_title="Danbooru Verification",
            completion_detector=DanbooruResponseInspector.is_verification_completion_url,
            request_capture=BrowserRequestCaptureConfig(host_filter="danbooru.donmai.us"),
            poll_interval_ms=500,
            result_validator=self._has_syncable_session,
        )

    @staticmethod
    def _build_session(result: BrowserChallengeResult) -> DanbooruBrowserSession:
        merged_cookies = DanbooruBrowserSession.merge_cookies(
            list(result.live_cookies),
            list(result.snapshot_cookies),
        )
        headers = dict(result.headers or {})
        effective_source_url = result.source_url or result.current_url or DANBOORU_BASE_URL
        if effective_source_url and "referer" not in {name.casefold() for name in headers}:
            headers["Referer"] = effective_source_url
        return DanbooruBrowserSession.from_browser_capture(
            cookies=merged_cookies,
            user_agent=result.user_agent,
            headers=headers,
            source_url=effective_source_url,
        )

    def _has_syncable_session(self, result: BrowserChallengeResult) -> bool:
        return self._build_session(result).has_clearance_cookie

    def _handle_missing(self, result: BrowserChallengeResult, tab_ids: list[str]) -> None:
        logger = self.interface._gui_logger()
        if logger is not None:
            logger.warning(
                f"[Danbooru] browser verification transfer missing trigger={result.trigger} "
                f"current_url={result.current_url or '<unknown>'}"
            )
        for tab_id in tab_ids:
            self.interface._set_tab_tip(tab_id, "验证页已返回，但没有采集到可回灌的 Cloudflare Cookie", cls="theme-err")
        self.interface._show_info(InfoBar.warning, "Danbooru 验证页已返回，但没有采集到可回灌的 Cloudflare Cookie", 5000)

    def _handle_success(
        self,
        result: BrowserChallengeResult,
        retry_callbacks: list[t.Callable[[], None]],
        tab_ids: list[str],
    ) -> None:
        session = self._build_session(result)
        session = danbooru_browser_session_store.update(
            cookies=session.cookies,
            user_agent=session.user_agent,
            headers=session.headers,
            source_url=session.source_url,
        )
        logger = self.interface._gui_logger()
        if logger is not None:
            logger.info(
                f"[Danbooru] browser verification session synced cookies={len(session.cookies)} "
                f"headers={len(session.headers)} retries={len(retry_callbacks)} "
                f"current_url={result.current_url or '<unknown>'}"
            )
        for tab_id in tab_ids:
            cookie_text = f"{len(session.cookies)} 个 Cookie" if session.cookies else "0 个 Cookie"
            header_text = f"{len(session.headers)} 个 Header"
            self.interface._set_tab_tip(tab_id, f"已同步浏览器验证态({cookie_text}, {header_text})，正在重试", cls="theme-success")
        self.interface._show_info(InfoBar.success, "Danbooru 浏览器验证态已同步，正在重试请求", 4000)
        for retry_callback in retry_callbacks:
            retry_callback()
