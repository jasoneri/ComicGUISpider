#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import re
import json
from PySide6 import QtNetwork
from PySide6.QtCore import Qt, QUrl, QEvent, QSize, Signal, QLoggingCategory
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
from GUI.core.browser.browser_environment import build_browser_environment
from GUI.core.browser.page_runtime import BrowserPageRuntime
from GUI.core.browser.profile import create_browser_window_profile
from GUI.core.browser.types import BrowserChallengeSpec, BrowserEnvironmentConfig
from GUI.core.browser.window_mode import BrowserWindowModeController
from GUI.uic.browser import Ui_browser
from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from GUI.tools import CopyUnfinished
from assets import res
from utils import conf
from utils.website import EHentaiKits
from variables import CGS_DOC

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


class CustomWebEnginePage(QWebEnginePage):
    def createWindow(self, _type):
        new_page = CustomWebEnginePage(self.profile(), self.parent())
        new_page.urlChanged.connect(lambda url: self.setUrl(url) if url.isValid() else None)
        return new_page


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
        zoom_view = getattr(self.view, "setZoomFactor", None)
        if callable(zoom_view):
            zoom_view(factor)
        else:
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

    def __init__(self, gui, *, skip_env_mode: bool = False):
        super(BrowserWindow, self).__init__()
        self.eh_kits = None
        self._set_referer_nterceptor = False
        self._first_show = True
        self.gui = gui
        self.interceptor = BrowserRequestInterceptor(self)
        self.interceptor.configure_monitor_vote_header(
            allowed_origins=("http://localhost:5173", CGS_DOC),
            page_path="/deploy/monitor", header_name="X-CGS-Flag", header_value="cgs-vote",
        )
        self.view = FramelessWebEngineView(self)
        self.profile = create_browser_window_profile(self)
        self.view.setPage(CustomWebEnginePage(self.profile, self.view))
        self.page_runtime = BrowserPageRuntime(self)
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
        apply_cookie_sets(self.profile.cookieStore(), config.cookie_sets)

    def apply_standard_environment(self):
        self.apply_environment(build_browser_environment(self))

    def _set_dev_tools(self):
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self.dev_tools = QWebEngineView()
        self.dev_tools.setWindowTitle("DevTools")
        self.dev_tools.page().setInspectedPage(self.view.page())
        self.dev_tools.show()

    def showEvent(self, event):
        super(BrowserWindow, self).showEvent(event)
        if not self.window_mode.uses_page_scan:
            CustomInfoBar.show_custom('', res.GUI.BrowserWindow_cf_challenge_tip,
                parent=self, _type="INFORMATION", ib_pos=InfoBarPosition.BOTTOM_LEFT)
        if self._first_show:
            self._first_show = False
            self.load_home()

    def setupUi(self, _window):
        super(BrowserWindow, self).setupUi(_window)
        self.titleBar.hide()
        self.groupBox.installEventFilter(self)
        self.topHintBox.clicked.connect(self.keep_top_hint)  # remark: setupUi 期间禁止 keep_top_hint ，不然会造成窗口边缘无法点击伸缩
        self.topHintBox.setIcon(FIF.PIN)
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

        self.homeBtn.clicked.connect(self.load_home)
        self.backBtn.clicked.connect(self.view.back)
        self.forwardBtn.clicked.connect(self.view.forward)
        self.refreshBtn.clicked.connect(self.reload_current_view)
        self.ensureBtn.clicked.connect(lambda: self.ensure(self.window_mode.ensure_callback))
        self.closeBtn.clicked.connect(self.close)

        def copy_unfinished_tasks():
            _ = CopyUnfinished(self.gui.task_mgr.unfinished_tasks)
            _.to_clip()
            InfoBar.success(
                title='Copied Tip', content=self.gui.res.copied_tip % _.length,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=2500, parent=self.view
            )

        self.copyBtn.clicked.connect(copy_unfinished_tasks)
        self.addressEdit.setPlaceholderText("输入链接后回车")
        self.addressEdit.linkSignal.connect(self._handle_address_submit)
        self.addressEdit.returnPressed.connect(self.addressEdit.link)
        self.horizontalLayout.addWidget(self.view)
        self.view.urlChanged.connect(lambda _url: self.addressEdit.setText(_url.toString()))
        for button in (
            self.topHintBox, self.homeBtn, self.backBtn, self.forwardBtn, self.refreshBtn, self.copyBtn, self.ensureBtn,
        ):
            button.installEventFilter(ToolTipFilter(button, showDelay=300, position=ToolTipPosition.TOP))
        if hasattr(self.gui, 'tf') and self.gui.tf and 'publish' in str(self.gui.tf).lower():
            FluentMonkeyPatch.rbutton_menu_PulishPage(self)
        else:
            FluentMonkeyPatch.rbutton_menu_WebEngine(self)
        self._default_window_title = self.windowTitle()
        self._default_ensure_tooltip = self.ensureBtn.toolTip()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "groupBox", None) and event.type() == QEvent.MouseButtonPress:
            child = obj.childAt(event.pos())
            if event.button() == Qt.LeftButton and child is None:
                global_point = event.globalPosition().toPoint()
                startSystemMove(self, global_point)
                return True
        return super().eventFilter(obj, event)

    def set_ensure_handler(self, callback=None, *, result_kind: str = "checked_ids"):
        self.window_mode.reset_standard_mode(
            window_title=self._default_window_title,
            ensure_tooltip=self._default_ensure_tooltip,
        )
        self.window_mode.set_ensure_handler(callback, result_kind=result_kind)

    def set_close_handler(self, callback=None):
        self.window_mode.set_close_handler(callback)

    def log_webengine_diagnostics(self, *, trigger: str):
        merged_rules = []
        seen_rules = set()
        for chunk in (
            os.environ.get("QT_LOGGING_RULES", ""),
            "qt.webenginecontext.debug=true",
            "qt.webengine.compositor.debug=true",
        ):
            for line in str(chunk or "").splitlines():
                normalized = line.strip()
                if normalized and normalized not in seen_rules:
                    seen_rules.add(normalized)
                    merged_rules.append(normalized)
        rules = "\n".join(merged_rules)
        QLoggingCategory.setFilterRules(rules)
        self.page_runtime.log_web_perf(f"webdiag logging_enabled rules={rules!r}")
        env_snapshot = {
            "trigger": trigger,
            "current_url": self.view.url().toString(),
            "home_url": self.home_url.toString(),
            "QSG_RHI_BACKEND": os.environ.get("QSG_RHI_BACKEND", ""),
            "QTWEBENGINE_CHROMIUM_FLAGS": os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
            "QT_LOGGING_RULES": os.environ.get("QT_LOGGING_RULES", ""),
        }
        payload = ", ".join(f"{key}={value!r}" for key, value in env_snapshot.items())
        self.page_runtime.log_web_perf(f"webdiag snapshot {payload}")

    def load_home(self):
        self.page_runtime.prepare_navigation()
        self.view.load(self.home_url)
        if self._set_referer_nterceptor:
            self.profile.setUrlRequestInterceptor(self.interceptor)

    def reload_current_view(self):
        current_url = self.view.url()
        if not (
            getattr(self.gui, "tf", None)
            and current_url.isLocalFile()
            and current_url.toLocalFile() == str(self.gui.tf)
        ):
            self.view.reload()
            return

        def _write_snapshot_and_reload(html):
            if html and getattr(self.gui, "tf", None):
                with open(self.gui.tf, "w", encoding="utf-8") as f:
                    f.write(html)
            self.view.reload()

        self.page_runtime.page_to_html(
            _write_snapshot_and_reload,
            description="browser refresh HTML snapshot",
            error_callback=lambda _exc: self.view.reload(),
        )

    def _handle_address_submit(self, text: str):
        text = str(text or "").strip()
        if not text:
            return
        lowered = text.casefold()
        if lowered == "dev":
            return self._set_dev_tools()
        if lowered == "gpu":
            return self.view.load(QUrl("chrome://gpu"))
        if lowered in {"diag", "webdiag"}:
            self.log_webengine_diagnostics(trigger="address-bar")
            return self.view.load(QUrl("chrome://gpu"))
        target = text if _SCHEME_RE.match(text) else f"https://{text}"
        url = QUrl.fromUserInput(target)
        if url.isValid() and not url.isEmpty():
            self.view.load(url)

    def keep_top_hint(self, _flag: bool = None):
        flag = _flag if _flag is not None else self.topHintBox.isChecked()
        self.topHintBox.setChecked(flag)
        if sys.platform == "win32" and self.isVisible():
            try:
                import win32con
                import win32gui
            except ImportError:
                pass
            else:
                hwnd = int(self.winId())
                insert_after = win32con.HWND_TOPMOST if flag else win32con.HWND_NOTOPMOST
                win32gui.SetWindowPos(
                    hwnd, insert_after, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
                )
                return
        self.setWindowFlag(Qt.WindowStaysOnTopHint, flag)
        if self.isVisible():
            self.show()

    def current_context_selected_text(self) -> str:
        request_getter = getattr(self.view, "lastContextMenuRequest", None)
        request = request_getter() if callable(request_getter) else None
        if request is None:
            return ""
        return (request.selectedText() or "").strip()

    def page(self, after_callback):
        self.page_runtime.collect_ensure_result(
            after_callback,
            result_kind=self.window_mode.ensure_result_kind,
        )

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

    def latest_image_request(self, *, url: str = "", path_suffix: str = "") -> dict:
        return self.interceptor.latest_image_request(url=url, path_suffix=path_suffix)

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
        if not cls.eh_kits.reqer.test_index():
            CustomInfoBar.show('', res.EHentai.ACCESS_FAIL, gui.showArea,
                cls.eh_kits.index, cls.eh_kits.name)
            return
        return True

    def tmp_sv_local(self):
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)

        self.page_runtime.page_to_html(
            refresh_tf, description="browser tmp_sv_local HTML snapshot",
        )

    def show_task_added_toast(self, title: str):
        js_code = f"window.showTaskAddedToast && window.showTaskAddedToast({json.dumps(title)});"
        self.page_runtime.run_js(js_code)

    def closeEvent(self, event):
        self.page_runtime.shutdown()
        self.window_mode.shutdown()
        if self.page_runtime.has_activity:
            self.page_runtime.log_js_metrics("closeEvent")
        self.window_mode.invoke_close_handler(event)
        if not event.isAccepted():
            return
        if getattr(self.gui, "BrowserWindow", None) is self:
            self.gui.BrowserWindow = None
        super().closeEvent(event)
