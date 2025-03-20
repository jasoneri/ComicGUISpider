#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from qfluentwidgets import (
    TransparentToolButton, HyperlinkButton, FluentIcon, 
    VBoxLayout, Flyout, FlyoutAnimationType, FlyoutViewBase, TableView,
    InfoBar, InfoBarIcon, InfoBarPosition, IndeterminateProgressBar,
    MessageBoxBase, TextBrowser, SubtitleLabel
)
from assets import res
from utils.docs import MarkdownConverter


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
        return _fly
        

    @staticmethod
    def calculate_target_position(widget):
        rect = widget.rect()
        bottom_center = widget.mapToGlobal(rect.bottomLeft())
        bottom_center.setX(bottom_center.x() + rect.width() // 2 - widget.width() // 2)
        bottom_center.setY(bottom_center.y() - 15)
        return bottom_center


class CustomMessageBox(MessageBoxBase):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.gui = parent
        self.yesButton.setText(res.Updater.update_ensure)
        self.textBrowser = TextBrowser(self)
        # self.textBrowser.setWordWrapMode(QtGui.QTextOption.NoWrap)  # 禁用自动换行
        self.textBrowser.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)  # 需要时显示水平滚动条
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


class IndeterminateBarFView(FlyoutViewBase):
    def __init__(self, parent=None):
        super(IndeterminateBarFView, self).__init__(parent)
        self.barLayout = QtWidgets.QHBoxLayout(self)
        self.barLayout.setContentsMargins(8, 0, 8, 0)
        indeterminateBar = IndeterminateProgressBar(self, start=True)
        self.barLayout.addWidget(indeterminateBar)
        self.setFixedSize(int(parent.width()*0.93), 10)


class TableFlyoutView(FlyoutViewBase):
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
        self.closeBtn.clicked.connect(self.close)
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
        tb_width = self.width - 20
        tb_height = self.height - 30
        self.tableView.setFixedSize(tb_width, tb_height)
        # 设置数据模型
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["漫画", "已阅最新章节"])
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
