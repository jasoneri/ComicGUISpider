#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtNetwork
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from qfluentwidgets import InfoBar, InfoBarPosition, FluentIcon as FIF, ToolTipFilter, ToolTipPosition
from qframelesswindow.webengine import FramelessWebEngineView

from GUI.uic.browser import Ui_browser
from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from GUI.tools import CopyUnfinished
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


class BrowserWindow(QMainWindow, Ui_browser):
    def __init__(self, gui, proxies: str = None):
        super(BrowserWindow, self).__init__()
        self.eh_kits = None
        self._set_referer_nterceptor = False
        self.interceptor = RefererInterceptor()
        if proxies:
            self.set_proxies(proxies)
        self.gui = gui
        self.view = FramelessWebEngineView(self)
        self.profile = self.view.page().profile()
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.home_url = QUrl.fromLocalFile(self.gui.tf)
        self.set_env_mode()
        self.load_home()
        self.output = []
        self.setupUi(self)

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

    def setupUi(self, _window):
        super(BrowserWindow, self).setupUi(_window)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.topHintBox.clicked.connect(self.keep_top_hint)
        self.set_btn()
        self.set_html()
        self.patch_tip()
        FluentMonkeyPatch.rbutton_menu_WebEngine(self)

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
        # logic
        self.homeBtn.clicked.connect(self.load_home)
        self.backBtn.clicked.connect(self.view.back)
        self.forwardBtn.clicked.connect(self.view.forward)
        self.refreshBtn.clicked.connect(self.view.reload)
        self.ensureBtn.clicked.connect(lambda : self.ensure(self.gui._next))
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

    def keep_top_hint(self):
        if self.topHintBox.isChecked():
            self.setWindowFlags(Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(Qt.Widget)
        self.show()

    def js_execute(self, js_code, callback):
        page = self.view.page()
        page.runJavaScript(js_code, callback)

    @staticmethod
    def js_execute_by_page(page, js_code, callback):
        page.runJavaScript(js_code, callback)

    def page(self, after_callback):
        def callback(ret):
            self.output = ret
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
    def init_task_panel(self, callback):
        self.js_execute("initTaskPanel();", lambda _: callback())

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
