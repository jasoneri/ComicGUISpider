#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from GUI.core.timer import safe_single_shot
from PyQt5.QtWidgets import QStackedLayout, QWidget, QVBoxLayout, QSizePolicy
from qfluentwidgets import (
    FluentIcon as FIF, ToolButton, ImageLabel, TransparentToolButton, ScrollArea, FlowLayout
)

from GUI.uic.ui_mainwindow import Ui_MainWindow
from GUI.uic.qfluent.components import TextBrowserLite, FlexImageLabel, ExpandButton
from assets import res as ori_res
from variables import VER
from utils import ori_path

res = ori_res.GUI.Uic


class MitmMainWindow(Ui_MainWindow):
    def setupUi(self, _mainWindow):
        _translate = QtCore.QCoreApplication.translate
        super(MitmMainWindow, self).setupUi(_mainWindow)
        _mainWindow.setWindowTitle(_translate("MainWindow", f"ComicGUISpider {VER}"))
        self.preset()

    def apply_translations(self):
        """依赖 res 翻译的文案设置，延迟到 set_language 之后调用"""
        _translate = QtCore.QCoreApplication.translate
        self.searchinput.setClearButtonEnabled(1)
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

    # === bg and bubble.svg

    def _mk_overlay(self, parent, name, image, *, init=None, lower=False):
        label = ImageLabel(parent)
        label.setObjectName(name)
        label.setImage(image)
        if init:
            init(label)
        pixmap = label.pixmap()
        label.show()
        if lower:
            label.lower()
        return label, pixmap

    def setup_bubble_widget(self):
        self._repaint_textBrowser()
        
        if hasattr(self, "tbWidgetLayout") and self.textBrowser.parent() is self.tbWidget:
            self.tbWidgetLayout.removeWidget(self.textBrowser)
        self.tbWidgetStackHost = QWidget(self.tbWidget)
        self.tbWidgetStackHost.setMinimumHeight(140)
        self.tbWidgetStackHost.setObjectName("tbWidgetStackHost")
        self.tbWidgetStackedLayout = QStackedLayout(self.tbWidgetStackHost)
        self.tbWidgetStackedLayout.setObjectName("tbWidgetStackedLayout")
        self.tbWidgetStackedLayout.setContentsMargins(0, 0, 0, 0)
        self.tbWidgetStackedLayout.setStackingMode(QStackedLayout.StackAll)
        self.bubbleLabel = FlexImageLabel(self.tbWidgetStackHost)
        self.bubbleLabel.setObjectName("bubbleLabel")
        self.bubbleLabel.setImage(':/speak.svg')
        self.bubbleLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.bubbleLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.tbWidgetStackedLayout.addWidget(self.bubbleLabel)
        contentWidget = QWidget(self.tbWidgetStackHost)
        contentWidget.setAttribute(Qt.WA_TranslucentBackground)
        contentLayout = QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(10,7,16,7)
        contentLayout.setSpacing(0)
        contentLayout.addWidget(self.textBrowser)
        self.tbWidgetStackedLayout.addWidget(contentWidget)

        self.tbWidgetStackedLayout.setCurrentWidget(contentWidget)
        if hasattr(self, "tbWidgetLayout"):
            self.tbWidgetLayout.addWidget(self.tbWidgetStackHost)

        self.textBrowser.setStyleSheet("background: transparent; border: none;")

    def setup_sleep_widget(self, _img=None):
        self.sleepLabel, self.sleepBasePixmap = self._mk_overlay(
            self.sleepWidget, "sleepLabel", _img or str(ori_path.joinpath("docs/public/cgs_sleep.png")),
            init=lambda l: (l.setAlignment(Qt.AlignLeft | Qt.AlignBottom), l.setScaledContents(True)),
        )
        safe_single_shot(0, self._sync_sleep_widget_geometry)

    def resizeEvent(self, event):
        QtWidgets.QMainWindow.resizeEvent(self, event)
        self._refresh_sleep_label_size()

    def _sync_sleep_widget_geometry(self):
        self._refresh_sleep_label_size()
        h = self.height() + self.sleepLabel.height() - self.sleepWidget.height()
        self.resize(self.width(), min(h, self.maximumHeight()))

    def _refresh_sleep_label_size(self):
        if not getattr(self, "sleepLabel", None) or not getattr(self, "sleepBasePixmap", None):
            return
        sw = self.sleepWidget.width()
        act_h = int(sw * (self.sleepBasePixmap.height() / self.sleepBasePixmap.width()))
        self.sleepLabel.setFixedSize(sw, act_h)
        self.sleepLabel.move(0, max(0, self.sleepWidget.height()-act_h))

    # ===

    def _repaint_textBrowser(self):
        if getattr(self, 'textBrowser', None):
            self.textBrowser.setParent(None)
            self.textBrowser.deleteLater()
        self.textBrowser = TextBrowserLite(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.textBrowser.sizePolicy().hasHeightForWidth())
        self.textBrowser.setSizePolicy(sizePolicy)
        self.textBrowser.setMinimumSize(QtCore.QSize(20, 140))
        self.textBrowser.setObjectName("textBrowser")
        self.tbWidgetLayout.addWidget(self.textBrowser)

    def preset(self):
        self.retrybtn.setDisabled(True)
        self.clipBtn.setDisabled(1)
        self.aggrBtn.setVisible(False)
        
        self.openPBtn = ToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.openPBtn.setSizePolicy(sizePolicy)
        self.openPBtn.setMinimumSize(QtCore.QSize(40, 0))
        self.openPBtn.setObjectName("openPBtn")
        self.openPBtn.setIcon(FIF.FOLDER)
        self.toolVLayout.insertWidget(0, self.openPBtn)

    def task_init(self):
        self.expandBtn = ExpandButton(self)
        self.clearBtn = TransparentToolButton(FIF.BROOM)

        self.scroll_content = QWidget()
        self.flow_layout = FlowLayout(self.scroll_content)
        self.flow_layout.setContentsMargins(4, 4, 4, 4)
        self.flow_layout.setHorizontalSpacing(8)
        self.flow_layout.setVerticalSpacing(8)

        self.scroll_area = ScrollArea()
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setWidgetResizable(True)

        self.barHLayout.insertWidget(0, self.expandBtn)
        self.barHLayout.addWidget(self.clearBtn)
        self.barVLayout.addWidget(self.scroll_area)

        self.expandBtn.setVisible(False)
        self.clearBtn.setVisible(False)
        self.scroll_area.setVisible(False)
