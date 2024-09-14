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
        MainWindow.resize(1120, 635)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainWindow.sizePolicy().hasHeightForWidth())
        MainWindow.setSizePolicy(sizePolicy)
        MainWindow.setMinimumSize(QtCore.QSize(1000, 635))
        MainWindow.setMaximumSize(QtCore.QSize(1400, 750))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        MainWindow.setFont(font)
        MainWindow.setFocusPolicy(QtCore.Qt.StrongFocus)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/dohnadohna_.png"), QtGui.QIcon.Normal, QtGui.QIcon.On)
        MainWindow.setWindowIcon(icon)
        MainWindow.setToolTipDuration(2)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_6 = QtWidgets.QVBoxLayout(self.centralwidget)
        self.verticalLayout_6.setContentsMargins(-1, -1, -1, 0)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout()
        self.verticalLayout_4.setContentsMargins(-1, -1, -1, 2)
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
        self.funcGroupBox.setMinimumSize(QtCore.QSize(670, 100))
        self.funcGroupBox.setMaximumSize(QtCore.QSize(9999, 100))
        self.funcGroupBox.setObjectName("funcGroupBox")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.funcGroupBox)
        self.horizontalLayout_2.setContentsMargins(0, 5, 5, 5)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.frame = QtWidgets.QFrame(self.funcGroupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setMinimumSize(QtCore.QSize(193, 0))
        self.frame.setObjectName("frame")
        self.verticalLayout_8 = QtWidgets.QVBoxLayout(self.frame)
        self.verticalLayout_8.setContentsMargins(9, 0, 2, 0)
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
        self.chooseBox.setObjectName("chooseBox")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.chooseBox.addItem("")
        self.verticalLayout_8.addWidget(self.chooseBox)
        self.verticalLayout_5 = QtWidgets.QVBoxLayout()
        self.verticalLayout_5.setSpacing(2)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.line_2 = QtWidgets.QFrame(self.frame)
        self.line_2.setEnabled(True)
        self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_2.setObjectName("line_2")
        self.verticalLayout_5.addWidget(self.line_2)
        self.checkisopen = QtWidgets.QCheckBox(self.frame)
        self.checkisopen.setMaximumSize(QtCore.QSize(16777215, 80))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(9)
        self.checkisopen.setFont(font)
        self.checkisopen.setObjectName("checkisopen")
        self.verticalLayout_5.addWidget(self.checkisopen)
        self.verticalLayout_8.addLayout(self.verticalLayout_5)
        self.horizontalLayout_2.addWidget(self.frame)
        self.line_3 = QtWidgets.QFrame(self.funcGroupBox)
        self.line_3.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_3.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_3.setObjectName("line_3")
        self.horizontalLayout_2.addWidget(self.line_3)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.frame1 = QtWidgets.QFrame(self.funcGroupBox)
        self.frame1.setObjectName("frame1")
        self.gridLayout = QtWidgets.QGridLayout(self.frame1)
        self.gridLayout.setContentsMargins(0, 5, 0, 0)
        self.gridLayout.setVerticalSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout_input = QtWidgets.QHBoxLayout()
        self.horizontalLayout_input.setSpacing(0)
        self.horizontalLayout_input.setObjectName("horizontalLayout_input")
        self.searchinput = QtWidgets.QLineEdit(self.frame1)
        self.searchinput.setEnabled(False)
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
        self.horizontalLayout_input.addWidget(self.searchinput)
        self.pageFrame = QtWidgets.QFrame(self.frame1)
        self.pageFrame.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pageFrame.sizePolicy().hasHeightForWidth())
        self.pageFrame.setSizePolicy(sizePolicy)
        self.pageFrame.setObjectName("pageFrame")
        self.Layout_page = QtWidgets.QHBoxLayout(self.pageFrame)
        self.Layout_page.setContentsMargins(0, 0, 0, 0)
        self.Layout_page.setSpacing(0)
        self.Layout_page.setObjectName("Layout_page")
        self.previousPageBtn = QtWidgets.QToolButton(self.pageFrame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.previousPageBtn.sizePolicy().hasHeightForWidth())
        self.previousPageBtn.setSizePolicy(sizePolicy)
        self.previousPageBtn.setStyleSheet("QToolButton {\n"
                                           "background-color: rgb(255, 255, 255);\n"
                                           "}")
        icon1 = QtGui.QIcon()
        icon1.addPixmap(QtGui.QPixmap(":/previous_page.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.previousPageBtn.setIcon(icon1)
        self.previousPageBtn.setIconSize(QtCore.QSize(25, 25))
        self.previousPageBtn.setAutoRaise(True)
        self.previousPageBtn.setObjectName("previousPageBtn")
        self.Layout_page.addWidget(self.previousPageBtn)
        self.nextPageBtn = QtWidgets.QToolButton(self.pageFrame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.nextPageBtn.sizePolicy().hasHeightForWidth())
        self.nextPageBtn.setSizePolicy(sizePolicy)
        self.nextPageBtn.setStyleSheet("QToolButton {\n"
                                       "background-color: rgb(255, 255, 255);\n"
                                       "}")
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap(":/next_page.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.nextPageBtn.setIcon(icon2)
        self.nextPageBtn.setIconSize(QtCore.QSize(25, 25))
        self.nextPageBtn.setAutoRaise(True)
        self.nextPageBtn.setObjectName("nextPageBtn")
        self.Layout_page.addWidget(self.nextPageBtn)
        self.line_6 = QtWidgets.QFrame(self.pageFrame)
        self.line_6.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_6.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_6.setObjectName("line_6")
        self.Layout_page.addWidget(self.line_6)
        self.verticalLayoutPageJump = QtWidgets.QVBoxLayout()
        self.verticalLayoutPageJump.setSpacing(2)
        self.verticalLayoutPageJump.setObjectName("verticalLayoutPageJump")
        self.pageEdit = QtWidgets.QLineEdit(self.pageFrame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pageEdit.sizePolicy().hasHeightForWidth())
        self.pageEdit.setSizePolicy(sizePolicy)
        self.pageEdit.setMaximumSize(QtCore.QSize(30, 16777215))
        font = QtGui.QFont()
        font.setPointSize(8)
        self.pageEdit.setFont(font)
        self.pageEdit.setFrame(False)
        self.pageEdit.setObjectName("pageEdit")
        self.verticalLayoutPageJump.addWidget(self.pageEdit)
        self.pageJumpBtn = QtWidgets.QToolButton(self.pageFrame)
        self.pageJumpBtn.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pageJumpBtn.sizePolicy().hasHeightForWidth())
        self.pageJumpBtn.setSizePolicy(sizePolicy)
        self.pageJumpBtn.setMaximumSize(QtCore.QSize(16777215, 20))
        self.pageJumpBtn.setStyleSheet("QToolButton {\n"
                                       "background-color: rgb(255, 255, 255);\n"
                                       "}")
        icon3 = QtGui.QIcon()
        icon3.addPixmap(QtGui.QPixmap(":/jump_page.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.pageJumpBtn.setIcon(icon3)
        self.pageJumpBtn.setIconSize(QtCore.QSize(20, 20))
        self.pageJumpBtn.setAutoRaise(True)
        self.pageJumpBtn.setObjectName("pageJumpBtn")
        self.verticalLayoutPageJump.addWidget(self.pageJumpBtn)
        self.Layout_page.addLayout(self.verticalLayoutPageJump)
        self.horizontalLayout_input.addWidget(self.pageFrame)
        self.gridLayout.addLayout(self.horizontalLayout_input, 0, 0, 1, 1)
        self.chooseinput = QtWidgets.QLineEdit(self.frame1)
        self.chooseinput.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.chooseinput.sizePolicy().hasHeightForWidth())
        self.chooseinput.setSizePolicy(sizePolicy)
        self.chooseinput.setMaximumSize(QtCore.QSize(16777215, 30))
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
        self.gridLayout.addWidget(self.chooseinput, 1, 0, 1, 1)
        self.horizontalLayout.addWidget(self.frame1)
        self.line_4 = QtWidgets.QFrame(self.funcGroupBox)
        self.line_4.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_4.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_4.setObjectName("line_4")
        self.horizontalLayout.addWidget(self.line_4)
        self.frame2 = QtWidgets.QFrame(self.funcGroupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame2.sizePolicy().hasHeightForWidth())
        self.frame2.setSizePolicy(sizePolicy)
        self.frame2.setMaximumSize(QtCore.QSize(90, 16777215))
        self.frame2.setObjectName("frame2")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame2)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(3)
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
        self.toolButton.setStyleSheet("QToolButton {\n"
                                      "    background-color: rgb(255, 170, 0);\n"
                                      "    border-radius: 7px;\n"
                                      "    padding-left: 2px;\n"
                                      "}")
        icon4 = QtGui.QIcon()
        icon4.addPixmap(QtGui.QPixmap(":/toolbox_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.toolButton.setIcon(icon4)
        self.toolButton.setIconSize(QtCore.QSize(20, 20))
        self.toolButton.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.toolButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
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
                                   "     border-radius: 7px;\n"
                                   "}")
        icon5 = QtGui.QIcon()
        icon5.addPixmap(QtGui.QPixmap(":/config_icon.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.confBtn.setIcon(icon5)
        self.confBtn.setIconSize(QtCore.QSize(18, 18))
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
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        self.retrybtn.setFont(font)
        self.retrybtn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        self.retrybtn.setWhatsThis("")
        self.retrybtn.setOrientation(QtCore.Qt.Horizontal)
        self.retrybtn.setStandardButtons(QtWidgets.QDialogButtonBox.Retry)
        self.retrybtn.setObjectName("retrybtn")
        self.verticalLayout.addWidget(self.retrybtn)
        self.horizontalLayout.addWidget(self.frame2)
        self.horizontalLayout_2.addLayout(self.horizontalLayout)
        self.line_5 = QtWidgets.QFrame(self.funcGroupBox)
        self.line_5.setFrameShape(QtWidgets.QFrame.VLine)
        self.line_5.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_5.setObjectName("line_5")
        self.horizontalLayout_2.addWidget(self.line_5)
        self.verticalLayout_9 = QtWidgets.QVBoxLayout()
        self.verticalLayout_9.setSpacing(0)
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        self.previewBtn = QtWidgets.QToolButton(self.funcGroupBox)
        self.previewBtn.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.previewBtn.sizePolicy().hasHeightForWidth())
        self.previewBtn.setSizePolicy(sizePolicy)
        self.previewBtn.setMinimumSize(QtCore.QSize(65, 60))
        self.previewBtn.setMaximumSize(QtCore.QSize(65, 110))
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(9)
        self.previewBtn.setFont(font)
        self.previewBtn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.previewBtn.setFocusPolicy(QtCore.Qt.StrongFocus)
        icon6 = QtGui.QIcon()
        icon6.addPixmap(QtGui.QPixmap(":/help_btn.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.On)
        self.previewBtn.setIcon(icon6)
        self.previewBtn.setIconSize(QtCore.QSize(65, 65))
        self.previewBtn.setChecked(False)
        self.previewBtn.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.previewBtn.setAutoRaise(True)
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
        font.setFamily("微软雅黑")
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
        icon7 = QtGui.QIcon()
        icon7.addPixmap(QtGui.QPixmap(":/crawl_btn.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.crawl_btn.setIcon(icon7)
        self.crawl_btn.setIconSize(QtCore.QSize(30, 30))
        self.crawl_btn.setCheckable(True)
        self.crawl_btn.setChecked(False)
        self.crawl_btn.setObjectName("crawl_btn")
        self.horizontalLayout_3.addWidget(self.crawl_btn)
        self.verticalLayout_2.addLayout(self.horizontalLayout_3)
        self.progressBar = QtWidgets.QProgressBar(self.centralwidget)
        font = QtGui.QFont()
        font.setFamily("微软雅黑")
        font.setPointSize(14)
        self.progressBar.setFont(font)
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
        self.chooseBox.setCurrentIndex(0)
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
        self.chooseBox.setItemText(0, _translate("MainWindow", "点选一个网站"))
        self.chooseBox.setItemText(1, _translate("MainWindow", "1、拷贝漫画"))
        self.chooseBox.setItemText(2, _translate("MainWindow", "2、jm**"))
        self.chooseBox.setItemText(3, _translate("MainWindow", "3、wnacg**"))
        self.chooseBox.setItemText(4, _translate("MainWindow", "4、ehentai**"))
        self.checkisopen.setText(_translate("MainWindow", "(完成后自动)打开存储目录"))
        self.searchinput.setInputMask(
            _translate("MainWindow", "输入关键字：xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"))
        self.searchinput.setText(_translate("MainWindow", "输入关键字："))
        self.previousPageBtn.setToolTip(_translate("MainWindow", "previous page/上一页"))
        self.previousPageBtn.setStatusTip(_translate("MainWindow", "previous page/上一页"))
        self.nextPageBtn.setToolTip(_translate("MainWindow", "next page/下一页"))
        self.nextPageBtn.setStatusTip(_translate("MainWindow", "next page/下一页"))
        self.pageEdit.setToolTip(_translate("MainWindow", "page of jump/翻页数"))
        self.pageEdit.setStatusTip(_translate("MainWindow", "page of jump/翻页数"))
        self.pageEdit.setInputMask(_translate("MainWindow", "000"))
        self.pageEdit.setPlaceholderText(_translate("MainWindow", "page"))
        self.pageJumpBtn.setToolTip(_translate("MainWindow", "jump page/翻页"))
        self.pageJumpBtn.setStatusTip(_translate("MainWindow", "jump page/翻页"))
        self.pageJumpBtn.setText(_translate("MainWindow", "jump"))
        self.chooseinput.setStatusTip(_translate("MainWindow",
                                                 "示例： 0 表示全选(特殊)  |  1 表示单选 1 (类推)  |  7+9 →表示多选 7、9 (加号)  |  3-5 →多选 3、4、5 (减号)  |  1+7-9 →复合多选 1、7、8、9"))
        self.chooseinput.setInputMask(_translate("MainWindow",
                                                 "输入序号：################################################################################"))
        self.chooseinput.setText(_translate("MainWindow", "输入序号："))
        self.toolButton.setText(_translate("MainWindow", "工具箱"))
        self.confBtn.setText(_translate("MainWindow", "配置"))
        self.retrybtn.setStatusTip(_translate("MainWindow", "重启程序（重启时，会卡个几秒）"))
        self.previewBtn.setToolTip(_translate("MainWindow", ">_<"))
        self.previewBtn.setStatusTip(_translate("MainWindow", "点击打开预览窗口，仅当出现书列表后才能使用"))
        self.previewBtn.setText(_translate("MainWindow", "点我预览"))
        self.next_btn.setText(_translate("MainWindow", "搜索"))
        self.crawl_btn.setText(_translate("MainWindow", "开始爬取！"))
        self.progressBar.setStatusTip(_translate("MainWindow",
                                                 " >>>进度条解读 Ⅰ、进度条蓝色表示后台还在下载中（ 有时进度条会回跳的请无视 ） Ⅱ、 绿色100%表示完成"))
