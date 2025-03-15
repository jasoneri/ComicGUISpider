from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from qfluentwidgets import (
    TransparentToolButton, HyperlinkButton, FluentIcon, 
    VBoxLayout, Flyout, FlyoutAnimationType, FlyoutViewBase, TableView,
    InfoBar, InfoBarIcon, InfoBarPosition
)


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
        w.addWidget(HyperlinkButton(FluentIcon.LINK, url, url_name))
        w.show()


class CustomFlyout:
    @classmethod
    def make(cls, view, target, parent):
        Flyout.make(
            view=view, target=target, parent=parent,
            aniType=FlyoutAnimationType.PULL_UP,
        )


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
