#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from qfluentwidgets import (
    TransparentToolButton, TransparentPushButton, HyperlinkButton, FluentIcon, 
    VBoxLayout, Flyout, FlyoutAnimationType, FlyoutViewBase, TableView,
    InfoBar, InfoBarIcon, InfoBarPosition, IndeterminateProgressBar,
    MessageBoxBase, TextBrowser, BodyLabel, SubtitleLabel, 
    TeachingTip, TeachingTipTailPosition, SplashScreen, ImageLabel
)
from assets import res
from utils.docs import MarkdownConverter


class CustomSplashScreen(SplashScreen):
    def __init__(self, parent=None, enableShadow=True):
        super(CustomSplashScreen, self).__init__(QIcon(":/guide.png"), parent, enableShadow)
        height = int(parent.height() * 0.7)
        self.setIconSize(QSize(height, height))


class CustomInfoBar:
    @staticmethod
    def show(title, content, parent, url, url_name, _type="ERROR"):
        w = InfoBar(
            icon=getattr(InfoBarIcon, _type.upper()),
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=-1,
            parent=parent
        )
        w.addWidget(HyperlinkButton(FluentIcon.LINK, url, url_name, parent=None))
        w.show()


class CustomFlyout:
    @classmethod
    def make(cls, view, target, parent, calc_bottom=False):
        _fly = Flyout.make(
            view=view, parent=parent, aniType=FlyoutAnimationType.PULL_UP, 
            target=cls.calculate_target_position(target) if calc_bottom else target
        )
        if hasattr(view, "closed"):
            view.closed.connect(_fly.close)
        return _fly


    @staticmethod
    def calculate_target_position(widget):
        rect = widget.rect()
        bottom_center = widget.mapToGlobal(rect.bottomLeft())
        bottom_center.setX(bottom_center.x() + rect.width() // 2 - widget.width() // 2)
        bottom_center.setY(bottom_center.y() - 15)
        return bottom_center


class CustomTeachingTip:
    @classmethod
    def make(cls, view, target, parent, tailPosition=TeachingTipTailPosition.BOTTOM):
        _tip = TeachingTip.make(
            view=view, target=target, duration=-1, tailPosition=tailPosition, parent=parent
        )
        if hasattr(view, "closed"):
            view.closed.connect(_tip.close)
        return _tip


class CustomMessageBox(MessageBoxBase):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.gui = parent
        self.yesButton.setText(res.Updater.update_ensure)
        self.textBrowser = TextBrowser(self)
        # self.textBrowser.setWordWrapMode(QtGui.QTextOption.NoWrap)  # 禁用自动换行
        self.textBrowser.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 需要时显示水平滚动条
        if title:
            self.titleLabel = SubtitleLabel(title)
            self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.textBrowser)
        self.widget.setMinimumWidth(int(parent.width() * 0.8))

    def validate(self):
        self.gui.updating_fly = CustomFlyout.make(
            view=IndeterminateBarFView(self.gui), 
            target=self.gui.textBrowser, parent=self.gui, calc_bottom=True
        )
        self.gui.conf_dia.puThread.update_signal.emit()
        return True

    def show_release_note(self, note):
        def _format_note(note):
            note = note.split("\n---")[0]
            return re.sub(r'\s*\(\s*[0-9a-f]{40}.*\)', '', note)
        html_text = MarkdownConverter.convert_html(_format_note(note))
        self.textBrowser.setHtml(html_text)
        self.gui.conf_dia.hide()
        self.show()


class SupportView(FlyoutViewBase):
    closed = pyqtSignal()  # 添加closed信号
    res = res.GUI.Uic
    
    def _copy_group(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.res.confDia_feedback_group)
        InfoBar.success(
            title='', content=self.res.confDia_feedback_group_copied,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
            duration=2500, parent=self.conf_dia
        )
        
    def __init__(self, proj_url, conf_dia=None):
        super(SupportView, self).__init__(conf_dia)
        self.conf_dia = conf_dia
        self.width = int(conf_dia.width() * 0.8)
        self.layout = VBoxLayout(self)
        self.titleLayout = QtWidgets.QHBoxLayout()
        # self.titleLayout.setContentsMargins(8, 0, 8, 0)
        self.githubBtn = HyperlinkButton(FluentIcon.GITHUB, proj_url, "Github")
        self.feedbackBtn = TransparentPushButton(FluentIcon.CHAT, self.res.confDia_feedback_group)
        self.feedbackBtn.clicked.connect(self._copy_group)
        spacerItem = QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        self.titleLayout.addWidget(self.githubBtn)
        self.titleLayout.addWidget(self.feedbackBtn)
        self.titleLayout.addItem(spacerItem)
        self.titleLayout.addWidget(self.closeBtn)
        
        self.promoteLayout = QtWidgets.QHBoxLayout()
        self.promoteBtn = HyperlinkButton(FluentIcon.LINK, self.res.confDia_promote_url, self.res.confDia_promote_title)
        self.contentLabel = BodyLabel(self.res.confDia_promote_content) 
        self.promoteLayout.addWidget(self.promoteBtn)
        self.promoteLayout.addWidget(self.contentLabel)
        self.promoteLayout.addItem(QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum))

        self.contentLabel = BodyLabel(res.GUI.Uic.confDia_support_content) 
        self.picLayout = QtWidgets.QHBoxLayout()
        self.aliPayLabel = ImageLabel(":/_support/alipay.png")
        self.aliPayLabel.scaledToWidth(int(self.width * 0.4))
        self.aliPayLabel.setBorderRadius(8, 8, 8, 8)
        self.picLayout.addWidget(self.aliPayLabel)
        vLine = QtWidgets.QFrame(self)
        vLine.setFrameShape(QtWidgets.QFrame.VLine)
        vLine.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.picLayout.addWidget(vLine)
        self.wePayLabel = ImageLabel(":/_support/wepay.png")
        self.wePayLabel.scaledToWidth(int(self.width * 0.4))
        self.wePayLabel.setBorderRadius(8, 8, 8, 8)
        self.picLayout.addWidget(self.wePayLabel)

        self.layout.addLayout(self.titleLayout)
        self.hLine = QtWidgets.QFrame(self)
        self.hLine.setFrameShape(QtWidgets.QFrame.HLine)
        self.hLine.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.layout.addWidget(self.hLine)
        self.layout.addLayout(self.promoteLayout)
        self.layout.addWidget(self.contentLabel)
        self.layout.addLayout(self.picLayout)
        self.setFixedWidth(self.width)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)


class IndeterminateBarFView(FlyoutViewBase):
    def __init__(self, parent=None):
        super(IndeterminateBarFView, self).__init__(parent)
        self.barLayout = QtWidgets.QHBoxLayout()
        self.barLayout.setContentsMargins(8, 0, 8, 0)
        indeterminateBar = IndeterminateProgressBar(self, start=True)
        self.barLayout.addWidget(indeterminateBar)
        self.setLayout(self.barLayout)
        self.setFixedSize(int(parent.width()*0.93), 10)


class TableFlyoutView(FlyoutViewBase):
    closed = pyqtSignal()

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        p_width = parent.width()
        p_height = parent.height()
        self.width = int(p_width * 0.6)
        self.height = int(p_height * 0.85)
        # 必须设置布局
        self.layout = VBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # 创建表格视图
        self.set_table(data)
        # 将表格添加到布局
        self.bottom_layout = QtWidgets.QHBoxLayout()
        self.bottom_layout.setObjectName("bottom_layout")
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        spacerItem3 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.bottom_layout.addItem(spacerItem3)
        self.bottom_layout.addWidget(self.closeBtn)
        
        self.layout.addWidget(self.tableView)
        self.layout.addLayout(self.bottom_layout, 1)
        # 必须设置视图尺寸
        self.setFixedSize(self.width, self.height)

    def set_table(self, data: dict):
        self.tableView = TableView(self)
        self.tableView.setBorderRadius(15)
        self.tableView.setWordWrap(False)
        tb_width = self.width
        tb_height = self.height - 30
        self.tableView.setFixedSize(tb_width, tb_height)
        self.tableView.verticalHeader().hide()
        # 设置数据模型
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Name/漫画", "Latest Chapter/已阅最新章节"])
        for book, chapter in data.items():
            row = [
                QStandardItem(book),
                QStandardItem(chapter)
            ]
            model.appendRow(row)
        self.tableView.setModel(model)
        self.tableView.horizontalHeader().setStretchLastSection(True)
        # 调整列宽
        self.tableView.setColumnWidth(0, int(tb_width * 0.6))
        self.tableView.setColumnWidth(1, int(tb_width * 0.25))
