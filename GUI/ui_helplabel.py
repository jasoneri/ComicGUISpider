# -*- coding: utf-8 -*-
from PyQt5.QtCore import QRect
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel


class Ui_HelpLabel(QLabel):
    def __init__(self, parent=None):
        super(Ui_HelpLabel, self).__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.setGeometry(QRect(10, 8, 680, 390))
        self.setPixmap(QPixmap(":/help.jpg"))
        self.setScaledContents(True)
        self.setObjectName("helplabel")
        self.hide()

    def re_pic(self):
        self.setPixmap(QPixmap(":/help2.jpg"))
