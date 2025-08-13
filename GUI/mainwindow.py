#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5 import QtCore

from GUI.uic.ui_mainwindow import Ui_MainWindow
from GUI.uic.qfluent.components import TextBrowserWithBg
from assets import res as ori_res


res = ori_res.GUI.Uic


class MitmMainWindow(Ui_MainWindow):
    def setupUi(self, _mainWindow):
        _translate = QtCore.QCoreApplication.translate
        super(MitmMainWindow, self).setupUi(_mainWindow)
        _mainWindow.setWindowTitle(_translate("MainWindow", "ComicGUISpider v2.4.0-beta.3"))
        self.retrybtn.setDisabled(True)
        self.clipBtn.setDisabled(1)
        self.searchinput.setClearButtonEnabled(1)
        self.chooseinput.setClearButtonEnabled(1)
        self._repaint_textBrowser()
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
        self.chooseBox.setCurrentIndex(0)
        self.checkisopen.setText(_translate("MainWindow", res.checkisopenDefaultText))
        self.searchinput.setPlaceholderText(_translate("MainWindow", res.searchinputPlaceholderText))
        self.chooseinput.setPlaceholderText(_translate("MainWindow", res.chooseinputPlaceholderText))
        self.next_btn.setText(_translate("MainWindow", res.next_btnDefaultText))
        self.chooseinput.setStatusTip(_translate("MainWindow", res.chooseinputTip))
        self.chooseBox.setToolTip(_translate("MainWindow", res.chooseBoxToolTip))
        self.previewBtn.setStatusTip(_translate("MainWindow", res.previewBtnStatusTip))
        self.progressBar.setStatusTip(_translate("MainWindow", res.progressBarStatusTip))

    def _repaint_textBrowser(self):
        if getattr(self, 'textBrowser', None):
            self.textBrowser.setParent(None)
            self.textBrowser.deleteLater()
        self.textBrowser = TextBrowserWithBg(self.centralwidget)
        self.textBrowser.setMinimumSize(QtCore.QSize(200, 350))
        self.textBrowser.setObjectName("textBrowser")
        self.funcLayout.insertWidget(0, self.textBrowser)
