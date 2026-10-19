# -*- coding: utf-8 -*-
"""rvTool interface：常驻表 + 顶部右对齐刷新按钮。

表随 ``rv_mgr.snapshot_changed`` 重建，懒构造于进页或首次触发时。
sauce 动作为 addonsInterface 的 sauceCell 承载，本页不含。
"""
from __future__ import annotations

import typing as t

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    TableView,
    ToolButton,
    VBoxLayout,
)

# CGS003: keep type-only backend imports out of the first-paint dependency graph.
if t.TYPE_CHECKING:
    from utils.redViewer_tools import BookShow


class RvShowMaxTable(QWidget):
    """show_max 表：三列 [漫画, 已阅最新章节, 已下载最新章节] + 删除/搜索选中记录。

    列宽按 ``COLUMN_RATIOS`` 随视口宽比例自适应，末列由 stretchLastSection 吃剩余；
    重标定必须挂在 ``tableView.viewport()`` 自身的 Resize 上——父 ``resizeEvent`` 触发时
    视口尺寸尚未更新，按旧宽度标定会把前两列固化成错值。
    """

    # viewport 宽度变化时按此比例重标定前两列，末列由 stretchLastSection 吃剩余。
    COLUMN_RATIOS = (0.5, 0.25, 0.25)
    # 壳最小高：布局原生最小值会顶高 rv 页，压到三分之二取整十；窗口缩到极限时表内滚动。
    SHELL_MIN_HEIGHT = 70

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.rvInterface = parent
        self.gui = parent.gui
        layout = VBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.set_table(data)
        # 需显式传 Qt.Alignment()：qfluent VBoxLayout.addWidget 默认 AlignTop，
        # stretch 格子内 widget 只按 sizeHint 顶部对齐、不填充。
        layout.addWidget(self.tableView, 1, Qt.Alignment())

        second_row = QHBoxLayout()
        self.delBtn = PrimaryPushButton(FIF.DELETE, "删除选中记录", self)
        self.delBtn.clicked.connect(self.delete_selected_record)
        self.searchBtn = PrimaryPushButton(FIF.SEARCH, "搜索选中记录", self)
        self.searchBtn.clicked.connect(self.send_selected_record)
        second_row.addWidget(self.delBtn)
        second_row.addWidget(self.searchBtn)
        second_row.addStretch(1)
        layout.addLayout(second_row)
        # 表格 min 同步下调，保证 SHELL_MIN_HEIGHT 内布局不溢出（表内滚动接管收缩）。
        self.setMinimumHeight(self.SHELL_MIN_HEIGHT)
        self.tableView.setMinimumHeight(
            max(32, self.SHELL_MIN_HEIGHT - layout.spacing() - self.delBtn.sizeHint().height()))

    def set_table(self, data: t.Dict[str, BookShow]):
        self.tableView = TableView(self)
        self.tableView.setBorderRadius(15)
        self.tableView.setWordWrap(False)
        self.tableView.verticalHeader().hide()
        # 设置数据模型
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["漫画", "已阅最新章节", "已下载最新章节"])
        for book in data.values():
            row = [
                QStandardItem(book.name),
                QStandardItem(book.show_max),
                QStandardItem(book.dl_max),
            ]
            model.appendRow(row)
        self.tableView.setModel(model)
        self.tableView.setSortingEnabled(True)
        self.tableView.horizontalHeader().setSortIndicatorShown(True)
        self.tableView.horizontalHeader().setStretchLastSection(True)

        self.tableView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # 列宽重标定挂在 viewport 自身 Resize：父 resizeEvent 里 viewport 尺寸尚未更新。
        self.tableView.viewport().installEventFilter(self)
        self._apply_column_widths()
        # 本方法会在运行时重建 tableView，新表不带 __init__ 打过的最小高；
        # 首次构造时 delBtn 尚未建立，由 __init__ 尾部统一施加，此处只负责刷新路径。
        if hasattr(self, "delBtn"):
            self.tableView.setMinimumHeight(
                max(32, self.SHELL_MIN_HEIGHT - self.layout().spacing() - self.delBtn.sizeHint().height()))

    def eventFilter(self, obj, event):
        # viewport 的 Resize 到达时其 size() 已是新值，此时按比例重标定前两列。
        table = getattr(self, "tableView", None)
        viewport = table.viewport() if table is not None else None
        if viewport is not None and obj is viewport and event.type() == QEvent.Type.Resize:
            self._apply_column_widths()
        return super().eventFilter(obj, event)

    def _apply_column_widths(self):
        width = self.tableView.viewport().width()
        if width <= 0:
            return
        self.tableView.setColumnWidth(0, int(width * self.COLUMN_RATIOS[0]))
        self.tableView.setColumnWidth(1, int(width * self.COLUMN_RATIOS[1]))

    def delete_selected_record(self):
        selection_model = self.tableView.selectionModel()
        if not selection_model.hasSelection():
            InfoBar.warning(
                title='', content='请先选择要删除的记录',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
                duration=5000, parent=self.rvInterface
            )
            return
        selected_indexes = selection_model.selectedRows()
        row = selected_indexes[0].row()
        model = self.tableView.model()
        book_name = model.item(row, 0).text()
        self.gui.rv_tools.delete_record(book_name)
        model.removeRow(row)

    def send_selected_record(self):
        selection_model = self.tableView.selectionModel()
        if not selection_model.hasSelection():
            InfoBar.warning(
                title='', content='请先选择行',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000, parent=self.rvInterface.table_fv
            )
            return
        elif self.gui.chooseBox.currentIndex() == 0:
            InfoBar.warning(
                title='', content='请先选择搜索源',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000, parent=self.rvInterface.table_fv
            )
            return
        selected_indexes = selection_model.selectedRows()
        row = selected_indexes[0].row()
        model = self.tableView.model()
        book_name = model.item(row, 0).text()
        def do():
            self.gui.searchinput.setText(book_name)
            cont = '已发至输入框，自行调整再点击搜索'
            if self.gui.rv_tools.ero != 1:
                # TODO: 非 ero 源下应直接搜索而非走预览，待定
                self.gui.mpreviewBtn.click()
                cont = f'''「{book_name}」已发至输入框进行搜索中'''
            InfoBar.info(title='', content=cont,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=2000, parent=self.gui.showArea)
        QTimer.singleShot(10, do)
        # 发去搜索后收起工作区窗口。
        self.rvInterface.host_window.close()


class RvInterface(QWidget):
    """rvTool 页面（objectName ``rvInterface``，挂 ToolWorkspaceWindow pivot）。"""

    infobar_pos = InfoBarPosition.BOTTOM_LEFT

    def __init__(self, gui, parent=None, *, host_window=None):
        super().__init__(parent)
        self.gui = gui
        # 动作后关窗的宿主窗口（ToolWorkspaceWindow）。
        self.host_window = host_window or parent
        self.table_fv = None        # 常驻表：懒构造，进页/首次触发才建
        self._table_source = None   # 建表所用的 bsm 字典，失效比对用
        self.setObjectName("rvInterface")
        self.init_ui()
        self.gui.rv_mgr.snapshot_changed.connect(self._on_snapshot_changed)

    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        # 顶部行：右对齐刷新按钮（常驻表刷新入口）。
        row1 = QHBoxLayout()
        row1.addStretch(1)
        self.scanBtn = ToolButton(FIF.SYNC)
        from assets import res as _res
        self.scanBtn.setToolTip(_res.GUI.Tools.rv_scan_local)
        row1.addWidget(self.scanBtn)
        self.main_layout.addLayout(row1)
        self.scanBtn.clicked.connect(self.rv_scan)
        # 常驻 table_fv 容器：expanding + stretch 1 撑满页面高度；表本身懒构造。
        # 需显式传 Qt.Alignment()：qfluent VBoxLayout.addWidget 默认 AlignTop，stretch 格子不填充。
        self.table_host = QWidget(self)
        self.table_host.setObjectName("rvTableHost")
        self.table_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_host_layout = QVBoxLayout(self.table_host)
        table_host_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.table_host, 1, Qt.Alignment())

    def rv_scan(self):
        # CGS003: conf / CgsRuleMgr / tools_res 延迟导入，避免进 interface 模块的首屏依赖图。
        from utils import conf
        from utils.config.rule import CgsRuleMgr
        from assets import res as _res
        if not CgsRuleMgr.exists(conf.sv_path):
            InfoBar.warning(title='', content=_res.GUI.Tools.rv_notCgsRule,
                position=InfoBarPosition.TOP_RIGHT, duration=4000, parent=self)
        self.gui.rv_mgr.start_scan(show_progress=True, parent_widget=self, pos=self.infobar_pos)

    def showEvent(self, event):
        super().showEvent(event)
        # 进页懒构造 / 失效重建统一入口
        self._sync_table()

    def _on_snapshot_changed(self, *_args):
        # snapshot_changed 先于 bsm=None 发射，延后一轮再比对，避免读到失效前的旧 bsm；
        # 计时器以 self 为父，随页面销毁，不会打到已删除的控件上。
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._sync_table)
        timer.start(0)

    def _sync_table(self):
        """失效重建：``gui.bsm`` 被置 None（扫描完成 / 站点重置）后按新数据重建。"""
        if self.table_fv is not None and self.gui.bsm is self._table_source:
            return
        data = self.gui.bsm
        if data is None:
            data = self.gui.rv_tools.show_max()
            self.gui.bsm = data
        self._rebuild_table(data)

    def _rebuild_table(self, data):
        self._table_source = data
        old = self.table_fv
        self.table_fv = RvShowMaxTable(data, self)
        self.table_host.layout().addWidget(self.table_fv, 1, Qt.Alignment())
        if old is not None:
            old.deleteLater()
