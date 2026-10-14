import sqlite3
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QTreeWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, InfoBar, InfoBarPosition, PushButton, SearchLineEdit, ToolButton, TreeWidget

from .entries import (MODE_DOUJIN, STATUS_TOOLTIP, UploadState, UploadStatus, map_snapshot)


class WebdavLibraryTree(QWidget):
    selection_changed = Signal()
    # 读库失败（锁 / 损坏）：由宿主（WebdavInterface）落日志 + InfoBar.error，树按空降级不静默。
    history_failed = Signal(str)

    def __init__(self, parent, history_store=None):
        super().__init__(parent)
        self.history = history_store
        self.entries = {}
        self._items = {}
        self._groups = {}
        self._group_leaves = {}
        self._group_entries = {}
        self._search_text = {}
        self._visible = set()
        self._statuses = {}
        self._checked = set()
        self._missing = set()
        self.filter_edit = SearchLineEdit(self)
        self.filter_edit.setPlaceholderText("筛选漫画 / 章节")
        self.filter_edit.setAccessibleName("筛选漫画和章节")
        self.select_btn = PushButton(FIF.CHECKBOX, "勾选筛选结果", self)
        self.clear_btn = ToolButton(FIF.CLOSE, self)
        self.clear_btn.setToolTip("清空勾选")
        self.clear_btn.setAccessibleName("清空勾选")
        self.select_btn.hide()
        self.clear_btn.hide()
        self.tree = TreeWidget(self)
        self.tree.setHeaderLabels(["漫画 / 章节", "格式", "状态"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setDragEnabled(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setUniformRowHeights(True)
        self._build_ui()
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemExpanded.connect(self._materialize_group)
        self.filter_edit.textChanged.connect(self._filter)
        self.select_btn.clicked.connect(self.select_visible)
        self.clear_btn.clicked.connect(self.clear_selection)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        # 书库区只负责筛选与勾选：远端地址属于连接卡配置，不在此重复展示。
        row = QHBoxLayout()
        row.addWidget(self.filter_edit, 1)
        row.addWidget(self.select_btn)
        row.addWidget(self.clear_btn)
        layout.addLayout(row)
        layout.addWidget(self.tree, 1)

    def set_snapshot(self, snapshot, mode):
        self.tree.setHeaderLabels(["本子 / 章节" if mode == MODE_DOUJIN else "漫画 / 章节", "格式", "状态"])
        current = self.tree.currentItem()
        current_key = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        current_is_group = current is not None and current.parent() is None
        expanded = {key for key, item in self._groups.items() if item.isExpanded()}
        scroll = self.tree.verticalScrollBar().value()
        previous = self._checked
        values = map_snapshot(snapshot, mode) if snapshot is not None else ()
        self.entries = {entry.local_path: entry for entry in values}
        self._checked = previous & {key for key, entry in self.entries.items() if entry.is_uploadable}
        self._statuses = {key: state for key, state in self._statuses.items() if key in self.entries}
        self._search_text = {key: f"{entry.book} {entry.ep} {key}".casefold() for key, entry in self.entries.items()}
        self._apply_history(mode)
        self._group_entries, self._group_leaves = {}, {}
        for entry in values:
            self._group_entries.setdefault(entry.group_key, []).append(entry.local_path)
            self._group_leaves.setdefault(entry.group_key, [])
            if entry.is_uploadable:
                self._group_leaves[entry.group_key].append(entry.local_path)
        with QSignalBlocker(self.tree):
            self.tree.clear()
            self._items, self._groups = {}, {}
            for key, keys in self._group_entries.items():
                group = QTreeWidgetItem([self.entries[keys[0]].book, "", ""])
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                group.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable if self._group_leaves[key] else flags)
                group.setData(0, Qt.ItemDataRole.UserRole, key)
                group.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self.tree.addTopLevelItem(group)
                self._groups[key] = group
            self._filter()
            for key in expanded & self._groups.keys():
                self._materialize_group(self._groups[key])
                self._groups[key].setExpanded(True)
            if current_is_group and current_key in self._groups:
                self.tree.setCurrentItem(self._groups[current_key])
            elif current_key in self.entries:
                self._materialize_group(self._groups[self.entries[current_key].group_key])
                self.tree.setCurrentItem(self._items[current_key])
        self._render_checks()
        self.tree.verticalScrollBar().setValue(scroll)
        removed = len(previous - self._checked)
        if removed:
            InfoBar.warning(title='', content=f"已移除 {removed} 项失效选择", position=InfoBarPosition.TOP,
                            duration=4000, parent=self.window() or self)

    def _apply_history(self, mode):
        """投影完成时的历史回填 + 冲突预演（R-H4/R-H5，纯本地 stat，零网络）。

        - 键 `(relative_path, mode)` 取 batch_id 最大的落地记录（限定 state='done' + 当前 mode）。
        - 缺失 ⇒ LOCAL_MISSING（有记录带 batch 前缀，无记录为幽灵条目无前缀）；
          cbz 且有记录时 size 不符 ⇒ LOCAL_MODIFIED；dir 只校验存在性。
        - 有条记录且无会话状态 ⇒ 恢复其终态（会话内在写优先，回填只补空缺）。
        - 读库失败 ⇒ history_failed 信号 + 按空降级（宿主可见告知），树与上传照常。
        """
        self._missing = set()
        if self.history is None or not self.entries:
            return
        keys = {(entry.relative_path, mode) for entry in self.entries.values()}
        try:
            records = self.history.latest_uploads(mode, keys)
        except (sqlite3.Error, OSError) as exc:
            # 读库失败必须可见（E-S1）：树内即示 InfoBar.error，信号交宿主落日志；历史按空降级。
            self.history_failed.emit(str(exc))
            InfoBar.error(title='', content="上传历史读取失败，请查看日志", position=InfoBarPosition.TOP,
                          duration=8000, parent=self.window() or self)
            return
        missing, modified = [], []
        for key, entry in self.entries.items():
            record = records.get((entry.relative_path, mode))
            batch = record.batch_id if record else 0
            try:
                exists = (Path(entry.local_path).is_file() if entry.kind == "cbz"
                          else Path(entry.local_path).is_dir())
                size_ok = (entry.kind != "cbz" or record is None or record.size is None
                           or Path(entry.local_path).stat().st_size == record.size)
            except OSError:
                exists, size_ok = False, False  # stat 失败按缺失处理；推送时会给出权威错误
            if not exists:
                self._statuses[key] = UploadState(UploadStatus.LOCAL_MISSING, batch=batch)
                missing.append(key)
            elif not size_ok:
                self._statuses[key] = UploadState(UploadStatus.LOCAL_MODIFIED, batch=batch)
                modified.append(key)
            elif record is not None and key not in self._statuses:
                self._statuses[key] = UploadState(UploadStatus(record.result), batch=batch)
        self._missing = set(missing)
        if missing or modified:
            InfoBar.warning(title='',
                            content=(f"{len(missing)} 项本地文件已删除 · {len(modified)} 项本地已修改（与上传记录不符），"
                                     "如为外部改动，可点右上角刷新重新扫描"),
                            position=InfoBarPosition.TOP, duration=6000, parent=self.window() or self)

    def _materialize_group(self, group):
        if group.childCount() or group.parent() is not None:
            return
        group_key = group.data(0, Qt.ItemDataRole.UserRole)
        with QSignalBlocker(self.tree):
            for key in self._group_entries[group_key]:
                entry = self.entries[key]
                state = self._statuses.get(key, UploadState(UploadStatus.PENDING))
                item = QTreeWidgetItem([entry.title, "CBZ" if entry.kind == "cbz" else "目录",
                                        entry.error_text or state.text()])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                item.setToolTip(2, state.reason or STATUS_TOOLTIP.get(state.status, ""))
                if entry.is_uploadable:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.CheckState.Checked if key in self._checked else Qt.CheckState.Unchecked)
                group.addChild(item)
                item.setHidden(key not in self._visible)
                self._items[key] = item

    def _item_changed(self, item, column):
        if column != 0:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        keys = self._group_leaves[key] if item.parent() is None else [key]
        eligible = {key for key in keys if key in self.entries and self.entries[key].is_uploadable}
        self._checked = self._checked | eligible if item.checkState(0) == Qt.CheckState.Checked else self._checked - eligible
        self._render_checks()

    def _render_checks(self):
        with QSignalBlocker(self.tree):
            for key, item in self._items.items():
                if self.entries[key].is_uploadable:
                    item.setCheckState(0, Qt.CheckState.Checked if key in self._checked else Qt.CheckState.Unchecked)
            for key, item in self._groups.items():
                leaves = self._group_leaves[key]
                count = sum(leaf in self._checked for leaf in leaves)
                state = Qt.CheckState.Checked if leaves and count == len(leaves) else Qt.CheckState.Unchecked
                if 0 < count < len(leaves):
                    state = Qt.CheckState.PartiallyChecked
                if leaves:
                    item.setCheckState(0, state)
        self.clear_btn.setVisible(bool(self._checked))
        self.selection_changed.emit()

    def _filter(self, *_args):
        term = self.filter_edit.text().casefold()
        self._visible = {key for key, text in self._search_text.items() if term in text}
        self.select_btn.setVisible(bool(term))
        for key, item in self._items.items():
            item.setHidden(key not in self._visible)
        for key, item in self._groups.items():
            item.setHidden(not any(leaf in self._visible for leaf in self._group_entries[key]))
        # 筛选改变会改变「筛选外已勾选」数量，标题行徽标由本信号驱动。
        self.selection_changed.emit()

    def selection_summary(self) -> tuple[int, int, int]:
        """(已勾选数, 其中被当前筛选隐藏的项数, 其中本地缺失的项数)；展示交给标题行 pill 徽标。"""
        return len(self._checked), len(self._checked - self._visible), len(self._checked & self._missing)

    def select_visible(self):
        self._checked = self._checked | {key for key in self._visible if self.entries[key].is_uploadable}
        self._render_checks()

    def clear_selection(self):
        self._checked = set()
        self._render_checks()

    def selected_entries(self) -> list[dict]:
        return [entry.payload() for key, entry in self.entries.items() if key in self._checked]

    def set_statuses(self, statuses: dict[str, UploadState]):
        self._statuses = self._statuses | {key: state for key, state in statuses.items() if key in self.entries}
        for key, state in statuses.items():
            if key not in self.entries:
                continue
            # 会话内新状态即时校正徽标的失效计数（如重推后本地文件恢复）。
            if state.status == UploadStatus.LOCAL_MISSING:
                self._missing.add(key)
            else:
                self._missing.discard(key)
        with QSignalBlocker(self.tree):
            for key, state in statuses.items():
                item = self._items.get(key)
                if item is None:
                    continue
                item.setText(2, self.entries[key].error_text or state.text())
                item.setToolTip(2, state.reason or STATUS_TOOLTIP.get(state.status, ""))
