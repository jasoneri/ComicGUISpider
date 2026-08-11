from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, QTimer, QUrl
from qfluentwidgets import InfoBarPosition

from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from utils import conf


class LoginPhase(str, Enum):
    """In-window login capture lifecycle only.

    Idle → Capturing → Saving → Idle
    Post-login navigation is a one-shot flag on Capturing, not its own phase.
    """

    Idle = "idle"
    Capturing = "capturing"
    Saving = "saving"


def normalize_cookie_domain(value: str) -> str:
    return str(value or "").strip().lstrip(".").casefold()


def cookie_domain_matches(cookie_domain: str, *, provider_domain: str = "", page_host: str = "") -> bool:
    """登录 cookies 域名过滤：cookie 域等于 provider 域/当前页域，或互为子域后缀。"""
    normalized_cookie_domain = normalize_cookie_domain(cookie_domain)
    if not normalized_cookie_domain:
        return False
    for candidate in (provider_domain, page_host):
        normalized_candidate = normalize_cookie_domain(candidate)
        if not normalized_candidate:
            continue
        if (
            normalized_cookie_domain == normalized_candidate
            or normalized_cookie_domain.endswith(f".{normalized_candidate}")
            or normalized_candidate.endswith(f".{normalized_cookie_domain}")
        ):
            return True
    return False


def is_cookie_collection_degraded(collected: dict, existing: dict) -> bool:
    """收集集是已存 cookie 名集的真子集 → 视为未登录态收集，拒绝覆盖完整登录态。"""
    return (
        bool(existing)
        and bool(collected)
        and set(collected).issubset(existing)
        and len(collected) < len(existing)
    )


def missing_required_cookies(collected: dict, required: tuple) -> tuple:
    """站点必填 cookies 缺失项（保存前完整性校验）。"""
    return tuple(name for name in required if not (collected or {}).get(name))


def decode_cookie_pair(cookie) -> tuple[str, str]:
    name = bytes(cookie.name()).decode("utf-8", "ignore").strip()
    value = bytes(cookie.value()).decode("utf-8", "ignore")
    return name, value


class BrowserLoginController(QObject):
    """BrowserWindow login-mode owner: capture → validate → conf → host finish.

    Entered only by `LoginManager.open_session` after the browser is presented.
    """

    _SAVE_FALLBACK_MS = 800

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._phase = LoginPhase.Idle
        self._provider_name = ""
        self._provider_domains: tuple[str, ...] = ()
        self._required_cookies: tuple[str, ...] = ()
        self._collected_cookies: dict[str, str] = {}
        self._cookie_store = None
        self._post_trigger_cookies: tuple[str, ...] = ()
        self._post_navigate_url = ""
        self._post_navigated = False
        self._save_finalized = False

    @property
    def phase(self) -> LoginPhase:
        return self._phase

    @property
    def is_active(self) -> bool:
        return self._phase is not LoginPhase.Idle

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def enter(self, *, provider_name: str) -> None:
        from utils.website.login import resolve_login_flow

        flow = resolve_login_flow(provider_name)
        if flow is None:
            raise ValueError(f"login flow missing for provider {provider_name!r}")

        self.exit()
        self._provider_name = flow.provider_name
        candidates = flow.cookie_domains or (flow.domain,)
        self._provider_domains = tuple(
            str(domain).lstrip(".").casefold() for domain in candidates if domain
        )
        self._required_cookies = tuple(flow.required_cookies or ())
        self._post_trigger_cookies = tuple(flow.post_login_trigger_cookies or ())
        self._post_navigate_url = str(flow.post_login_navigate_url or "")
        self._post_navigated = False
        self._save_finalized = False
        self._collected_cookies.clear()
        self._wire_capture()
        self._phase = LoginPhase.Capturing
        self._window.window_mode.enter_plain_page_mode(
            window_title="登录",
            ensure_tooltip="保存 Cookies 并关闭浏览器",
        )
        self.apply_context_menu()

    def exit(self) -> None:
        """Clear browser capture only. Host session is released by shutdown/finish_session."""
        self._unwire_capture()
        self._provider_name = ""
        self._provider_domains = ()
        self._required_cookies = ()
        self._collected_cookies.clear()
        self._post_trigger_cookies = ()
        self._post_navigate_url = ""
        self._post_navigated = False
        self._save_finalized = False
        self._phase = LoginPhase.Idle

    def apply_context_menu(self) -> None:
        FluentMonkeyPatch.rbutton_menu_LoginMode(self._window)

    def collect_and_save(self) -> None:
        """右键菜单仅在 Capturing 挂接；Saving 中忽略重复触发。"""
        if self._phase is not LoginPhase.Capturing:
            return

        provider_name = self._provider_name
        required_cookies = self._required_cookies
        page_host = str(self._window.view.url().host() or "").lstrip(".").casefold()
        target_domains = self._provider_domains
        cookies: dict[str, str] = dict(self._collected_cookies)
        cookie_store = self._window.profile.cookieStore()
        self._phase = LoginPhase.Saving
        self._save_finalized = False
        load_all_connected = False

        def matches_domain(cookie_domain: str) -> bool:
            return any(
                cookie_domain_matches(cookie_domain, provider_domain=candidate, page_host=page_host)
                for candidate in target_domains
            )

        def on_cookie_added(cookie) -> None:
            name, value = decode_cookie_pair(cookie)
            if name and matches_domain(str(cookie.domain() or "")):
                cookies[name] = value

        def finalize() -> None:
            nonlocal load_all_connected
            if self._save_finalized:
                return
            self._save_finalized = True
            if load_all_connected:
                cookie_store.cookieAdded.disconnect(on_cookie_added)
                load_all_connected = False
            # Window may have shut down while waiting for loadAllCookies.
            if self._phase is not LoginPhase.Saving:
                return
            if self._finish_save(provider_name, cookies, required_cookies):
                return
            self._phase = LoginPhase.Capturing

        if cookies:
            finalize()
            return
        cookie_store.cookieAdded.connect(on_cookie_added)
        load_all_connected = True
        cookie_store.loadAllCookies()
        QTimer.singleShot(self._SAVE_FALLBACK_MS, finalize)

    def shutdown(self) -> None:
        """Window teardown: drop capture and release host session if still open."""
        was_active = self.is_active
        self.exit()
        if was_active:
            self._window.gui.login_mgr.release_session()

    def _finish_save(
        self,
        provider_name: str,
        cookies: dict[str, str],
        required_cookies: tuple[str, ...],
    ) -> bool:
        if not cookies:
            self._warn("未提取到 cookies，请确认已登录后再点“保存 Cookies 并关闭浏览器”")
            return False

        if required_cookies:
            missing = missing_required_cookies(cookies, required_cookies)
            if missing:
                self._warn(
                    f"登录态不完整，缺少必填 cookies: {', '.join(missing)}。"
                    f"请确认已登录并访问站点页面获取完整登录态后再保存"
                    f"（exhentai 需访问 exhentai.org 由服务器下发 igneous）"
                )
                return False

        existing = conf.cookies.get(provider_name) or {}
        if is_cookie_collection_degraded(cookies, existing):
            self._warn(
                f"检测到未登录状态(仅收集到 {len(cookies)} 个 cookies)，"
                f"已保留现有完整登录态，请登录后再保存"
            )
            return False

        conf.cookies.switch(provider_name)
        conf.cookies.update_current(cookies)
        self._window.gui.login_mgr.finish_session(
            provider_name=provider_name, cookie_count=len(cookies),
        )
        self.exit()
        self._window.close()
        return True

    def _wire_capture(self) -> None:
        self._unwire_capture()
        cookie_store = self._window.profile.cookieStore()
        self._cookie_store = cookie_store
        cookie_store.cookieAdded.connect(self._on_cookie_added)

    def _unwire_capture(self) -> None:
        cookie_store = self._cookie_store
        if cookie_store is None:
            return
        cookie_store.cookieAdded.disconnect(self._on_cookie_added)
        self._cookie_store = None

    def _on_cookie_added(self, cookie) -> None:
        if self._phase is not LoginPhase.Capturing:
            return
        name, value = decode_cookie_pair(cookie)
        if not name:
            return
        if not any(
            cookie_domain_matches(str(cookie.domain() or ""), provider_domain=candidate)
            for candidate in self._provider_domains
        ):
            return
        self._collected_cookies[name] = value
        self._maybe_post_login_navigate(name)

    def _maybe_post_login_navigate(self, cookie_name: str) -> None:
        if self._post_navigated or not self._post_navigate_url:
            return
        if cookie_name not in self._post_trigger_cookies:
            return
        self._post_navigated = True
        self._window.view.load(QUrl(self._post_navigate_url))

    def _warn(self, content: str) -> None:
        CustomInfoBar.show_custom(
            "",
            content,
            parent=self._window,
            _type="WARNING",
            ib_pos=InfoBarPosition.TOP_RIGHT,
        )
