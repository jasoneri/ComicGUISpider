#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, QTimer
from qfluentwidgets import FluentIcon as FIF, ToolButton, ImageLabel

from GUI.uic.ui_mainwindow import Ui_MainWindow
from GUI.uic.qfluent.components import TextBrowserWithBg
from assets import res as ori_res
from variables import VER

res = ori_res.GUI.Uic


class MitmMainWindow(Ui_MainWindow):
    def setupUi(self, _mainWindow):
        _translate = QtCore.QCoreApplication.translate
        super(MitmMainWindow, self).setupUi(_mainWindow)
        _mainWindow.setWindowTitle(_translate("MainWindow", f"ComicGUISpider {VER}"))
        self.retrybtn.setDisabled(True)
        self.clipBtn.setDisabled(1)
        self.searchinput.setClearButtonEnabled(1)
        # self._repaint_textBrowser()
        self.preset()
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(0, _translate("MainWindow", res.chooseBoxDefault))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(1, _translate("MainWindow", "1、拷贝漫画"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(2, _translate("MainWindow", "2、jm🔞"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(3, _translate("MainWindow", "3、wnacg🔞"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(4, _translate("MainWindow", "4、ehentai🔞"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(5, _translate("MainWindow", "5、Māngabz"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(6, _translate("MainWindow", "6、hitomi🔞"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(7, _translate("MainWindow", "7、kemono🔞"))
        self.chooseBox.addItem("")
        self.chooseBox.setItemText(8, _translate("MainWindow", "8、h-comic🔞"))
        self.chooseBox.setCurrentIndex(0)
        self.searchinput.setPlaceholderText(_translate("MainWindow", res.searchinputPlaceholderText))
        self.chooseBox.setToolTip(_translate("MainWindow", res.chooseBoxToolTip))
        self.previewBtn.setStatusTip(_translate("MainWindow", res.previewBtnStatusTip))
        self.progressBar.setStatusTip(_translate("MainWindow", res.progressBarStatusTip))
        self.setup_bubble_widget()

    def setup_bubble_widget(self):
        self.bubbleLabel = ImageLabel(self.tbWidget)
        self.bubbleLabel.setObjectName("bubbleLabel")
        self.bubbleLabel.setImage(':/speak.svg')
        self.bubbleBasePixmap = self.bubbleLabel.pixmap()
        self.bubbleLabel.show()
        self.bubbleLabel.lower()
        self.textBrowser.raise_()
        self.textBrowser.setStyleSheet("background: transparent; border: none;")
        QTimer.singleShot(0, self._refresh_bubble_label_size)

    def setup_sleep_widget(self, _img=None):
        self.sleepLabel = ImageLabel(self.sleepWidget)
        self.sleepLabel.setObjectName("sleepLabel")
        self.sleepLabel.setImage(_img or "docs/public/cgs_sleep.png")
        self.sleepLabel.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.sleepLabel.setScaledContents(True)
        self.sleepBasePixmap = self.sleepLabel.pixmap()
        QTimer.singleShot(0, self._refresh_sleep_label_size)

    def resizeEvent(self, event):
        QtWidgets.QMainWindow.resizeEvent(self, event)
        self._refresh_bubble_label_size()
        self._refresh_sleep_label_size()

    def _refresh_bubble_label_size(self):
        label = getattr(self, 'bubbleLabel', None)
        pixmap = getattr(self, 'bubbleBasePixmap', None)
        target_width = self.tbWidget.width()
        target_height = self.tbWidget.height()
        scaled = pixmap.scaled(target_width, target_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        label.setFixedSize(target_width, target_height)
        label.move(0, 0)
        label.lower()

    def _refresh_sleep_label_size(self):
        sw = self.sleepWidget.width()
        act_h = int(sw * (self.sleepBasePixmap.height() / self.sleepBasePixmap.width()))
        self.sleepLabel.setFixedSize(sw, act_h)
        self.sleepLabel.move(0, max(0, self.sleepWidget.height()-act_h))

    def _repaint_textBrowser(self):
        if getattr(self, 'textBrowser', None):
            self.textBrowser.setParent(None)
            self.textBrowser.deleteLater()
        self.textBrowser = TextBrowserWithBg(self)
        self.textBrowser.setMinimumSize(QtCore.QSize(200, 350))
        self.textBrowser.setObjectName("textBrowser")
        self.funcLayout.insertWidget(0, self.textBrowser)

    def preset(self):
        self.openPBtn = ToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.openPBtn.setSizePolicy(sizePolicy)
        self.openPBtn.setMinimumSize(QtCore.QSize(55, 0))
        self.openPBtn.setObjectName("openPBtn")
        self.openPBtn.setIcon(FIF.FOLDER)
        self.toolVLayout.insertWidget(0, self.openPBtn)
