#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import re
import json
import time
import contextlib
from PySide6 import QtNetwork
from PySide6.QtCore import Qt, QUrl, QEvent, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from qfluentwidgets import InfoBar, InfoBarPosition, FluentIcon as FIF, ToolTipFilter, ToolTipPosition
from qframelesswindow import FramelessMainWindow
from qframelesswindow.webengine import FramelessWebEngineView
from qframelesswindow.utils import startSystemMove

from GUI.core.browser.runtime import (
    BrowserRequestInterceptor,
    apply_cookie_sets,
)
from GUI.core.browser.page_runtime import BrowserPageRuntime
from GUI.core.browser.site_runtime import build_browser_environment
from GUI.core.browser.types import BrowserChallengeSpec, BrowserEnvironmentConfig
from GUI.core.browser.window_mode import BrowserWindowModeController
from GUI.types import SearchContextSnapshot
from GUI.uic.browser import Ui_browser
from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from GUI.tools import CopyUnfinished
from GUI.core.theme import theme_mgr, CustTheme
from assets import res
from utils import conf
from utils.website import EHentaiKits

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


class CustomWebEnginePage(QWebEnginePage):
    def createWindow(self, _type):
        new_page = QWebEnginePage(self.profile(), self.parent())
        new_page.urlChanged.connect(lambda url: self.setUrl(url) if url.isValid() else None)
        return new_page


class CustomFramelessWebEngineView(FramelessWebEngineView):
    _SCROLLBAR_CSS_TPL = """::-webkit-scrollbar {{ width: 12px; height: 12px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{
    background: rgba({rgb}, 0.35);
    border-radius: 6px;
    border: 3px solid transparent;
    background-clip: content-box;
}}
::-webkit-scrollbar-thumb:hover {{
    background: rgba({rgb}, 0.55);
    background-clip: content-box;
}}"""
    
    @staticmethod
    def _get_scrollbar_css():
        rgb = "255,255,255" if theme_mgr.get_theme() == CustTheme.DARK else "0,0,0"
        return CustomFramelessWebEngineView._SCROLLBAR_CSS_TPL.format(rgb=rgb)
    
    def createPage(self):
        return CustomWebEnginePage(self.page().profile(), self)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.browser = parent
        self._injected = False
        self._last_injected_css = None
        self.setPage(self.createPage())
        theme_mgr.subscribe(self.on_theme_changed)

    def on_page_ready(self):
        self._inject_scrollbar_css(reason="page-ready")
    
    def on_theme_changed(self, _):
        runtime = getattr(self.browser, "page_runtime", None)
        if runtime is None or not runtime.page_ready:
            return
        self._inject_scrollbar_css(reason="theme-changed")

    def _inject_scrollbar_css(self, _ok=True, *, reason="manual"):
        runtime = getattr(self.browser, "page_runtime", None)
        if runtime is None or not runtime.page_ready:
            if runtime is not None:
                runtime.log_web_perf(f"scrollbar_css skipped reason={reason} page_ready=False")
            return
        self._injected = True
        css = self._get_scrollbar_css()
        if self._last_injected_css == css:
            runtime.log_web_perf(f"scrollbar_css skipped reason={reason} unchanged=True")
            return
        js = f"""(function(){{
var id='__cgs_scrollbar__';
var root=document.head||document.documentElement;
if(!root) return false;
var s=document.getElementById(id);
if(!s){{
  s=document.createElement('style');s.id=id;root.appendChild(s);
}}
if(s.textContent==={json.dumps(css)}) return false;
s.textContent={json.dumps(css)};
return true;
}})();"""
        started_at = time.perf_counter()

        def _log_result(changed):
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            if changed:
                self._last_injected_css = css
                runtime.record_scrollbar_css_injection(reason=reason, elapsed_ms=elapsed_ms)
                return
            runtime.log_web_perf(
                f"scrollbar_css skipped reason={reason} unchanged=True elapsed_ms={elapsed_ms:.1f}"
            )

        self.browser.run_js(js, _log_result, page=self.page())
    
    def _reset_injected(self):
        self._injected = False
        self._last_injected_css = None


class ZoomManager:
    _step = 0.05
    _min = 0.25
    _max = 5.0
    
    def __init__(self, browser):
        self.browser = browser
        self.view = browser.view
        self.gui = browser.gui
        self._current = getattr(self.gui, 'browser_zoom_factor', 1.0)
        self.browser.zoomInBtn.clicked.connect(self._on_zoom_in_clicked)
        self.browser.zoomOutBtn.clicked.connect(self._on_zoom_out_clicked)
        self.view.loadFinished.connect(self._on_load_finished)
    
    @property
    def current(self):
        return self._current
    
    @property
    def can_zoom_in(self):
        return self._current < self._max - 1e-6
    
    @property
    def can_zoom_out(self):
        return self._current > self._min + 1e-6
    
    def set_zoom(self, factor: float):
        factor = round(max(self._min, min(self._max, factor)), 2)
        self._current = factor
        if hasattr(self.gui, 'browser_zoom_factor'):
            self.gui.browser_zoom_factor = factor
        try:
            self.view.setZoomFactor(factor)
        except Exception:
            self.view.page().setZoomFactor(factor)
    
    def reset(self):
        self.set_zoom(1.0)
    
    def _on_load_finished(self, ok: bool):
        if ok:
            self.set_zoom(self._current)

    def _on_zoom_in_clicked(self):
        if self.can_zoom_in:
            self.set_zoom(self._current + self._step)
        self._update_zoom_buttons()
    
    def _on_zoom_out_clicked(self):
        if self.can_zoom_out:
            self.set_zoom(self._current - self._step)
        self._update_zoom_buttons()
    
    def _update_zoom_buttons(self):
        self.browser.zoomInBtn.setEnabled(self.can_zoom_in)
        self.browser.zoomOutBtn.setEnabled(self.can_zoom_out)


class BrowserWindow(FramelessMainWindow, Ui_browser):
    pageInteractive = Signal(str, float)
    pageLoadFinishedDetailed = Signal(bool, float)

    def __init__(self, gui, *, skip_env_mode: bool = False, snapshot: SearchContextSnapshot | None = None):
        super(BrowserWindow, self).__init__()
        self.eh_kits = None
        self._set_referer_nterceptor = False
        self._first_show = True
        self.gui = gui
        self.search_context = snapshot
        self.interceptor = BrowserRequestInterceptor(self)
        self.view = CustomFramelessWebEngineView(self)
        self.page_runtime = BrowserPageRuntime(self)
        self._configure_web_settings()
        self.profile = self.view.page().profile()
        # self.profile.setHttpUserAgent(
        #     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36")
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.window_mode = BrowserWindowModeController(self, self.interceptor)
        preview_file = getattr(self.gui, "tf", None)
        self.home_url = QUrl.fromLocalFile(str(preview_file)) if preview_file else QUrl("about:blank")
        if not skip_env_mode:
            self.apply_standard_environment()
        self.output = []
        self.setupUi(self)
        self.zoom_mgr = ZoomManager(self)

    def _configure_web_settings(self):
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

    def updateFrameless(self):
        runtime = getattr(self, "page_runtime", None)
        if runtime is None:
            return super().updateFrameless()
        return runtime.update_frameless(super().updateFrameless)

    def apply_environment(self, config: BrowserEnvironmentConfig):
        if config.proxy:
            BrowserWindow.set_proxies(config.proxy)
        self._set_referer_nterceptor = bool(config.referer_url)
        self.interceptor.set_referer_url(config.referer_url or None)
        apply_cookie_sets(self.view.page().profile().cookieStore(), config.cookie_sets)

    def apply_standard_environment(self):
        self.apply_environment(build_browser_environment(self.gui, self.search_context))

    def update_search_context(self, snapshot: SearchContextSnapshot | None):
        self.search_context = snapshot
        self.apply_standard_environment()

    def _set_dev_tools(self):
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self.dev_tools = QWebEngineView()
        self.dev_tools.setWindowTitle("DevTools")
        self.dev_tools.page().setInspectedPage(self.view.page())
        self.dev_tools.show()

    def showEvent(self, event):
        super(BrowserWindow, self).showEvent(event)
        self.page_runtime.log_web_perf(
            f"showEvent first_show={self._first_show} visible={self.isVisible()}"
        )
        if self._first_show:
            self._first_show = False
            self.load_home()

    def setupUi(self, _window):
        super(BrowserWindow, self).setupUi(_window)
        self._setup_frameless_chrome()
        self.topHintBox.clicked.connect(self.keep_top_hint)
        self.set_btn()
        self._setup_address_edit()
        self.set_html()
        self.patch_tip()
        self.set_rbtn_menu()
        self._default_window_title = self.windowTitle()
        self._default_ensure_tooltip = self.ensureBtn.toolTip()

    def set_rbtn_menu(self):
        if hasattr(self.gui, 'tf') and self.gui.tf:
            if 'publish' in str(self.gui.tf).lower():
                return FluentMonkeyPatch.rbutton_menu_PulishPage(self)
        FluentMonkeyPatch.rbutton_menu_WebEngine(self)

    def _setup_frameless_chrome(self):
        self.titleBar.hide()
        self.groupBox.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "groupBox", None) and event.type() == QEvent.MouseButtonPress:
            child = obj.childAt(event.pos())
            if event.button() == Qt.LeftButton and child is None:
                global_point = event.globalPosition().toPoint()
                self.page_runtime.log_web_perf(
                    f"startSystemMove local=({event.pos().x()},{event.pos().y()}) "
                    f"global=({global_point.x()},{global_point.y()}) child=<none> "
                    f"page_ready={self.page_runtime.page_ready} url={self.view.url().toString()!r}"
                )
                startSystemMove(self, global_point)
                return True
        return super().eventFilter(obj, event)

    def patch_tip(self):
        for button in (self.topHintBox, self.homeBtn, self.backBtn, self.forwardBtn, self.refreshBtn, self.copyBtn, self.ensureBtn):
            button.installEventFilter(ToolTipFilter(button, showDelay=300, position=ToolTipPosition.TOP))

    def set_btn(self):
        # ui
        self.topHintBox.setIcon(FIF.PIN)
        self.topHintBox.setChecked(True)
        self.homeBtn.setIcon(FIF.HOME)
        self.backBtn.setIcon(FIF.LEFT_ARROW)
        self.forwardBtn.setIcon(FIF.RIGHT_ARROW)
        self.refreshBtn.setIcon(FIF.SYNC)
        self.copyBtn.setIcon(FIF.COPY)
        self.ensureBtn.setIcon(FIF.DOWNLOAD)
        self.zoomInBtn.setIcon(FIF.ZOOM_IN)
        self.zoomOutBtn.setIcon(FIF.ZOOM_OUT)
        self.closeBtn.setIconSize(QSize(20, 20))
        self.closeBtn.setIcon(QIcon(':/close.svg'))
        # logic
        self.homeBtn.clicked.connect(self.load_home)
        self.backBtn.clicked.connect(self.view.back)
        self.forwardBtn.clicked.connect(self.view.forward)
        self.refreshBtn.clicked.connect(self.view.reload)
        self.ensureBtn.clicked.connect(lambda: self.ensure(self.window_mode.ensure_callback))
        self.closeBtn.clicked.connect(self.close)
        def copyUnfinishedTasks():
            _ = CopyUnfinished(self.gui.task_mgr.unfinished_tasks)
            _.to_clip()
            InfoBar.success(
                title='Copied Tip', content=self.gui.res.copied_tip % _.length,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=2500, parent=self.view
            )
        self.copyBtn.clicked.connect(copyUnfinishedTasks)

    def set_ensure_handler(self, callback=None):
        self.window_mode.reset_standard_mode(
            window_title=self._default_window_title,
            ensure_tooltip=self._default_ensure_tooltip,
        )
        self.window_mode.set_ensure_handler(callback)

    def set_close_handler(self, callback=None):
        self.window_mode.set_close_handler(callback)

    def _setup_address_edit(self):
        self.addressEdit.setPlaceholderText("输入链接后回车")
        self.addressEdit.linkSignal.connect(self._handle_address_submit)

    def load_home(self):
        self.page_runtime.prepare_navigation()
        self.view._reset_injected()
        self.view.load(self.home_url)
        if self._set_referer_nterceptor:
            self.profile = self.view.page().profile()
            self.profile.setUrlRequestInterceptor(self.interceptor)

    def set_html(self):
        self.horizontalLayout.addWidget(self.view)
        self.view.urlChanged.connect(lambda _url: self.addressEdit.setText(_url.toString()))

    def _handle_address_submit(self, text: str):
        text = str(text or "").strip()
        if not text:
            return
        if text.casefold() == "dev":
            self._set_dev_tools()
            return
        target = text if _SCHEME_RE.match(text) else f"https://{text}"
        url = QUrl.fromUserInput(target)
        if url.isValid() and not url.isEmpty():
            self.view.load(url)

    def keep_top_hint(self, _flag: bool = None):
        flag = _flag if _flag is not None else self.topHintBox.isChecked()
        self.topHintBox.setChecked(flag)
        started_at = time.perf_counter()
        if sys.platform == "win32" and self.isVisible():
            with contextlib.suppress(Exception):
                import win32con
                import win32gui
                hwnd = int(self.winId())
                insert_after = win32con.HWND_TOPMOST if flag else win32con.HWND_NOTOPMOST
                win32gui.SetWindowPos(
                    hwnd, insert_after, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
                )
                self.page_runtime.record_top_hint(
                    flag=flag,
                    elapsed_ms=(time.perf_counter() - started_at) * 1000,
                )
                return
        self.setWindowFlag(Qt.WindowStaysOnTopHint, flag)
        if self.isVisible():
            self.show()
        self.page_runtime.record_top_hint(
            flag=flag,
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
        )

    def current_context_selected_text(self) -> str:
        request_getter = getattr(self.view, "lastContextMenuRequest", None)
        request = request_getter() if callable(request_getter) else None
        if request is None:
            return ""
        return (request.selectedText() or "").strip()

    def log_js_metrics(self, scope: str, **extra):
        self.page_runtime.log_js_metrics(scope, **extra)

    def run_js(self, js_code, callback=None, *, page=None):
        self.page_runtime.run_js(js_code, callback, page=page)

    def js_execute(self, js_code, callback):
        self.run_js(js_code, callback)

    @staticmethod
    def js_execute_by_page(page, js_code, callback):
        BrowserPageRuntime.js_execute_by_page(page, js_code, callback)

    def run_js_result(
        self, js_body, callback,
        *,
        expected_kind, description, page=None, error_callback=None,
    ):
        self.page_runtime.run_js_result(
            js_body, callback, expected_kind=expected_kind, description=description, page=page, error_callback=error_callback,
        )

    def page_to_html(self, callback, *, page=None, description="page.toHtml()", error_callback=None):
        self.page_runtime.page_to_html(
            callback, page=page, description=description, error_callback=error_callback,
        )

    def page(self, after_callback):
        self.page_runtime.run_page_scan(after_callback, uses_page_scan=self.window_mode.uses_page_scan, )

    ensure = page

    @staticmethod
    def set_proxies(proxy_str):
        """
        :param proxy_str: like 127.0.0.1:8080
        """
        proxy = QtNetwork.QNetworkProxy()
        proxy.setType(QtNetwork.QNetworkProxy.HttpProxy)
        host, port = proxy_str.split(':')
        proxy.setHostName(host)
        proxy.setPort(int(port))
        QtNetwork.QNetworkProxy.setApplicationProxy(proxy)

    @staticmethod
    def clear_proxies():
        proxy = QtNetwork.QNetworkProxy()
        proxy.setType(QtNetwork.QNetworkProxy.NoProxy)
        QtNetwork.QNetworkProxy.setApplicationProxy(proxy)

    def enter_challenge_mode(
        self, spec: BrowserChallengeSpec,
        *,
        ensure_handler=None, close_handler=None,
    ):
        self.window_mode.enter_challenge_mode(
            spec, ensure_handler=ensure_handler, close_handler=close_handler,
        )

    def collect_challenge_result(
        self, spec: BrowserChallengeSpec, callback,
        *,
        current_url: str = "", trigger: str = "manual",
    ):
        self.window_mode.collect_challenge_result(
            spec, callback, current_url=current_url, trigger=trigger,
        )

    @classmethod
    def check_ehentai(cls, gui):
        if not conf.cookies.get("ehentai"):
            InfoBar.error(
                title='', content=res.EHentai.COOKIES_NOT_SET,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=-1, parent=gui.showArea
            )
            return
        cls.eh_kits = EHentaiKits(conf)
        if not cls.eh_kits.test_index():
            CustomInfoBar.show('', res.EHentai.ACCESS_FAIL, gui.showArea,
                cls.eh_kits.index, cls.eh_kits.name)
            return
        return True

    def tmp_sv_local(self):
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)

        self.page_to_html(refresh_tf,description="browser tmp_sv_local HTML snapshot",)

    def show_task_added_toast(self, title: str):
        js_code = f"window.showTaskAddedToast && window.showTaskAddedToast({json.dumps(title)});"
        self.run_js(js_code)

    def closeEvent(self, event):
        if hasattr(self, 'view'):
            theme_mgr.unsubscribe(self.view.on_theme_changed)
        self.page_runtime.shutdown()
        self.window_mode.shutdown()
        if self.page_runtime.has_activity:
            self.log_js_metrics("closeEvent")
        self.window_mode.invoke_close_handler(event)
        if not event.isAccepted():
            return
        if getattr(self.gui, "BrowserWindow", None) is self:
            self.gui.BrowserWindow = None
        super().closeEvent(event)
