from __future__ import annotations

import threading
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QRect, QTimer, QUrl
from PySide6.QtGui import QGuiApplication

from GUI.core.anim import PopupAnimator
from GUI.core.font import font_color
from utils import conf
from variables import SPIDERS, Spider


SUPPORT_SITES = frozenset({
    Spider.JM, Spider.EHENTAI, Spider.MANGABZ, Spider.NHENTAI,
    Spider.MANHUAGUI, Spider.DM5, Spider.COMICABC,
})


def cookie_inject_domains(flow) -> tuple[str, ...]:
    """登录注入候选域：flow.cookie_domains 优先，否则 provider 域 + 登录页 host。"""
    declared = tuple(flow.cookie_domains or ())
    if declared:
        return tuple(str(domain).lstrip(".").casefold() for domain in declared if domain)

    candidates: set[str] = set()
    if flow.domain:
        candidates.add(str(flow.domain).lstrip(".").casefold())
    login_host = urlsplit(flow.login_url).hostname or ""
    if login_host:
        candidates.add(str(login_host).lstrip(".").casefold())
    return tuple(sorted(candidates))


class LoginManager(QObject):
    """Host login product owner.

    Boundaries (compound, not one blob):
    - Site chrome: loginBtn visibility + optional silent probe (generation only).
    - Session: non-empty `_session_provider` after browser login mode is entered.
    - Browser capture/save: `BrowserWindow.login_controller` only.

    Probe is orthogonal to session. Do not fold probe into a shared phase enum.
    """

    def __init__(self, gui):
        super().__init__(gui)
        self._gui = gui
        self._session_provider = ""
        self._probe_generation = 0

    @property
    def session_active(self) -> bool:
        return bool(self._session_provider)

    @property
    def session_provider(self) -> str:
        return self._session_provider

    def bind(self) -> None:
        self._gui.loginBtn.clicked.connect(self.open_session)

    def on_site_changed(self, site_index: int) -> None:
        supported = site_index in SUPPORT_SITES
        self._gui.loginBtn.setVisible(supported)
        self._probe_generation += 1
        if supported:
            self._probe_current_site()

    def open_session(self) -> None:
        """loginBtn only: visibility already limits this to SUPPORT_SITES + live runtime."""
        from utils.website.login import resolve_login_flow, resolve_login_open_target

        flow = resolve_login_flow(self._gui.gui_site_runtime.name)
        target = resolve_login_open_target(
            flow, saved_cookies=conf.cookies.get(flow.provider_name) or {},
        )
        if target.hint:
            self._gui.say(font_color(target.hint, cls="theme-warning"), ignore_http=True)
        if target.blocked or not target.url:
            return

        browser_window = self._present_browser()
        self._inject_saved_cookies(browser_window, flow)
        # Capture must be live before navigation so cookieAdded is not missed.
        browser_window.login_controller.enter(provider_name=flow.provider_name)
        self._session_provider = flow.provider_name
        browser_window.view.load(QUrl(target.url))

    def release_session(self) -> None:
        """Browser login left without product finish (window close / cancel)."""
        self._session_provider = ""

    def finish_session(self, *, provider_name: str, cookie_count: int) -> None:
        """Browser save success only. Rebuild runtime so cookies snapshot is current."""
        self.release_session()
        self._gui.say(
            font_color(
                f"已保存 {provider_name} cookies ({cookie_count} 个)到配置",
                cls="theme-highlight",
            ),
            ignore_http=True,
        )
        current_index = self._gui.chooseBox.currentIndex()
        self._gui.gui_site_runtime = self._gui._create_gui_site_runtime(current_index)

    def _present_browser(self):
        gui = self._gui
        screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
        rect = QRect(gui.x(), int(screen_height * 0.05), gui.width(), int(screen_height * 0.9))
        if not gui.BrowserWindow:
            gui.set_preview(rect, skip_env_mode=gui.gui_site_runtime.site_index not in SPIDERS)
        else:
            gui.BrowserWindow.setGeometry(rect)
            # Login open always has a live site runtime; refresh conf cookies into the profile.
            gui.BrowserWindow.apply_standard_environment()
        PopupAnimator.show(gui.BrowserWindow, gui.BrowserWindow.geometry(), duration_ms=220, direction="right")
        return gui.BrowserWindow

    @staticmethod
    def _inject_saved_cookies(browser_window, flow) -> None:
        from GUI.core.browser.runtime import apply_cookie_sets
        from GUI.core.browser.types import BrowserCookieSet

        saved_cookies = conf.cookies.get(flow.provider_name) or {}
        if not saved_cookies:
            return
        cookie_sets = tuple(
            BrowserCookieSet(values=saved_cookies, domain=domain, url=f"https://{domain}/")
            for domain in cookie_inject_domains(flow)
        )
        apply_cookie_sets(browser_window.profile.cookieStore(), cookie_sets)

    def _probe_current_site(self) -> None:
        """Optional background check; generation cancels stale replies. Not a session phase."""
        from utils.website.login import resolve_login_flow, run_login_check

        provider_name = self._gui.gui_site_runtime.name
        flow = resolve_login_flow(provider_name)
        if flow is None or flow.check_login is None:
            return
        if not (conf.cookies.get(provider_name) or {}):
            return

        generation = self._probe_generation
        label = flow.label

        def worker() -> None:
            result = run_login_check(provider_name, conf_state=conf)
            if result.get("status") != "fail":
                return
            QTimer.singleShot(0, lambda: self._announce_stale_login(generation, label))

        threading.Thread(target=worker, daemon=True).start()

    def _announce_stale_login(self, generation: int, label: str) -> None:
        if generation != self._probe_generation:
            return
        self._gui.say(
            font_color(f"{label} 登录态已失效，点击登录按钮重新登录", cls="theme-warning"),
            ignore_http=True,
        )
