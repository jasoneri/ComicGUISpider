# -*- coding: utf-8 -*-
"""自定义 cell 创建对话框：addonsInterface 的 mgrCell.addBtn 触发。

两种执行方式二选一：命令行（Edit 填写）/ 执行二进制（Conf.sv_path 同款文件选择卡）；
图标可空（无图标），也可选内置图标或经文件选择器挑本地图片。表单非法时覆写
``validate()`` 阻止关闭并提示，不做静默拒绝。``cell_data`` 仅在 accept 后有值。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PushSettingCard,
    SegmentedWidget,
)

from assets import res as ori_res

uic_res = ori_res.GUI.Uic

MODE_CMD = "cmd"       # 命令行
MODE_BIN = "bin"       # 执行二进制
CUSTOM_ICON = "__custom__"   # ComboBox 中"自定义图片…"的哨兵 userData
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.svg *.ico *.bmp)"

# 可选内置图标 = GUI/src/tools 现有图标；userData 存完整资源路径（空串 = 无图标）
ICON_OPTIONS = (
    "",
    ":/tools/rv.png",
    ":/tools/saucenao.png",
    ":/tools/ascii2d.png",
    ":/tools/config_icon.png",
    ":/tools/ht.svg",
)


class CustomCellDialog(MessageBoxBase):
    """创建模式②（用户自定义组合）cell。"""

    def __init__(self, taken_names=(), parent=None):
        super().__init__(parent)
        self.cell_data = None
        self._taken_names = set(taken_names)
        self._bin_path = ""
        self._custom_icon = ""
        self._prev_icon_index = 0
        self.widget.setMinimumWidth(480)
        self.yesButton.setText("创建")
        self.cancelButton.setText("取消")

        box = QVBoxLayout()
        box.setSpacing(10)
        box.setContentsMargins(0, 0, 0, 0)

        self.nameEdit = LineEdit()
        self.nameEdit.setClearButtonEnabled(True)
        self.nameEdit.setPlaceholderText("例如 komga")
        box.addLayout(self._row("名称", self.nameEdit))

        self.iconBox = ComboBox()
        for icon in ICON_OPTIONS:
            self.iconBox.addItem(Path(icon).stem or "无图标", userData=icon)
            if icon:
                self.iconBox.setItemIcon(self.iconBox.count() - 1, QIcon(QPixmap(icon)))
        self.iconBox.addItem("自定义图片…", userData=CUSTOM_ICON)
        self.iconBox.currentIndexChanged.connect(self._on_icon_changed)
        box.addLayout(self._row("图标", self.iconBox))

        self.modeSeg = SegmentedWidget(self)
        self.modeSeg.addItem(routeKey=MODE_CMD, text="命令行", onClick=lambda *_: self._sync_mode())
        self.modeSeg.addItem(routeKey=MODE_BIN, text="执行二进制", onClick=lambda *_: self._sync_mode())
        self.modeSeg.setCurrentItem(MODE_CMD)
        box.addLayout(self._row("执行方式", self.modeSeg))

        self.cmdEdit = LineEdit()
        self.cmdEdit.setClearButtonEnabled(True)
        self.cmdEdit.setPlaceholderText("例如 komga serve D:/komga/library")
        box.addLayout(self._row("命令行", self.cmdEdit))

        self.binCard = PushSettingCard("选择文件", FIF.FOLDER, "执行文件", "未选择", self.widget)
        self.binCard.clicked.connect(self._pick_bin)
        box.addWidget(self.binCard)

        self.viewLayout.addLayout(box)
        self._sync_mode()

    @staticmethod
    def _row(title: str, widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(BodyLabel(title))
        row.addWidget(widget, 1)
        return row

    def _sync_mode(self):
        is_cmd = self.modeSeg.currentRouteKey() == MODE_CMD
        self.cmdEdit.setVisible(is_cmd)
        self.binCard.setVisible(not is_cmd)

    def _on_icon_changed(self, index: int):
        """选"自定义图片…"即开文件选择器；取消则退回上一选项。"""
        if self.iconBox.itemData(index) != CUSTOM_ICON:
            self._prev_icon_index = index
            return
        # 必须推迟到本次菜单点击处理结束之后再开文件选择器:qfluent 的 ComboBoxMenu
        # 带 WA_DeleteOnClose,在它的 itemClicked 处理里直接起原生文件对话框(Win32
        # 模态循环)会让菜单在嵌套循环期间被销毁,循环返回后菜单 C++ 侧继续使用已
        # 释放对象 → Qt6Widgets.dll access violation,进程当场退出且不留 Python 堆栈。
        # 传 self 作 context:对话框若在本次点击后紧接着被销毁,回调自动作废。
        QTimer.singleShot(0, self, lambda: self._pick_custom_icon(index))

    def _pick_custom_icon(self, index: int):
        file, _ = QFileDialog.getOpenFileName(self, "选择图标图片", "", IMAGE_FILTER)
        if not file:
            self.iconBox.blockSignals(True)
            self.iconBox.setCurrentIndex(self._prev_icon_index)
            self.iconBox.blockSignals(False)
            return
        self._prev_icon_index = index
        self._custom_icon = file
        self.iconBox.setItemText(index, Path(file).name)
        self.iconBox.setItemIcon(index, QIcon(QPixmap(file)))

    def _pick_bin(self):
        file, _ = QFileDialog.getOpenFileName(self, uic_res.sv_path_desc_tip)
        if not file:
            return
        self._bin_path = file
        self.binCard.setContent(file)
        self.binCard.setToolTip(file)

    def validate(self) -> bool:
        name = self.nameEdit.text().strip()
        if not name:
            return self._reject_form("请填写名称")
        if name in self._taken_names:
            return self._reject_form(f"名称「{name}」已存在")
        if self.modeSeg.currentRouteKey() == MODE_CMD:
            if not self.cmdEdit.text().strip():
                return self._reject_form("请填写命令行")
            self.cell_data = dict(name=name, icon=self._current_icon(), mode=MODE_CMD,
                                  cmd=self.cmdEdit.text().strip(), path="")
        else:
            if not self._bin_path:
                return self._reject_form("请选择执行文件")
            self.cell_data = dict(name=name, icon=self._current_icon(), mode=MODE_BIN,
                                  cmd="", path=self._bin_path)
        return True

    def _current_icon(self) -> str:
        if self.iconBox.currentData() == CUSTOM_ICON:
            return self._custom_icon
        return self.iconBox.currentData() or ""

    def _reject_form(self, content: str) -> bool:
        InfoBar.warning(title="", content=content, parent=self,
                        position=InfoBarPosition.TOP, duration=2500)
        return False


class CommandEditDialog(MessageBoxBase):
    """编辑自定义 cell 的命令行（cell 内 executefileBtn 在 cmd 模式下触发）。"""

    def __init__(self, command: str, parent=None):
        super().__init__(parent)
        self.command = ""
        self.widget.setMinimumWidth(420)
        self.yesButton.setText("Save")
        self.cancelButton.setText("Cancel")

        self.edit = LineEdit()
        self.edit.setClearButtonEnabled(True)
        self.edit.setText(command)
        self.edit.setPlaceholderText("e.g. komga serve D:/komga/library")
        self.viewLayout.addWidget(self.edit)

    def validate(self) -> bool:
        text = self.edit.text().strip()
        if not text:
            InfoBar.warning(title="", content="命令行不能为空", parent=self,
                            position=InfoBarPosition.TOP, duration=2500)
            return False
        self.command = text
        return True
