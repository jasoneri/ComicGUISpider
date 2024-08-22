#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtNetwork
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QMainWindow, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView
from GUI.uic.browser import Ui_browser
from assets import res


class BrowserWindow(QMainWindow, Ui_browser):
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
