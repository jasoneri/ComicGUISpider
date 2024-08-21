# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_mainwindow.ui'
#
# Created by: PyQt5 UI code generator 5.15.10
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1200, 635)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainWindow.sizePolicy().hasHeightForWidth())
        MainWindow.setSizePolicy(sizePolicy)
        MainWindow.setMinimumSize(QtCore.QSize(920, 635))
        MainWindow.setMaximumSize(QtCore.QSize(1400, 730))
        MainWindow.setFocusPolicy(QtCore.Qt.StrongFocus)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/dohnadohna_.png"), QtGui.QIcon.Normal, QtGui.QIcon.On)
        MainWindow.setWindowIcon(icon)
        MainWindow.setToolTipDuration(2)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_6 = QtWidgets.QVBoxLayout(self.centralwidget)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout()
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.funcLayout = QtWidgets.QVBoxLayout()
        self.funcLayout.setObjectName("funcLayout")
        self.textBrowser = QtWidgets.QTextBrowser(self.centralwidget)
        self.textBrowser.setMinimumSize(QtCore.QSize(200, 350))
        self.textBrowser.setMaximumSize(QtCore.QSize(9999, 9999))
        font = QtGui.QFont()
        font.setPointSize(11)
        font.setBold(False)
        font.setWeight(50)
        self.textBrowser.setFont(font)
        self.textBrowser.setObjectName("textBrowser")
        self.funcLayout.addWidget(self.textBrowser)
        self.funcGroupBox = QtWidgets.QGroupBox(self.centralwidget)
        self.funcGroupBox.setEnabled(True)
        self.funcGroupBox.setMinimumSize(QtCore.QSize(670, 130))
        self.funcGroupBox.setMaximumSize(QtCore.QSize(9999, 130))
        self.funcGroupBox.setObjectName("funcGroupBox")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.funcGroupBox)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.frame = QtWidgets.QFrame(self.funcGroupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setMinimumSize(QtCore.QSize(180, 0))
        self.frame.setObjectName("frame")
        self.verticalLayout_8 = QtWidgets.QVBoxLayout(self.frame)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.chooseBox = QtWidgets.QComboBox(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.chooseBox.sizePolicy().hasHeightForWidth())
        self.chooseBox.setSizePolicy(sizePolicy)
        self.chooseBox.setMaximumSize(QtCore.QSize(16777215, 70))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(13)
        font.setBold(True)
        font.setItalic(False)
        font.setUnderline(False)
        font.setWeight(75)
        font.setStrikeOut(False)
        font.setKerning(True)
        self.chooseBox.setFont(font)
        self.chooseBox.setStyleSheet("border-radius: 10px;")
        self.chooseBox.setInputMethodHints(QtCore.Qt.ImhNone)
        self.chooseBox.setObjectName("chooseBox")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.verticalLayout_8.addWidget(self.chooseBox)
        self.verticalLayout_5 = QtWidgets.QVBoxLayout()
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.line_2 = QtWidgets.QFrame(self.frame)
        self.line_2.setEnabled(True)
        self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_2.setObjectName("line_2")
        self.verticalLayout_5.addWidget(self.line_2)
        self.checkisopen = QtWidgets.QCheckBox(self.frame)
        self.checkisopen.setMaximumSize(QtCore.QSize(16777215, 80))
        self.checkisopen.setObjectName("checkisopen")
        self.verticalLayout_5.addWidget(self.checkisopen)
        self.verticalLayout_8.addLayout(self.verticalLayout_5)
        self.horizontalLayout_2.addWidget(self.frame)
        self.line_3 = QtWidgets.QFrame(self.funcGroupBox)
        self.line_3.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_3.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_3.setObjectName("line_3")
        self.horizontalLayout_2.addWidget(self.line_3)
        self.input_field = QtWidgets.QFrame(self.funcGroupBox)
        self.input_field.setObjectName("input_field")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.input_field)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.frame1 = QtWidgets.QFrame(self.input_field)
        self.frame1.setObjectName("frame1")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.frame1)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.searchinput = QtWidgets.QLineEdit(self.frame1)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(40)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.searchinput.sizePolicy().hasHeightForWidth())
        self.searchinput.setSizePolicy(sizePolicy)
        self.searchinput.setMaximumSize(QtCore.QSize(9999, 70))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(13)
        self.searchinput.setFont(font)
        self.searchinput.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.searchinput.setToolTip("")
        self.searchinput.setToolTipDuration(-1)
        self.searchinput.setFrame(False)
        self.searchinput.setClearButtonEnabled(True)
        self.searchinput.setObjectName("searchinput")
        self.verticalLayout_3.addWidget(self.searchinput)
        self.chooseinput = QtWidgets.QLineEdit(self.frame1)
        self.chooseinput.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.chooseinput.sizePolicy().hasHeightForWidth())
        self.chooseinput.setSizePolicy(sizePolicy)
        self.chooseinput.setMaximumSize(QtCore.QSize(9999, 25))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(11)
        self.chooseinput.setFont(font)
        self.chooseinput.setFocusPolicy(QtCore.Qt.NoFocus)
        self.chooseinput.setToolTip("")
        self.chooseinput.setToolTipDuration(-1)
        self.chooseinput.setMaxLength(85)
        self.chooseinput.setFrame(False)
        self.chooseinput.setCursorPosition(85)
        self.chooseinput.setClearButtonEnabled(True)
        self.chooseinput.setObjectName("chooseinput")
        self.verticalLayout_3.addWidget(self.chooseinput)
        self.horizontalLayout.addWidget(self.frame1)
        spacerItem = QtWidgets.QSpacerItem(13, 20, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.horizontalLayout.addItem(spacerItem)
        self.line_4 = QtWidgets.QFrame(self.input_field)
        self.line_4.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_4.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_4.setObjectName("line_4")
        self.horizontalLayout.addWidget(self.line_4)
        self.frame2 = QtWidgets.QFrame(self.input_field)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame2.sizePolicy().hasHeightForWidth())
        self.frame2.setSizePolicy(sizePolicy)
        self.frame2.setMaximumSize(QtCore.QSize(90, 16777215))
        self.frame2.setObjectName("frame2")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.toolButton = QtWidgets.QToolButton(self.frame2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.toolButton.sizePolicy().hasHeightForWidth())
        self.toolButton.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.toolButton.setFont(font)
        self.toolButton.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.toolButton.setStyleSheet("QToolButton {\n"
                                      "    background-color: rgb(255, 170, 0);\n"
                                      "   border-radius: 7px;\n"
                                      "}")
        self.toolButton.setAutoRepeat(False)
        self.toolButton.setAutoExclusive(False)
        self.toolButton.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.toolButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.toolButton.setAutoRaise(False)
        self.toolButton.setArrowType(QtCore.Qt.UpArrow)
        self.toolButton.setObjectName("toolButton")
        self.verticalLayout.addWidget(self.toolButton)
        self.confBtn = QtWidgets.QPushButton(self.frame2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.confBtn.sizePolicy().hasHeightForWidth())
        self.confBtn.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.confBtn.setFont(font)
        self.confBtn.setStyleSheet("QPushButton {\n"
                                   "    background-color: rgb(0, 255, 255);\n"
                                   "    border-radius: 7px;\n"
                                   "}")
        self.confBtn.setAutoDefault(False)
        self.confBtn.setObjectName("confBtn")
        self.verticalLayout.addWidget(self.confBtn)
        self.retrybtn = QtWidgets.QDialogButtonBox(self.frame2)
        self.retrybtn.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.retrybtn.sizePolicy().hasHeightForWidth())
        self.retrybtn.setSizePolicy(sizePolicy)
        self.retrybtn.setMinimumSize(QtCore.QSize(20, 0))
        self.retrybtn.setMaximumSize(QtCore.QSize(100, 16777215))
        self.retrybtn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        self.retrybtn.setWhatsThis("")
        self.retrybtn.setOrientation(QtCore.Qt.Horizontal)
        self.retrybtn.setStandardButtons(QtWidgets.QDialogButtonBox.Retry)
        self.retrybtn.setObjectName("retrybtn")
        self.verticalLayout.addWidget(self.retrybtn)
        self.horizontalLayout.addWidget(self.frame2)
        self.horizontalLayout_2.addWidget(self.input_field)
        self.line_5 = QtWidgets.QFrame(self.funcGroupBox)
        self.line_5.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_5.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_5.setObjectName("line_5")
        self.horizontalLayout_2.addWidget(self.line_5)
        self.verticalLayout_9 = QtWidgets.QVBoxLayout()
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        self.previewBtn = QtWidgets.QToolButton(self.funcGroupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.previewBtn.sizePolicy().hasHeightForWidth())
        self.previewBtn.setSizePolicy(sizePolicy)
        self.previewBtn.setMinimumSize(QtCore.QSize(65, 60))
        self.previewBtn.setMaximumSize(QtCore.QSize(65, 110))
        self.previewBtn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.previewBtn.setFocusPolicy(QtCore.Qt.StrongFocus)
        icon1 = QtGui.QIcon()
        icon1.addPixmap(QtGui.QPixmap(":/help_btn.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.On)
        self.previewBtn.setIcon(icon1)
        self.previewBtn.setIconSize(QtCore.QSize(65, 65))
        self.previewBtn.setCheckable(False)
        self.previewBtn.setChecked(False)
        self.previewBtn.setPopupMode(QtWidgets.QToolButton.DelayedPopup)
        self.previewBtn.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.previewBtn.setAutoRaise(True)
        self.previewBtn.setArrowType(QtCore.Qt.NoArrow)
        self.previewBtn.setObjectName("previewBtn")
        self.verticalLayout_9.addWidget(self.previewBtn)
        self.horizontalLayout_2.addLayout(self.verticalLayout_9)
        self.funcLayout.addWidget(self.funcGroupBox)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setContentsMargins(-1, -1, -1, 0)
        self.horizontalLayout_3.setSpacing(5)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.next_btn = QtWidgets.QCommandLinkButton(self.centralwidget)
        self.next_btn.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.next_btn.sizePolicy().hasHeightForWidth())
        self.next_btn.setSizePolicy(sizePolicy)
        self.next_btn.setMinimumSize(QtCore.QSize(0, 0))
        self.next_btn.setMaximumSize(QtCore.QSize(195, 40))
        self.next_btn.setSizeIncrement(QtCore.QSize(0, 0))
        font = QtGui.QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(12)
        self.next_btn.setFont(font)
        self.next_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.next_btn.setToolTip("")
        self.next_btn.setToolTipDuration(-1)
        self.next_btn.setStatusTip("")
        self.next_btn.setWhatsThis("")
        self.next_btn.setStyleSheet("QCommandLinkButton {\n"
                                    "    background-image: url(:/search_btn2.png);\n"
                                    "    background-color: rgb(74, 222, 109); \n"
                                    "    text-align: center;\n"
                                    "}")
        self.next_btn.setIconSize(QtCore.QSize(50, 25))
        self.next_btn.setCheckable(False)
        self.next_btn.setChecked(False)
        self.next_btn.setAutoRepeat(False)
        self.next_btn.setAutoExclusive(False)
        self.next_btn.setAutoRepeatInterval(300)
        self.next_btn.setObjectName("next_btn")
        self.horizontalLayout_3.addWidget(self.next_btn)
        self.line = QtWidgets.QFrame(self.centralwidget)
        self.line.setFrameShape(QtWidgets.QFrame.VLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line.setObjectName("line")
        self.horizontalLayout_3.addWidget(self.line)
        self.crawl_btn = QtWidgets.QPushButton(self.centralwidget)
        self.crawl_btn.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.crawl_btn.sizePolicy().hasHeightForWidth())
        self.crawl_btn.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(14)
        self.crawl_btn.setFont(font)
        self.crawl_btn.setToolTip("")
        self.crawl_btn.setStyleSheet("QPushButton {\n"
                                     "    background-color: rgb(74, 222, 109);\n"
                                     "    border-radius: 5px;\n"
                                     "}")
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap(":/crawl_btn.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.crawl_btn.setIcon(icon2)
        self.crawl_btn.setIconSize(QtCore.QSize(30, 30))
        self.crawl_btn.setCheckable(True)
        self.crawl_btn.setChecked(False)
        self.crawl_btn.setObjectName("crawl_btn")
        self.horizontalLayout_3.addWidget(self.crawl_btn)
        self.verticalLayout_2.addLayout(self.horizontalLayout_3)
        self.progressBar = QtWidgets.QProgressBar(self.centralwidget)
        font = QtGui.QFont()
        font.setFamily("黑体")
        font.setPointSize(14)
        self.progressBar.setFont(font)
        self.progressBar.setStyleSheet("")
        self.progressBar.setProperty("value", 0)
        self.progressBar.setObjectName("progressBar")
        self.verticalLayout_2.addWidget(self.progressBar)
        self.funcLayout.addLayout(self.verticalLayout_2)
        self.verticalLayout_4.addLayout(self.funcLayout)
        self.verticalLayout_6.addLayout(self.verticalLayout_4)
        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        font = QtGui.QFont()
        font.setPointSize(10)
        self.statusbar.setFont(font)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        self.previewBtn.clicked.connect(MainWindow.show_preview)  # type: ignore
        self.chooseBox.currentIndexChanged['int'].connect(self.searchinput.clear)  # type: ignore
        QtCore.QMetaObject.connectSlotsByName(MainWindow)
        MainWindow.setTabOrder(self.previewBtn, self.chooseBox)
        MainWindow.setTabOrder(self.chooseBox, self.searchinput)
        MainWindow.setTabOrder(self.searchinput, self.next_btn)
        MainWindow.setTabOrder(self.next_btn, self.chooseinput)
        MainWindow.setTabOrder(self.chooseinput, self.next_btn)
        MainWindow.setTabOrder(self.crawl_btn, self.checkisopen)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "ComicGUISpider v1.6.0"))
        self.chooseBox.setToolTip(_translate("MainWindow", "选中网站后看状态栏有输入提示"))
        self.chooseBox.setCurrentText(_translate("MainWindow", "点选一个网站"))
        self.chooseBox.setItemText(0, _translate("MainWindow", "点选一个网站"))
        self.chooseBox.setItemText(1, _translate("MainWindow", "1、拷贝漫画"))
        self.chooseBox.setItemText(2, _translate("MainWindow", "2、jm**"))
        self.chooseBox.setItemText(3, _translate("MainWindow", "3、wnacg**"))
        self.checkisopen.setText(_translate("MainWindow", "(完成后自动)打开存储目录"))
        self.searchinput.setInputMask(
            _translate("MainWindow", "输入关键字：xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"))
        self.searchinput.setText(_translate("MainWindow", "输入关键字："))
        self.chooseinput.setStatusTip(_translate("MainWindow",
                                                 "示例： 0 表示全选(特殊)  |  1 表示单选 1 (类推)  |  7+9 →表示多选 7、9 (加号)  |  3-5 →多选 3、4、5 (减号)  |  1+7-9 →复合多选 1、7、8、9"))
        self.chooseinput.setInputMask(_translate("MainWindow",
                                                 "输入序号：################################################################################"))
        self.chooseinput.setText(_translate("MainWindow", "输入序号："))
        self.next_btn.setText(_translate("MainWindow", "搜索"))
        self.toolButton.setText(_translate("MainWindow", "工具箱.."))
        self.confBtn.setText(_translate("MainWindow", "更改配置"))
        self.retrybtn.setStatusTip(_translate("MainWindow", "重启程序（重启时，会卡个几秒）"))
        self.previewBtn.setToolTip(_translate("MainWindow", ">_<"))
        self.previewBtn.setStatusTip(_translate("MainWindow", "点击打开预览窗口，仅当出现书列表后才能使用"))
        self.previewBtn.setText(_translate("MainWindow", "点我预览\n"
                                                         ">_<"))
        self.next_btn.setText(_translate("MainWindow", "搜索"))
        self.crawl_btn.setText(_translate("MainWindow", "开始爬取！"))
        self.progressBar.setStatusTip(_translate("MainWindow",
                                                 " >>>进度条解读 Ⅰ、进度条蓝色表示后台还在下载中（ 有时进度条会回跳的请无视 ） Ⅱ、 绿色100%表示完成"))
