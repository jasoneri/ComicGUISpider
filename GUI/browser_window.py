#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import json
import contextlib
from PyQt5 import QtNetwork
from PyQt5.QtCore import Qt, QUrl, QEvent, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from qfluentwidgets import InfoBar, InfoBarPosition, FluentIcon as FIF, ToolTipFilter, ToolTipPosition
from qframelesswindow import FramelessMainWindow
from qframelesswindow.webengine import FramelessWebEngineView
from qframelesswindow.utils import startSystemMove

from GUI.uic.browser import Ui_browser
from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from GUI.tools import CopyUnfinished
from GUI.core.theme import theme_mgr, CustTheme
from assets import res
from variables import CN_PREVIEW_NEED_PROXIES_IDXES
from utils import conf
from utils.website import EHentaiKits


class RefererInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self):
        super().__init__()
        self.referer_url = None

    def set_referer_url(self, referer_url):
        self.referer_url = referer_url

    def interceptRequest(self, info):
        if self.referer_url and info.requestUrl().toString().endswith(('png', 'jpg', 'jpeg', 'webp', 'avif')):
            # print(f"[{self.referer_url}]{info.requestUrl().toString()}")
            info.setHttpHeader(b"referer", self.referer_url.encode())


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
        self.setPage(self.createPage())
        self.loadFinished.connect(self._inject_scrollbar_css)
        self.loadProgress.connect(self._on_load_progress)
        theme_mgr.subscribe(self.on_theme_changed)
    
    def _on_load_progress(self, progress):
        if progress >= 10 and not self._injected:
            self._inject_scrollbar_css()
    
    def on_theme_changed(self, _):
        self._inject_scrollbar_css()
    
    def _inject_scrollbar_css(self, _ok=True):
        self._injected = True
        css = self._get_scrollbar_css()
        js = f"""(function(){{
var id='__cgs_scrollbar__',old=document.getElementById(id);
if(old)old.remove();
var s=document.createElement('style');
s.id=id;s.textContent={json.dumps(css)};
(document.head||document.documentElement).appendChild(s);
}})();"""
        self.page().runJavaScript(js)
        self.browser.keep_top_hint(self.browser.topHintBox.isChecked())
        self.browser.updateFrameless()
    
    def _reset_injected(self):
        self._injected = False


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
    def __init__(self, gui, proxies: str = None):
        super(BrowserWindow, self).__init__()
        self.eh_kits = None
        self._set_referer_nterceptor = False
        self._first_show = True
        self.interceptor = RefererInterceptor()
        if proxies:
            self.set_proxies(proxies)
        self.gui = gui
        self.view = CustomFramelessWebEngineView(self)
        self.profile = self.view.page().profile()
        self.profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.home_url = QUrl.fromLocalFile(self.gui.tf)
        self.set_env_mode()
        self.output = []
        self.setupUi(self)
        self.zoom_mgr = ZoomManager(self)

    def set_env_mode(self):
        index = self.gui.chooseBox.currentIndex()
        conf_proxy = (conf.proxies or [None])[0]
        if res.lang == 'zh-CN':  # 中文圈环境
            proxies = None if index not in CN_PREVIEW_NEED_PROXIES_IDXES else \
                conf_proxy
            if proxies:
                BrowserWindow.set_proxies(proxies)
        elif conf_proxy:   # set proxy to browser if proxy exist on conf.yml
            BrowserWindow.set_proxies(conf_proxy)
        if index == 2 and conf.cookies.get("jm"):  # jm
            self.set_cookies("jm")
        elif index == 4:  # e-hentai
            self.set_cookies("ehentai")
        elif index == 6:  # hitomi
            self.set_referer_nterceptor(self.gui.spiderUtils.index)

    def _set_dev_tools(self):
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        self.dev_tools = QWebEngineView()
        self.dev_tools.setWindowTitle("DevTools")
        self.dev_tools.page().setInspectedPage(self.view.page())
        self.dev_tools.show()

    def showEvent(self, event):
        super(BrowserWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self.load_home()

    def setupUi(self, _window):
        super(BrowserWindow, self).setupUi(_window)
        self._setup_frameless_chrome()
        self.topHintBox.clicked.connect(self.keep_top_hint)
        self.set_btn()
        self.set_html()
        self.patch_tip()
        self.set_rbtn_menu()

    def set_rbtn_menu(self):
        if hasattr(self.gui, 'tf') and self.gui.tf:
            if 'publish' in str(self.gui.tf).lower():
                return FluentMonkeyPatch.rbutton_menu_PulishPage(self)
        FluentMonkeyPatch.rbutton_menu_WebEngine(self)

    def _setup_frameless_chrome(self):
        self.titleBar.hide()
        self.groupBox.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "groupBox", None) and event.type() == QEvent.MouseButtonPress \
            and (event.button() == Qt.LeftButton and obj.childAt(event.pos()) is None):
                startSystemMove(self, event.globalPos())
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
        self.ensureBtn.clicked.connect(lambda : self.ensure(self.gui._next))
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

    def set_referer_nterceptor(self, url):
        self._set_referer_nterceptor = True
        self.interceptor.set_referer_url(url)

    def load_home(self):
        self.view._reset_injected()
        self.view.load(self.home_url)
        if self._set_referer_nterceptor:
            self.profile = self.view.page().profile()
            self.profile.setUrlRequestInterceptor(self.interceptor)

    def set_html(self):
        self.horizontalLayout.addWidget(self.view)
        self.view.urlChanged.connect(lambda _url: self.addressEdit.setText(_url.toString()))

    def second_init(self):
        """翻页时，页面变更tf文件，需要刷新"""
        self.home_url = QUrl.fromLocalFile(self.gui.tf)
        self.load_home()

    def keep_top_hint(self, _flag: bool = None):
        flag = _flag if _flag is not None else self.topHintBox.isChecked()
        self.topHintBox.setChecked(flag)
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
                return
        self.setWindowFlag(Qt.WindowStaysOnTopHint, flag)
        if self.isVisible():
            self.show()

    def js_execute(self, js_code, callback):
        page = self.view.page()
        page.runJavaScript(js_code, callback)

    @staticmethod
    def js_execute_by_page(page, js_code, callback):
        page.runJavaScript(js_code, callback)

    def page(self, after_callback):
        def callback(ret):
            self.output = ret or []  # 可能js还没加载好scanChecked导致返回的undefined
            after_callback()

        self.js_execute("scanChecked()", callback)

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

    def set_cookies(self, website):
        match website:
            case "ehentai":
                cookies_item = conf.cookies.get("ehentai").items()
                domain = self.gui.spiderUtils.domain
                url = self.gui.spiderUtils.index
            case "jm":
                cookies_item = conf.cookies.get("jm").items()
                domain = self.gui.spiderUtils.get_domain()
                url = f"https://{domain}"
        for key, values in cookies_item:
            my_cookie = QNetworkCookie()
            my_cookie.setName(key.encode())
            my_cookie.setValue(str(values).encode())
            my_cookie.setDomain(domain)
            self.view.page().profile().cookieStore().setCookie(my_cookie, QUrl(url))

    @classmethod
    def check_ehentai(cls, gui):
        if not conf.cookies.get("ehentai"):
            InfoBar.error(
                title='', content=res.EHentai.COOKIES_NOT_SET,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=-1, parent=gui.textBrowser
            )
            return
        cls.eh_kits = EHentaiKits(conf)
        if not cls.eh_kits.test_index():
            CustomInfoBar.show('', res.EHentai.ACCESS_FAIL, gui.textBrowser,
                cls.eh_kits.index, cls.eh_kits.name)
            return
        return True

    def tmp_sv_local(self):
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)

        self.js_execute("get_curr_hml();", refresh_tf)

    # ---子任务模块
    def init_tasks_progress_panel(self, callback=None):
        def on_init_complete(_):
            self.gui.tf.set_tasks_progress_panel()
            if callback:
                callback()
        self.js_execute("initTaskPanel();", on_init_complete)

    def add_task(self, tasks_obj):
        _js_code = f"""addTask('{tasks_obj.taskid}', `{tasks_obj.display_title}`, `{tasks_obj.tasks_count}`, `{tasks_obj.title_url}`);"""
        js_code = """if (typeof addTask === 'function') {
                %s;
            } else { false; }""" % _js_code
        self.js_execute(js_code, lambda _: None)

    def update_progress(self, taskid, progress, callback):
        _js_code = f"""updateTaskProgress(`{taskid}`, {progress});"""
        js_code = """if (typeof updateTaskProgress === 'function') {
                %s;
            } else { false; }""" % _js_code
        self.js_execute(js_code, lambda _: callback())

    def closeEvent(self, event):
        if hasattr(self, 'view'):  
            theme_mgr.unsubscribe(self.view.on_theme_changed)  
        super().closeEvent(event)
