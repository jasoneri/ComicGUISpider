#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtCore

from GUI.uic.ui_mainwindow import Ui_MainWindow
from assets import res as ori_res


res = ori_res.GUI.Uic


class MitmMainWindow(Ui_MainWindow):
    def setupUi(self, _mainWindow):
        _translate = QtCore.QCoreApplication.translate
        super(MitmMainWindow, self).setupUi(_mainWindow)
        _mainWindow.setWindowTitle(_translate("MainWindow", "ComicGUISpider v2.0.0"))
        self.retrybtn.setDisabled(True)
        self.chooseinput.setStatusTip(_translate("MainWindow", res.chooseinputTip))
        self.chooseBox.setToolTip(_translate("MainWindow", res.chooseBoxToolTip))
        self.previewBtn.setStatusTip(_translate("MainWindow", res.previewBtnStatusTip))
        self.progressBar.setStatusTip(_translate("MainWindow", res.progressBarStatusTip))
