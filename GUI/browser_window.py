#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtNetwork
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from qfluentwidgets import InfoBar, InfoBarPosition, FluentIcon as FIF
from qframelesswindow.webengine import FramelessWebEngineView

from GUI.uic.browser import Ui_browser
from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from assets import res
from utils import conf
from utils.website import EHentaiKits
from utils.processed_class import CopyUnfinished


class BrowserWindow(QMainWindow, Ui_browser):
    eh_kits = None

    def __init__(self, gui, tf, parent=None, proxies: str = None):
        super(BrowserWindow, self).__init__(parent)
        if proxies:
            self.set_proxies(proxies)
        self.gui = gui
        self.tf = tf
        self.view = FramelessWebEngineView(self)
        self.home_url = QUrl.fromLocalFile(self.tf)
        self.view.load(self.home_url)
        self.output = []
        self.setupUi(self)

    def setupUi(self, _window):
        super(BrowserWindow, self).setupUi(_window)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.topHintBox.clicked.connect(self.keep_top_hint)
        self.set_btn()
        self.set_html()
        FluentMonkeyPatch.rbutton_menu_WebEngine(self)

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
        self.homeBtn.clicked.connect(lambda: self.view.load(self.home_url))
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
                duration=2500, parent=self
            )
        self.copyBtn.clicked.connect(copyUnfinishedTasks)

    def set_html(self):
        self.horizontalLayout.addWidget(self.view)
        self.view.urlChanged.connect(lambda _url: self.addressEdit.setText(_url.toString()))

    def second_init(self, tf):
        """翻页时，页面变更tf文件，需要刷新"""
        self.tf = tf
        self.home_url = QUrl.fromLocalFile(self.tf)
        self.view.load(self.home_url)

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
            self.output = list(map(int, ret)) if ret else []
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

    def set_ehentai(self):
        for key, values in conf.eh_cookies.items():
            my_cookie = QNetworkCookie()
            my_cookie.setName(key.encode())
            my_cookie.setValue(str(values).encode())
            my_cookie.setDomain(EHentaiKits.domain)
            self.view.page().profile().cookieStore().setCookie(my_cookie, QUrl(EHentaiKits.index))

    @classmethod
    def check_ehentai(cls, window):
        if not conf.eh_cookies:
            InfoBar.error(
                title='', content=res.EHentai.COOKIES_NOT_SET,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=-1, parent=window.textBrowser
            )
            return
        cls.eh_kits = EHentaiKits(conf)
        if not cls.eh_kits.test_index():
            CustomInfoBar.show('', res.EHentai.ACCESS_FAIL, window.textBrowser,
                cls.eh_kits.index, cls.eh_kits.name)
            return
        return True

    def tmp_sv_local(self):
        def refresh_tf(html):
            if html:
                with open(self.tf, 'w', encoding='utf-8') as f:
                    f.write(html)

        self.js_execute("get_curr_hml();", refresh_tf)

    # ---子任务模块
    def init_task_panel(self, callback):
        self.js_execute("initTaskPanel();", lambda _: callback())

    def add_task(self, tasks_obj):
        _js_code = f"""addTask('{tasks_obj.taskid}', `{tasks_obj.title}`, `{tasks_obj.tasks_count}`, `{tasks_obj.title_url}`);"""
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
