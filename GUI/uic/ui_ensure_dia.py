# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_ensure_dia.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


# from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QSize, QCoreApplication, QMetaObject, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QTextEdit, QDialogButtonBox


class Ui_FinEnsureDialog(object):
    def setupUi(self, FinEnsureDialog):
        FinEnsureDialog.setObjectName("FinEnsureDialog")
        FinEnsureDialog.resize(500, 410)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(FinEnsureDialog.sizePolicy().hasHeightForWidth())
        FinEnsureDialog.setSizePolicy(sizePolicy)
        FinEnsureDialog.setMinimumSize(QSize(500, 410))
        FinEnsureDialog.setMaximumSize(QSize(750, 410))
        self.verticalLayout = QVBoxLayout(FinEnsureDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.textEdit = QTextEdit(FinEnsureDialog)
        self.textEdit.setMinimumSize(QSize(0, 330))
        font = QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(11)
        font.setBold(True)
        font.setWeight(75)
        self.textEdit.setFont(font)
        self.textEdit.setFocusPolicy(Qt.ClickFocus)
        self.textEdit.setObjectName("textEdit")
        self.verticalLayout.addWidget(self.textEdit)
        self.buttonBox = QDialogButtonBox(FinEnsureDialog)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(48)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.buttonBox.sizePolicy().hasHeightForWidth())
        self.buttonBox.setSizePolicy(sizePolicy)
        self.buttonBox.setOrientation(Qt.Vertical)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(FinEnsureDialog)
        self.buttonBox.accepted.connect(FinEnsureDialog.accept)
        self.buttonBox.rejected.connect(FinEnsureDialog.reject)
        QMetaObject.connectSlotsByName(FinEnsureDialog)

    def retranslateUi(self, FinEnsureDialog):
        _translate = QCoreApplication.translate
        FinEnsureDialog.setWindowTitle(_translate("FinEnsureDialog", "Dialog"))
