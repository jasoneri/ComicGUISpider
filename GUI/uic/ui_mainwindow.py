# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_mainwindow.ui'
##
## Created by: Qt User Interface Compiler version 6.11.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QMainWindow, QSizePolicy, QStatusBar,
    QToolButton, QVBoxLayout, QWidget)
from qfluentwidgets import CheckBox, ComboBox, CompactSpinBox, LineEdit, ProgressBar, TextBrowser, TextEdit
from GUI.uic.qfluent.components.icons import CgsIcon

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(800, 350)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainWindow.sizePolicy().hasHeightForWidth())
        MainWindow.setSizePolicy(sizePolicy)
        MainWindow.setMinimumSize(QSize(800, 350))
        MainWindow.setMaximumSize(QSize(1200, 655))
        font = QFont()
        font.setFamilies([u"\u5fae\u8f6f\u96c5\u9ed1"])
        MainWindow.setFont(font)
        MainWindow.setFocusPolicy(Qt.StrongFocus)
        icon = QIcon()
        icon.addFile(u":/CGS-logo.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainWindow.setWindowIcon(icon)
        MainWindow.setToolTipDuration(2)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_4 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.showArea = QWidget(self.centralwidget)
        self.showArea.setObjectName(u"showArea")
        sizePolicy.setHeightForWidth(self.showArea.sizePolicy().hasHeightForWidth())
        self.showArea.setSizePolicy(sizePolicy)
        self.verticalLayout_5 = QVBoxLayout(self.showArea)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.tbWidget = QWidget(self.showArea)
        self.tbWidget.setObjectName(u"tbWidget")
        sizePolicy.setHeightForWidth(self.tbWidget.sizePolicy().hasHeightForWidth())
        self.tbWidget.setSizePolicy(sizePolicy)
        self.tbWidgetLayout = QVBoxLayout(self.tbWidget)
        self.tbWidgetLayout.setObjectName(u"tbWidgetLayout")
        self.tbWidgetLayout.setContentsMargins(10, 7, 16, 7)
        self.textBrowser = TextBrowser(self.tbWidget)
        self.textBrowser.setObjectName(u"textBrowser")
        sizePolicy.setHeightForWidth(self.textBrowser.sizePolicy().hasHeightForWidth())
        self.textBrowser.setSizePolicy(sizePolicy)
        self.textBrowser.setMinimumSize(QSize(20, 140))
        font1 = QFont()
        font1.setPointSize(11)
        font1.setBold(False)
        self.textBrowser.setFont(font1)

        self.tbWidgetLayout.addWidget(self.textBrowser)


        self.horizontalLayout_4.addWidget(self.tbWidget)

        self.sleepWidget = QWidget(self.showArea)
        self.sleepWidget.setObjectName(u"sleepWidget")
        sizePolicy.setHeightForWidth(self.sleepWidget.sizePolicy().hasHeightForWidth())
        self.sleepWidget.setSizePolicy(sizePolicy)
        self.sleepWidget.setMinimumSize(QSize(250, 0))
        self.sleepWidget.setMaximumSize(QSize(250, 16777215))

        self.horizontalLayout_4.addWidget(self.sleepWidget)


        self.verticalLayout_5.addLayout(self.horizontalLayout_4)


        self.verticalLayout_2.addWidget(self.showArea)

        self.funcLayout = QVBoxLayout()
        self.funcLayout.setSpacing(2)
        self.funcLayout.setObjectName(u"funcLayout")
        self.funcGroupBox = QGroupBox(self.centralwidget)
        self.funcGroupBox.setObjectName(u"funcGroupBox")
        self.funcGroupBox.setEnabled(True)
        self.funcGroupBox.setMinimumSize(QSize(670, 100))
        self.funcGroupBox.setMaximumSize(QSize(9999, 100))
        self.horizontalLayout_2 = QHBoxLayout(self.funcGroupBox)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 1, 5, 1)
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.frame = QFrame(self.funcGroupBox)
        self.frame.setObjectName(u"frame")
        self.gridLayout = QGridLayout(self.frame)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setVerticalSpacing(3)
        self.gridLayout.setContentsMargins(0, 1, 0, 1)
        self.horizontalLayout_input = QHBoxLayout()
        self.horizontalLayout_input.setSpacing(0)
        self.horizontalLayout_input.setObjectName(u"horizontalLayout_input")
        self.chooseBox = ComboBox(self.frame)
        self.chooseBox.setObjectName(u"chooseBox")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.chooseBox.sizePolicy().hasHeightForWidth())
        self.chooseBox.setSizePolicy(sizePolicy1)
        self.chooseBox.setMaximumSize(QSize(16777215, 70))
        font2 = QFont()
        font2.setFamilies([u"\u5fae\u8f6f\u96c5\u9ed1"])
        font2.setPointSize(13)
        font2.setBold(True)
        font2.setItalic(False)
        font2.setUnderline(False)
        font2.setStrikeOut(False)
        font2.setKerning(True)
        self.chooseBox.setFont(font2)
        self.chooseBox.setStyleSheet(u"border-radius: 10px;")

        self.horizontalLayout_input.addWidget(self.chooseBox)

        self.pageFrame = QFrame(self.frame)
        self.pageFrame.setObjectName(u"pageFrame")
        self.pageFrame.setEnabled(False)
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.pageFrame.sizePolicy().hasHeightForWidth())
        self.pageFrame.setSizePolicy(sizePolicy2)
        self.pageFrame.setStyleSheet(u"QToolButton { background-color: rgb(127, 127, 127); }")
        self.Layout_page = QHBoxLayout(self.pageFrame)
        self.Layout_page.setSpacing(0)
        self.Layout_page.setObjectName(u"Layout_page")
        self.Layout_page.setContentsMargins(0, 0, 0, 0)
        self.previousPageBtn = QToolButton(self.pageFrame)
        self.previousPageBtn.setObjectName(u"previousPageBtn")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.previousPageBtn.sizePolicy().hasHeightForWidth())
        self.previousPageBtn.setSizePolicy(sizePolicy3)
        icon1 = QIcon()
        icon1.addFile(u":/page/previous_page.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.previousPageBtn.setIcon(icon1)
        self.previousPageBtn.setIconSize(QSize(25, 25))
        self.previousPageBtn.setAutoRaise(True)

        self.Layout_page.addWidget(self.previousPageBtn)

        self.nextPageBtn = QToolButton(self.pageFrame)
        self.nextPageBtn.setObjectName(u"nextPageBtn")
        sizePolicy3.setHeightForWidth(self.nextPageBtn.sizePolicy().hasHeightForWidth())
        self.nextPageBtn.setSizePolicy(sizePolicy3)
        icon2 = QIcon()
        icon2.addFile(u":/page/next_page.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.nextPageBtn.setIcon(icon2)
        self.nextPageBtn.setIconSize(QSize(25, 25))
        self.nextPageBtn.setAutoRaise(True)

        self.Layout_page.addWidget(self.nextPageBtn)

        self.line_6 = QFrame(self.pageFrame)
        self.line_6.setObjectName(u"line_6")
        self.line_6.setFrameShape(QFrame.Shape.VLine)
        self.line_6.setFrameShadow(QFrame.Shadow.Sunken)

        self.Layout_page.addWidget(self.line_6)

        self.verticalLayoutPageJump = QVBoxLayout()
        self.verticalLayoutPageJump.setSpacing(2)
        self.verticalLayoutPageJump.setObjectName(u"verticalLayoutPageJump")
        self.pageEdit = CompactSpinBox(self.pageFrame)
        self.pageEdit.setObjectName(u"pageEdit")
        sizePolicy2.setHeightForWidth(self.pageEdit.sizePolicy().hasHeightForWidth())
        self.pageEdit.setSizePolicy(sizePolicy2)
        self.pageEdit.setMinimum(1)
        self.pageEdit.setMaximum(9999)

        self.verticalLayoutPageJump.addWidget(self.pageEdit)

        self.pageJumpBtn = QToolButton(self.pageFrame)
        self.pageJumpBtn.setObjectName(u"pageJumpBtn")
        self.pageJumpBtn.setEnabled(False)
        sizePolicy2.setHeightForWidth(self.pageJumpBtn.sizePolicy().hasHeightForWidth())
        self.pageJumpBtn.setSizePolicy(sizePolicy2)
        self.pageJumpBtn.setMaximumSize(QSize(16777215, 20))
        icon3 = QIcon()
        icon3.addFile(u":/page/jump_page.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.pageJumpBtn.setIcon(icon3)
        self.pageJumpBtn.setIconSize(QSize(20, 20))
        self.pageJumpBtn.setAutoRaise(True)

        self.verticalLayoutPageJump.addWidget(self.pageJumpBtn)


        self.Layout_page.addLayout(self.verticalLayoutPageJump)


        self.horizontalLayout_input.addWidget(self.pageFrame)

        self.verticalLayout_3 = QVBoxLayout()
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.rvBtn = QToolButton(self.frame)
        self.rvBtn.setObjectName(u"rvBtn")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.rvBtn.sizePolicy().hasHeightForWidth())
        self.rvBtn.setSizePolicy(sizePolicy4)
        self.rvBtn.setStyleSheet(u"QToolButton {padding: 0px;}")
        icon4 = QIcon()
        icon4.addFile(u":/tools/rv.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.rvBtn.setIcon(icon4)
        self.rvBtn.setIconSize(QSize(50, 50))
        self.rvBtn.setAutoRaise(True)

        self.verticalLayout_3.addWidget(self.rvBtn)


        self.horizontalLayout_input.addLayout(self.verticalLayout_3)


        self.gridLayout.addLayout(self.horizontalLayout_input, 0, 0, 1, 1)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setSpacing(3)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.searchinput = LineEdit(self.frame)
        self.searchinput.setObjectName(u"searchinput")
        self.searchinput.setEnabled(False)
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy5.setHorizontalStretch(40)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.searchinput.sizePolicy().hasHeightForWidth())
        self.searchinput.setSizePolicy(sizePolicy5)
        self.searchinput.setMaximumSize(QSize(9999, 70))
        font3 = QFont()
        font3.setFamilies([u"\u5fae\u8f6f\u96c5\u9ed1"])
        font3.setPointSize(13)
        self.searchinput.setFont(font3)
        self.searchinput.setFocusPolicy(Qt.StrongFocus)
        self.searchinput.setToolTipDuration(-1)
        self.searchinput.setFrame(False)
        self.searchinput.setClearButtonEnabled(True)

        self.horizontalLayout_3.addWidget(self.searchinput)

        self.aggrBtn = QToolButton(self.frame)
        self.aggrBtn.setObjectName(u"aggrBtn")
        sizePolicy.setHeightForWidth(self.aggrBtn.sizePolicy().hasHeightForWidth())
        self.aggrBtn.setSizePolicy(sizePolicy)
        self.aggrBtn.setMinimumSize(QSize(55, 0))
        self.aggrBtn.setStyleSheet(u"QToolButton {\n"
"    background-color: rgb(79, 238, 153);\n"
"    border-radius: 7px;\n"
"}")
        icon5 = QIcon()
        icon5.addFile(u":/tools/aggr.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.aggrBtn.setIcon(icon5)
        self.aggrBtn.setIconSize(QSize(28, 28))
        self.aggrBtn.setPopupMode(QToolButton.InstantPopup)
        self.aggrBtn.setAutoRaise(True)

        self.horizontalLayout_3.addWidget(self.aggrBtn)

        self.clipBtn = QToolButton(self.frame)
        self.clipBtn.setObjectName(u"clipBtn")
        sizePolicy.setHeightForWidth(self.clipBtn.sizePolicy().hasHeightForWidth())
        self.clipBtn.setSizePolicy(sizePolicy)
        self.clipBtn.setMinimumSize(QSize(55, 0))
        self.clipBtn.setStyleSheet(u"QToolButton {\n"
"    background-color: rgb(255, 170, 0);\n"
"    border-radius: 7px;\n"
"}")
        icon6 = QIcon()
        icon6.addFile(u":/tools/clip.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.clipBtn.setIcon(icon6)
        self.clipBtn.setIconSize(QSize(25, 25))
        self.clipBtn.setPopupMode(QToolButton.InstantPopup)
        self.clipBtn.setAutoRaise(True)

        self.horizontalLayout_3.addWidget(self.clipBtn)

        self.htBtn = QToolButton(self.frame)
        self.htBtn.setObjectName(u"htBtn")
        sizePolicy.setHeightForWidth(self.htBtn.sizePolicy().hasHeightForWidth())
        self.htBtn.setSizePolicy(sizePolicy)
        self.htBtn.setMinimumSize(QSize(55, 0))
        self.htBtn.setStyleSheet(u"QToolButton {\n"
"    background-color: rgb(230, 94, 245);\n"
"    border-radius: 7px;\n"
"}")
        icon7 = QIcon()
        icon7.addFile(u":/tools/ht.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.htBtn.setIcon(icon7)
        self.htBtn.setIconSize(QSize(25, 25))
        self.htBtn.setPopupMode(QToolButton.InstantPopup)
        self.htBtn.setAutoRaise(True)

        self.horizontalLayout_3.addWidget(self.htBtn)


        self.gridLayout.addLayout(self.horizontalLayout_3, 2, 0, 1, 1)


        self.horizontalLayout.addWidget(self.frame)

        self.line_4 = QFrame(self.funcGroupBox)
        self.line_4.setObjectName(u"line_4")
        self.line_4.setFrameShape(QFrame.Shape.VLine)
        self.line_4.setFrameShadow(QFrame.Shadow.Sunken)

        self.horizontalLayout.addWidget(self.line_4)

        self.toolWidget = QWidget(self.funcGroupBox)
        self.toolWidget.setObjectName(u"toolWidget")
        sizePolicy3.setHeightForWidth(self.toolWidget.sizePolicy().hasHeightForWidth())
        self.toolWidget.setSizePolicy(sizePolicy3)
        self.toolWidget.setMinimumSize(QSize(35, 0))
        self.verticalLayout = QVBoxLayout(self.toolWidget)
        self.verticalLayout.setSpacing(3)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.toolVLayout = QVBoxLayout()
        self.toolVLayout.setObjectName(u"toolVLayout")
        self.confBtn = QToolButton(self.toolWidget)
        self.confBtn.setObjectName(u"confBtn")
        sizePolicy.setHeightForWidth(self.confBtn.sizePolicy().hasHeightForWidth())
        self.confBtn.setSizePolicy(sizePolicy)
        self.confBtn.setStyleSheet(u"QToolButton {\n"
"	background-color: rgb(0, 255, 255);\n"
"     border-radius: 7px;\n"
"}")
        icon8 = QIcon()
        icon8.addFile(u":/tools/config_icon.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.confBtn.setIcon(icon8)
        self.confBtn.setIconSize(QSize(18, 18))

        self.toolVLayout.addWidget(self.confBtn)

        self.retrybtn = QToolButton(self.toolWidget)
        self.retrybtn.setObjectName(u"retrybtn")
        sizePolicy.setHeightForWidth(self.retrybtn.sizePolicy().hasHeightForWidth())
        self.retrybtn.setSizePolicy(sizePolicy)
        self.retrybtn.setStyleSheet(u"QToolButton {\n"
"	background-color: rgb(208, 208, 156);\n"
"    border-radius: 7px;\n"
"}")
        self.retrybtn.setIcon(CgsIcon.REBOOT.fixed_light_surface_icon())
        self.retrybtn.setIconSize(QSize(18, 18))
        self.retrybtn.setPopupMode(QToolButton.InstantPopup)
        self.retrybtn.setAutoRaise(True)

        self.toolVLayout.addWidget(self.retrybtn)


        self.verticalLayout.addLayout(self.toolVLayout)


        self.horizontalLayout.addWidget(self.toolWidget)


        self.horizontalLayout_2.addLayout(self.horizontalLayout)

        self.line_5 = QFrame(self.funcGroupBox)
        self.line_5.setObjectName(u"line_5")
        self.line_5.setFrameShape(QFrame.Shape.VLine)
        self.line_5.setFrameShadow(QFrame.Shadow.Sunken)

        self.horizontalLayout_2.addWidget(self.line_5)

        self.verticalLayout_9 = QVBoxLayout()
        self.verticalLayout_9.setSpacing(0)
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.previewBtn = QToolButton(self.funcGroupBox)
        self.previewBtn.setObjectName(u"previewBtn")
        sizePolicy2.setHeightForWidth(self.previewBtn.sizePolicy().hasHeightForWidth())
        self.previewBtn.setSizePolicy(sizePolicy2)
        self.previewBtn.setMinimumSize(QSize(65, 60))
        self.previewBtn.setMaximumSize(QSize(65, 110))
        self.previewBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.previewBtn.setFocusPolicy(Qt.StrongFocus)
        icon10 = QIcon()
        icon10.addFile(u":/previewBtn.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.previewBtn.setIcon(icon10)
        self.previewBtn.setIconSize(QSize(65, 65))
        self.previewBtn.setChecked(False)
        self.previewBtn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.previewBtn.setAutoRaise(True)

        self.verticalLayout_9.addWidget(self.previewBtn)

        self.mpreviewBtn = QToolButton(self.funcGroupBox)
        self.mpreviewBtn.setObjectName(u"mpreviewBtn")
        sizePolicy2.setHeightForWidth(self.mpreviewBtn.sizePolicy().hasHeightForWidth())
        self.mpreviewBtn.setSizePolicy(sizePolicy2)
        self.mpreviewBtn.setMinimumSize(QSize(65, 60))
        self.mpreviewBtn.setMaximumSize(QSize(65, 110))
        self.mpreviewBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.mpreviewBtn.setFocusPolicy(Qt.StrongFocus)
        icon11 = QIcon()
        icon11.addFile(u":/mPreviewBtn.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.mpreviewBtn.setIcon(icon11)
        self.mpreviewBtn.setIconSize(QSize(65, 65))
        self.mpreviewBtn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.mpreviewBtn.setAutoRaise(True)

        self.verticalLayout_9.addWidget(self.mpreviewBtn)


        self.horizontalLayout_2.addLayout(self.verticalLayout_9)


        self.funcLayout.addWidget(self.funcGroupBox)

        self.barVLayout = QVBoxLayout()
        self.barVLayout.setSpacing(6)
        self.barVLayout.setObjectName(u"barVLayout")
        self.barVLayout.setContentsMargins(-1, 4, -1, -1)
        self.barHLayout = QHBoxLayout()
        self.barHLayout.setObjectName(u"barHLayout")
        self.progressBar = ProgressBar(self.centralwidget)
        self.progressBar.setObjectName(u"progressBar")

        self.barHLayout.addWidget(self.progressBar)


        self.barVLayout.addLayout(self.barHLayout)


        self.funcLayout.addLayout(self.barVLayout)


        self.verticalLayout_2.addLayout(self.funcLayout)


        self.verticalLayout_4.addLayout(self.verticalLayout_2)

        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        font4 = QFont()
        font4.setPointSize(10)
        self.statusbar.setFont(font4)
        MainWindow.setStatusBar(self.statusbar)
        QWidget.setTabOrder(self.previewBtn, self.chooseBox)

        self.retranslateUi(MainWindow)
        self.previewBtn.clicked.connect(MainWindow.show_preview)
        self.chooseBox.currentIndexChanged.connect(self.searchinput.clear)

        self.chooseBox.setCurrentIndex(-1)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"ComicGUISpider v1.6.2", None))
#if QT_CONFIG(tooltip)
        self.previousPageBtn.setToolTip(QCoreApplication.translate("MainWindow", u"previous page/\u4e0a\u4e00\u9875", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.previousPageBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"previous page/\u4e0a\u4e00\u9875", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.nextPageBtn.setToolTip(QCoreApplication.translate("MainWindow", u"next page/\u4e0b\u4e00\u9875", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.nextPageBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"next page/\u4e0b\u4e00\u9875", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.pageEdit.setToolTip(QCoreApplication.translate("MainWindow", u"page of jump/\u7ffb\u9875\u6570", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.pageEdit.setStatusTip(QCoreApplication.translate("MainWindow", u"page of jump/\u7ffb\u9875\u6570", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.pageJumpBtn.setToolTip(QCoreApplication.translate("MainWindow", u"jump page/\u7ffb\u9875", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.pageJumpBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"jump page/\u7ffb\u9875", None))
#endif // QT_CONFIG(statustip)
        self.pageJumpBtn.setText(QCoreApplication.translate("MainWindow", u"jump", None))
#if QT_CONFIG(tooltip)
        self.searchinput.setToolTip("")
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.aggrBtn.setToolTip(QCoreApplication.translate("MainWindow", u"aggrSearch/\u805a\u5408\u641c\u7d22", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.aggrBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"aggrSearch/\u805a\u5408\u641c\u7d22", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.clipBtn.setToolTip(QCoreApplication.translate("MainWindow", u"clip/\u8bfb\u526a\u8d34\u677f", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.clipBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"clip/\u8bfb\u526a\u8d34\u677f", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.htBtn.setToolTip(QCoreApplication.translate("MainWindow", u"hitomiTools", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.htBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"hitomiTools", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.confBtn.setToolTip(QCoreApplication.translate("MainWindow", u"configuration/\u914d\u7f6e", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.confBtn.setStatusTip(QCoreApplication.translate("MainWindow", u"configuration/\u914d\u7f6e", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.retrybtn.setToolTip(QCoreApplication.translate("MainWindow", u"reset-search/\u91cd\u7f6e\u641c\u7d22", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(statustip)
        self.retrybtn.setStatusTip(QCoreApplication.translate("MainWindow", u"reset-search/\u91cd\u7f6e\u641c\u7d22", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(tooltip)
        self.previewBtn.setToolTip(QCoreApplication.translate("MainWindow", u">_<", None))
#endif // QT_CONFIG(tooltip)
        self.previewBtn.setText(QCoreApplication.translate("MainWindow", u"\u641c\u7d22\u5e76\u9884\u89c8", None))
        self.mpreviewBtn.setText(QCoreApplication.translate("MainWindow", u"\u641c\u7d22\u5e76\u9884\u89c8", None))
    # retranslateUi
