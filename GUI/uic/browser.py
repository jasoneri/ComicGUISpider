# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'browser.ui'
#
# Created by: PyQt5 UI code generator 5.15.10
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_browser(object):
    def setupUi(self, browser):
        browser.setObjectName("browser")
        browser.resize(1040, 500)
        browser.setMinimumSize(QtCore.QSize(1040, 417))
        browser.setMaximumSize(QtCore.QSize(1375, 16777215))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/dohnadohna_.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        browser.setWindowIcon(icon)
        self.centralwidget = QtWidgets.QWidget(browser)
        self.centralwidget.setMinimumSize(QtCore.QSize(0, 0))
        self.centralwidget.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayout = QtWidgets.QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox = QtWidgets.QGroupBox(self.centralwidget)
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 40))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.groupBox)
        self.horizontalLayout_2.setContentsMargins(-1, 5, -1, 5)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.topHintBox = QtWidgets.QCheckBox(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.topHintBox.sizePolicy().hasHeightForWidth())
        self.topHintBox.setSizePolicy(sizePolicy)
        self.topHintBox.setMinimumSize(QtCore.QSize(0, 0))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        self.topHintBox.setFont(font)
        self.topHintBox.setAutoFillBackground(False)
        self.topHintBox.setStyleSheet("")
        self.topHintBox.setChecked(True)
        self.topHintBox.setObjectName("topHintBox")
        self.horizontalLayout_2.addWidget(self.topHintBox)
        self.line = QtWidgets.QFrame(self.groupBox)
        self.line.setFrameShape(QtWidgets.QFrame.VLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line.setObjectName("line")
        self.horizontalLayout_2.addWidget(self.line)
        self.homeBtn = QtWidgets.QToolButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.homeBtn.sizePolicy().hasHeightForWidth())
        self.homeBtn.setSizePolicy(sizePolicy)
        self.homeBtn.setMinimumSize(QtCore.QSize(0, 0))
        self.homeBtn.setMaximumSize(QtCore.QSize(25, 16777215))
        icon1 = QtGui.QIcon()
        icon1.addPixmap(QtGui.QPixmap(":/home_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        icon1.addPixmap(QtGui.QPixmap(":/home_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.On)
        self.homeBtn.setIcon(icon1)
        self.homeBtn.setIconSize(QtCore.QSize(20, 20))
        self.homeBtn.setAutoRaise(True)
        self.homeBtn.setObjectName("homeBtn")
        self.horizontalLayout_2.addWidget(self.homeBtn)
        self.backBtn = QtWidgets.QToolButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.backBtn.sizePolicy().hasHeightForWidth())
        self.backBtn.setSizePolicy(sizePolicy)
        self.backBtn.setMinimumSize(QtCore.QSize(0, 0))
        self.backBtn.setMaximumSize(QtCore.QSize(25, 16777215))
        self.backBtn.setStatusTip("")
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap(":/arrow_left_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.backBtn.setIcon(icon2)
        self.backBtn.setIconSize(QtCore.QSize(20, 20))
        self.backBtn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.backBtn.setAutoRaise(True)
        self.backBtn.setArrowType(QtCore.Qt.NoArrow)
        self.backBtn.setObjectName("backBtn")
        self.horizontalLayout_2.addWidget(self.backBtn)
        self.forwardBtn = QtWidgets.QToolButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.forwardBtn.sizePolicy().hasHeightForWidth())
        self.forwardBtn.setSizePolicy(sizePolicy)
        self.forwardBtn.setMaximumSize(QtCore.QSize(25, 16777215))
        icon3 = QtGui.QIcon()
        icon3.addPixmap(QtGui.QPixmap(":/arrow_right_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.forwardBtn.setIcon(icon3)
        self.forwardBtn.setIconSize(QtCore.QSize(20, 20))
        self.forwardBtn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.forwardBtn.setAutoRaise(True)
        self.forwardBtn.setArrowType(QtCore.Qt.NoArrow)
        self.forwardBtn.setObjectName("forwardBtn")
        self.horizontalLayout_2.addWidget(self.forwardBtn)
        self.refreshBtn = QtWidgets.QToolButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.refreshBtn.sizePolicy().hasHeightForWidth())
        self.refreshBtn.setSizePolicy(sizePolicy)
        self.refreshBtn.setMaximumSize(QtCore.QSize(25, 16777215))
        icon4 = QtGui.QIcon()
        icon4.addPixmap(QtGui.QPixmap(":/refresh_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.refreshBtn.setIcon(icon4)
        self.refreshBtn.setIconSize(QtCore.QSize(20, 20))
        self.refreshBtn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.refreshBtn.setAutoRaise(True)
        self.refreshBtn.setObjectName("refreshBtn")
        self.horizontalLayout_2.addWidget(self.refreshBtn)
        self.addressEdit = QtWidgets.QLineEdit(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.addressEdit.sizePolicy().hasHeightForWidth())
        self.addressEdit.setSizePolicy(sizePolicy)
        self.addressEdit.setMinimumSize(QtCore.QSize(400, 0))
        self.addressEdit.setObjectName("addressEdit")
        self.horizontalLayout_2.addWidget(self.addressEdit)
        spacerItem = QtWidgets.QSpacerItem(632, 15, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.isRetain = QtWidgets.QCheckBox(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.isRetain.sizePolicy().hasHeightForWidth())
        self.isRetain.setSizePolicy(sizePolicy)
        self.isRetain.setChecked(True)
        self.isRetain.setObjectName("isRetain")
        self.horizontalLayout_2.addWidget(self.isRetain)
        self.ensureBtn = QtWidgets.QToolButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.ensureBtn.sizePolicy().hasHeightForWidth())
        self.ensureBtn.setSizePolicy(sizePolicy)
        self.ensureBtn.setMinimumSize(QtCore.QSize(82, 0))
        self.ensureBtn.setMaximumSize(QtCore.QSize(82, 16777215))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(10)
        font.setBold(True)
        font.setItalic(False)
        font.setUnderline(False)
        font.setWeight(75)
        self.ensureBtn.setFont(font)
        self.ensureBtn.setStyleSheet("QToolButton {\n"
                                     "    background-color: rgb(85, 255, 0);\n"
                                     "    border-radius: 6px;\n"
                                     "}")
        icon5 = QtGui.QIcon()
        icon5.addPixmap(QtGui.QPixmap(":/download_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.ensureBtn.setIcon(icon5)
        self.ensureBtn.setIconSize(QtCore.QSize(16, 16))
        self.ensureBtn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.ensureBtn.setAutoRaise(True)
        self.ensureBtn.setObjectName("ensureBtn")
        self.horizontalLayout_2.addWidget(self.ensureBtn)
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 1)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.gridLayout.addLayout(self.horizontalLayout, 1, 0, 1, 1)
        browser.setCentralWidget(self.centralwidget)

        self.retranslateUi(browser)
        QtCore.QMetaObject.connectSlotsByName(browser)

    def retranslateUi(self, browser):
        _translate = QtCore.QCoreApplication.translate
        browser.setWindowTitle(_translate("browser", "inner browser/内置浏览器"))
        self.topHintBox.setToolTip(_translate("browser", "WindowStaysOnTopHint"))
        self.topHintBox.setText(_translate("browser", "窗口置顶"))
        self.homeBtn.setToolTip(_translate("browser", "home/回到初始页"))
        self.homeBtn.setText(_translate("browser", "..."))
        self.backBtn.setToolTip(_translate("browser", "back/后退"))
        self.backBtn.setText(_translate("browser", "..."))
        self.forwardBtn.setToolTip(_translate("browser", "forward/前进"))
        self.forwardBtn.setText(_translate("browser", "..."))
        self.refreshBtn.setToolTip(_translate("browser", "refresh page/刷新页面"))
        self.refreshBtn.setText(_translate("browser", "..."))
        self.isRetain.setText(_translate("browser", "翻页时保留选择"))
        self.ensureBtn.setToolTip(_translate("browser", "download selected"))
        self.ensureBtn.setText(_translate("browser", "确认选择"))
