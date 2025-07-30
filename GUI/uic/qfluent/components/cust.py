import typing as t
from enum import Enum
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from qfluentwidgets import (
    TransparentToolButton, HyperlinkButton, PrimaryPushButton,
    FluentIcon, FluentIconBase, Theme,
    VBoxLayout, Flyout, FlyoutAnimationType, FlyoutViewBase, TableView,
    InfoBar, InfoBarIcon, InfoBarPosition, IndeterminateProgressBar, BodyLabel,
    TeachingTip, TeachingTipTailPosition, ImageLabel
)


from assets import res
from utils.redViewer_tools import BookShow, delete_record


class CustomInfoBar:
    @staticmethod
    def show(title, content, parent, url, url_name, _type="ERROR", **kw):
        InfoBar_kw = dict(
            icon=getattr(InfoBarIcon, _type.upper()),
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=-1,
            parent=parent
        )
        w = InfoBar(**{**InfoBar_kw, **kw})
        w.addWidget(HyperlinkButton(FluentIcon.LINK, url, url_name, parent=None))
        w.show()

    @staticmethod
    def show_custom(title, content, parent, _type="ERROR", widgets=[], **kw):
        InfoBar_kw = dict(
            icon=getattr(InfoBarIcon, _type.upper()),
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=-1,
            parent=parent
        )
        w = InfoBar(**{**InfoBar_kw, **kw})
        for widget in widgets:
            w.addWidget(widget)
        w.show()


class CustomFlyout:
    @classmethod
    def make(cls, view, target, parent, calc_bottom=False, aniType=FlyoutAnimationType.PULL_UP):
        _fly = Flyout.make(
            view=view, parent=parent, aniType=aniType, 
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


class CustomIcon(FluentIconBase, Enum):
    DISCORD = "configDialog/discord"
    QQ = "configDialog/qq"
    TOOL_MERGE = "tools/merge"
    TOOL_BOOK_MARKED = "tools/book_marked"
    
    def path(self, theme=Theme.AUTO):
        return f':/{self.value}.svg'


class SupportView(FlyoutViewBase):
    closed = pyqtSignal()  # 添加closed信号
    res = res.GUI.Uic
    
    def __init__(self, proj_url, conf_dia=None):
        super(SupportView, self).__init__(conf_dia)
        self.conf_dia = conf_dia
        self.width = int(conf_dia.width() * 0.8)
        self.layout = VBoxLayout(self)
        self.titleLayout = QtWidgets.QHBoxLayout()
        self.githubBtn = HyperlinkButton(FluentIcon.GITHUB, proj_url, "Github")
        self.qqGroupBtn = HyperlinkButton(CustomIcon.QQ, "https://qm.qq.com/q/T2SONVQmiW", "QQ")
        self.discordBtn = HyperlinkButton(CustomIcon.DISCORD, "https://discord.gg/znD4p2fpSE", "Discord")
        spacerItem = QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        self.titleLayout.addWidget(self.githubBtn)
        self.titleLayout.addWidget(self.qqGroupBtn)
        self.titleLayout.addWidget(self.discordBtn)
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

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.toolWin = parent
        p_width = parent.width()
        p_height = parent.height()
        self.width = int(p_width * 0.8)
        self.height = int(p_height * 4)
        # 必须设置布局
        self.layout = VBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # 创建表格视图
        self.set_table(data)
        first_row = QtWidgets.QHBoxLayout()
        first_row.addWidget(self.tableView)
        
        second_row = QtWidgets.QHBoxLayout()
        
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        self.delBtn = PrimaryPushButton(FluentIcon.DELETE, "删除选中记录", self)
        self.delBtn.clicked.connect(self.delete_selected_record)
        second_row.addWidget(self.delBtn)
        second_row.addItem(spacerItem)
        second_row.addWidget(self.closeBtn)
        
        self.layout.addLayout(first_row)
        self.layout.addLayout(second_row)
        # 必须设置视图尺寸
        self.setFixedSize(self.width, self.height)

    def set_table(self, data: t.List[BookShow]):
        self.tableView = TableView(self)
        self.tableView.setBorderRadius(15)
        self.tableView.setWordWrap(False)
        tb_width = self.width
        tb_height = self.height - 30
        self.tableView.setFixedSize(tb_width, tb_height)
        self.tableView.verticalHeader().hide()
        # 设置数据模型
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["漫画", "已阅最新章节", "已下载最新章节"])
        for book in data:
            row = [
                QStandardItem(book.name),
                QStandardItem(book.show_max),
                QStandardItem(book.dl_max)
            ]
            model.appendRow(row)
        self.tableView.setModel(model)
        self.tableView.horizontalHeader().setStretchLastSection(True)
        # 调整列宽
        self.tableView.setColumnWidth(0, int(tb_width * 0.5))
        self.tableView.setColumnWidth(1, int(tb_width * 0.2))
        self.tableView.setColumnWidth(2, int(tb_width * 0.2))

        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

    def delete_selected_record(self):
        selection_model = self.tableView.selectionModel()
        if not selection_model.hasSelection():
            InfoBar.warning(
                title='', content='请先选择要删除的记录',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
                duration=5000, parent=self.toolWin
            )
            return
        selected_indexes = selection_model.selectedRows()
        row = selected_indexes[0].row()
        model = self.tableView.model()
        book_name = model.item(row, 0).text()
        delete_record(book_name)
        model.removeRow(row)
