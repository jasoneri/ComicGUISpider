#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtNetwork
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWidgets import QMainWindow, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView

from GUI.uic.browser import Ui_browser
from assets import res
from utils import conf
from utils.special.ehentai import EHentaiKits


class BrowserWindow(QMainWindow, Ui_browser):
    eh_kits = None

    def __init__(self, tf, parent=None, proxies: str = None):
        super(BrowserWindow, self).__init__(parent)
        if proxies:
            self.set_proxies(proxies)
        self.tf = tf
        self.view = QWebEngineView()
        self.home_url = QUrl.fromLocalFile(self.tf)
        self.view.load(self.home_url)
        self.output = []
        self.setupUi(self)

    def setupUi(self, _window):
        super(BrowserWindow, self).setupUi(_window)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.topHintBox.clicked.connect(self.keep_top_hint)
        # self.ensureBtn.clicked.connect(self.ensure)
        self.set_html()

    def ensure(self, after_callback):
        def callback(ret):
            if not ret:
                QMessageBox.information(self, 'Warning', res.GUI.BrowserWindow_ensure_warning, QMessageBox.Ok)
            else:
                self.output = list(map(int, ret))
                self.close()
                after_callback()

        page = self.view.page()
        page.runJavaScript("""scanChecked()""", callback)

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

    def keep_top_hint(self):
        if self.topHintBox.isChecked():
            self.setWindowFlags(Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(Qt.Widget)
        self.show()

    def set_html(self):
        self.homeBtn.clicked.connect(lambda: self.view.load(self.home_url))
        self.backBtn.clicked.connect(self.view.back)
        self.forwardBtn.clicked.connect(self.view.forward)
        self.refreshBtn.clicked.connect(self.view.reload)
        self.horizontalLayout.addWidget(self.view)
        self.view.urlChanged.connect(lambda _url: self.addressEdit.setText(_url.toString()))

    def set_e_hentai(self):
        def recheck():
            limit = self.eh_kits.get_limit()
            self.limitCntLabel.setText(limit)

        if not conf.eh_cookies:
            QMessageBox.information(self, 'Warning', res.EHentai.COOKIES_NOT_SET, QMessageBox.Ok)
            return
        if not conf.proxies:
            QMessageBox.information(self, 'Warning', res.EHentai.PROXIES_NOT_SET, QMessageBox.Ok)
            return
        self.eh_kits = self.eh_kits or EHentaiKits(conf.eh_cookies, conf.proxies)
        if not self.eh_kits.test_index():
            QMessageBox.information(self, 'Warning', f"{res.EHentai.ACCESS_FAIL} {self.eh_kits.index}")
            return
        recheck()
        self.ehentaiWidget.setEnabled(True)
        self.recheckBtn.clicked.connect(recheck)

        for key, values in conf.eh_cookies.items():
            my_cookie = QNetworkCookie()
            my_cookie.setName(key.encode())
            my_cookie.setValue(str(values).encode())
            my_cookie.setDomain(self.eh_kits.domain)
            self.view.page().profile().cookieStore().setCookie(my_cookie, QUrl(self.eh_kits.index))
