from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import typing as t

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QTableWidgetItem,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, MessageBoxBase,
    StrongBodyLabel, SubtitleLabel, TableWidget, ToolButton, PrimaryToolButton,
    TransparentToolButton, TreeWidget,
)

from GUI.uic.qfluent.components import AcceptEdit
from utils.config.qc import danbooru_cfg

_ROLE_DATA = Qt.UserRole


@dataclass(slots=True)
class FavoriteGroupSnapshot:
    name: str
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FavoriteDialogSnapshot:
    default_tags: list[str] = field(default_factory=list)
    custom_groups: list[FavoriteGroupSnapshot] = field(default_factory=list)

    def ensure_custom_group(self):
        if not self.custom_groups:
            self.custom_groups.append(FavoriteGroupSnapshot("custom1", []))

    def group_names(self) -> list[str]:
        return [group.name for group in self.custom_groups]

    def group(self, group_name: str) -> FavoriteGroupSnapshot:
        for group in self.custom_groups:
            if group.name == group_name:
                return group
        raise ValueError(f"收藏组不存在: {group_name}")

    def set_default_tags(self, tags: t.Iterable[str]):
        self.default_tags = sorted(dict.fromkeys(tag for tag in tags if tag))


def _readonly_table_item(text: str, role_data: object) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setData(_ROLE_DATA, role_data)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return item


def _readonly_tree_item(text: str, role_data: object) -> QTreeWidgetItem:
    item = QTreeWidgetItem([text, "", ""])
    item.setData(0, _ROLE_DATA, role_data)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return item


class DanbooruFavoriteNameDialog(MessageBoxBase):
    """.discard()"""

class DanbooruFavoriteManagerDialog(FramelessDialog):
    favorites_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._syncing_custom_selection = False
        self._snapshot = self._load_snapshot()
        self._current_group = self._snapshot.custom_groups[0].name
        self.setupUi(self)
        self._configure_tables()
        self.refresh_view()

    def setupUi(self, Dialog):
        self.titleBar.closeBtn.hide()
        _ = Dialog
        self.resize(860, 560)
        self.setMinimumSize(860, 560)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 4, 0, 0)
        self.main_layout.setSpacing(8)

        self.content_widget = QWidget(self)
        self.content_layout = QHBoxLayout(self.content_widget)
        self.closeBtn = TransparentToolButton(self)
        self.closeBtn.setIconSize(QSize(20, 20))
        self.closeBtn.setIcon(QIcon(':/close.svg'))
        self.closeBtn.clicked.connect(self.close)
        self.acceptBtn = PrimaryToolButton(FIF.SAVE, Dialog)
        self.acceptBtn.setToolTip("保存收藏")
        self.acceptBtn.clicked.connect(self._accept_changes)
        self.head_layout = QHBoxLayout()
        self.head_layout.addStretch()
        self.head_layout.addWidget(self.acceptBtn)
        self.head_layout.addWidget(self.closeBtn)
        self.content_layout.setContentsMargins(12, 8, 12, 12)
        self.content_layout.setSpacing(8)

        self.default_frame = QFrame(self.content_widget)
        self.default_layout = QVBoxLayout(self.default_frame)
        self.default_layout.setContentsMargins(0, 0, 0, 0)
        self.default_layout.setSpacing(8)
        self.default_title = StrongBodyLabel("默认区", self.default_frame)
        self.default_table = TableWidget(self.default_frame)
        self.default_layout.addWidget(self.default_title)
        self.default_layout.addWidget(self.default_table, 1)

        self.middle_buttons_widget = QWidget(self.content_widget)
        self.middle_buttons_layout = QVBoxLayout(self.middle_buttons_widget)
        self.middle_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.middle_buttons_layout.setSpacing(10)
        self.middle_buttons_layout.addStretch(1)
        self.mv_right_btn = TransparentToolButton(FIF.RIGHT_ARROW, self.middle_buttons_widget)
        self.mv_left_btn = TransparentToolButton(FIF.LEFT_ARROW, self.middle_buttons_widget)
        self.mv_right_btn.clicked.connect(self._move_default_selection_to_current_group)
        self.mv_left_btn.clicked.connect(self._move_custom_selection_to_default)
        self.middle_buttons_layout.addWidget(self.mv_right_btn)
        self.middle_buttons_layout.addWidget(self.mv_left_btn)
        self.middle_buttons_layout.addStretch(1)

        self.custom_frame = QFrame(self.content_widget)
        self.custom_layout = QVBoxLayout(self.custom_frame)
        self.custom_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_layout.setSpacing(8)
        self.custom_title = StrongBodyLabel("自定义区", self.custom_frame)
        self.headRow = QHBoxLayout()
        self.headRow.setContentsMargins(0, 0, 0, 0)
        self.headRow.setSpacing(8)
        self.curr_group_label = StrongBodyLabel("", self.custom_frame)
        self.new_group_btn = TransparentToolButton(FIF.ADD, self.custom_frame)
        self.new_group_btn.clicked.connect(self._create_group)
        self.headRow.addWidget(self.curr_group_label)
        self.headRow.addStretch(1)
        self.headRow.addWidget(self.new_group_btn)
        self.custom_tree = TreeWidget(self.custom_frame)
        self.custom_layout.addWidget(self.custom_title)
        self.custom_layout.addLayout(self.headRow)
        self.custom_layout.addWidget(self.custom_tree, 1)

        self.content_layout.addWidget(self.default_frame, 1)
        self.content_layout.addWidget(self.middle_buttons_widget, 0, Qt.AlignVCenter)
        self.content_layout.addWidget(self.custom_frame, 1)
        self.main_layout.addLayout(self.head_layout)
        self.main_layout.addWidget(self.content_widget)

    def _configure_tables(self):
        self.default_table.setColumnCount(2)
        self.default_table.horizontalHeader().hide()
        self.default_table.verticalHeader().hide()
        self.default_table.setBorderVisible(True)
        self.default_table.setWordWrap(False)
        self.default_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.default_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.default_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.default_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.default_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.default_table.setColumnWidth(1, 40)
        with contextlib.suppress(RuntimeError, TypeError):
            self.default_table.entered.disconnect()
        self.default_table.setMouseTracking(False)
        self.default_table.viewport().setMouseTracking(False)
        self.default_table.delegate.setHoverRow(-1)

        self.custom_tree.setColumnCount(3)
        self.custom_tree.header().hide()
        self.custom_tree.setBorderVisible(True)
        self.custom_tree.setWordWrap(False)
        self.custom_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.custom_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.custom_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.custom_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.custom_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.custom_tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.custom_tree.setColumnWidth(1, 40)
        self.custom_tree.setColumnWidth(2, 40)
        self.custom_tree.itemSelectionChanged.connect(self._handle_custom_selection_changed)

    def _load_snapshot(self) -> FavoriteDialogSnapshot:
        groups = [
            FavoriteGroupSnapshot(group_name, list(tags))
            for group_name, tags in danbooru_cfg.get_grouped_favorites()
        ]
        if not groups:
            groups = [FavoriteGroupSnapshot("custom1", [])]
        return FavoriteDialogSnapshot(
            default_tags=sorted(danbooru_cfg.get_favorites()),
            custom_groups=groups,
        )

    def _tool_button(self, icon, tooltip: str, callback: t.Callable[[], None]):
        button = TransparentToolButton(icon, self)
        button.setFixedSize(28, 28)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def _apply_snapshot_change(
        self,
        change: t.Callable[[], None],
    ):
        def _show_info(factory, content: str, duration: int = 2500):
            factory(
                title="", content=content, orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=duration, parent=self,
            )

        try:
            change()
        except ValueError as exc:
            _show_info(InfoBar.error, str(exc), 3500)
            return
        self.refresh_view()

    def refresh_view(self):
        def _delete_default_tag(tag: str):
            self._apply_snapshot_change(
                lambda: self._snapshot.set_default_tags(current for current in self._snapshot.default_tags if current != tag)
            )

        self._snapshot.ensure_custom_group()
        group_names = self._snapshot.group_names()
        if self._current_group not in group_names:
            self._current_group = group_names[0]

        self._loading = True
        try:
            self.default_table.clearContents()
            self.default_table.setRowCount(0)
            for row, tag in enumerate(self._snapshot.default_tags):
                self.default_table.insertRow(row)
                self.default_table.setItem(row, 0, _readonly_table_item(tag, tag))
                self.default_table.setCellWidget(row,1,
                    self._tool_button(FIF.DELETE,f"删除 {tag}",lambda checked=False, current=tag: _delete_default_tag(current),
                    ),
                )

            self.custom_tree.clear()
            for group in self._snapshot.custom_groups:
                group_item = _readonly_tree_item(group.name, {"kind": "group", "group": group.name})
                self.custom_tree.addTopLevelItem(group_item)
                self.custom_tree.setItemWidget(group_item, 1,
                    self._tool_button(FIF.EDIT, f"重命名 {group.name}",
                        lambda checked=False, current=group.name: self._rename_group(current),
                    ),
                )
                self.custom_tree.setItemWidget(group_item, 2,
                    self._tool_button(FIF.DELETE, f"删除 {group.name}",
                        lambda checked=False, current=group.name: self._delete_group(current),
                    ),
                )
                for tag in group.tags:
                    tag_item = _readonly_tree_item(tag, {"kind": "tag", "group": group.name, "tag": tag})
                    group_item.addChild(tag_item)
                    self.custom_tree.setItemWidget(tag_item, 2,
                        self._tool_button(FIF.DELETE, f"删除 {tag}",
                            lambda checked=False, group_name=group.name, current=tag: self._delete_group_tag(group_name, current),
                        ),
                    )
            self.custom_tree.expandAll()
        finally:
            self._loading = False

        self.curr_group_label.setText(f"target: {self._current_group}")
        self._syncing_custom_selection = True
        try:
            self.custom_tree.clearSelection()
            for index in range(self.custom_tree.topLevelItemCount()):
                item = self.custom_tree.topLevelItem(index)
                if self._item_meta(item).get("group") != self._current_group:
                    continue
                item.setSelected(True)
                self.custom_tree.setCurrentItem(item)
                break
        finally:
            self._syncing_custom_selection = False

    def _selected_default_rows(self) -> list[int]:
        selection_model = self.default_table.selectionModel()
        if selection_model is None or not selection_model.hasSelection():
            return []
        return sorted(index.row() for index in selection_model.selectedRows())

    def _selected_default_tags(self) -> list[str]:
        selected_tags = []
        for row in self._selected_default_rows():
            item = self.default_table.item(row, 0)
            if item is None:
                continue
            tag = str(item.data(_ROLE_DATA) or "").strip()
            if tag:
                selected_tags.append(tag)
        return selected_tags

    def default_table_selection_snapshot(self) -> dict[str, t.Any]:
        selected_rows = self._selected_default_rows()
        return {
            "selected_rows": selected_rows,
            "selected_tags": self._selected_default_tags(),
        }

    def _item_meta(self, item: QTreeWidgetItem | None) -> dict[str, str]:
        if item is None:
            return {}
        payload = item.data(0, _ROLE_DATA)
        return payload if isinstance(payload, dict) else {}

    def _selected_group_names(self) -> list[str]:
        group_names = []
        for item in self.custom_tree.selectedItems():
            meta = self._item_meta(item)
            if meta.get("kind") != "group":
                continue
            group_name = meta.get("group", "")
            if group_name and group_name not in group_names:
                group_names.append(group_name)
        return group_names

    def _selected_group_tags(self) -> tuple[str | None, list[str]]:
        group_name = None
        tags = []
        for item in self.custom_tree.selectedItems():
            meta = self._item_meta(item)
            if meta.get("kind") != "tag":
                continue
            item_group = meta.get("group", "")
            tag = meta.get("tag", "")
            if not item_group or not tag:
                continue
            if group_name is None:
                group_name = item_group
            if item_group != group_name:
                continue
            if tag not in tags:
                tags.append(tag)
        return group_name, tags

    def _handle_custom_selection_changed(self):
        if self._loading or self._syncing_custom_selection:
            return
        selected_items = self.custom_tree.selectedItems()
        if not selected_items:
            return
        current_item = self.custom_tree.currentItem() or selected_items[-1]
        current_meta = self._item_meta(current_item)
        target_group = current_meta.get("group", "")
        if not target_group:
            return

        filtered = [
            item for item in selected_items
            if self._item_meta(item).get("kind") == current_meta.get("kind")
            and (current_meta.get("kind") != "tag" or self._item_meta(item).get("group") == target_group)
        ]
        if len(filtered) != len(selected_items):
            self._syncing_custom_selection = True
            try:
                self.custom_tree.clearSelection()
                for item in filtered:
                    item.setSelected(True)
                current_item.setSelected(True)
                self.custom_tree.setCurrentItem(current_item)
            finally:
                self._syncing_custom_selection = False

        self._current_group = target_group
        self.curr_group_label.setText(f"target: {target_group}")

    def _delete_group_tag(self, group_name: str, tag: str):
        def change():
            group = self._snapshot.group(group_name)
            group.tags = [current for current in group.tags if current != tag]
            self._current_group = group.name
        self._apply_snapshot_change(change)

    def _create_group(self):
        def change():
            index = 1
            while f"custom{index}" in self._snapshot.group_names():
                index += 1
            self._current_group = f"custom{index}"
            self._snapshot.custom_groups.append(FavoriteGroupSnapshot(self._current_group, []))
        self._apply_snapshot_change(change)

    def _rename_group(self, group_name: str):
        dialog = DanbooruFavoriteNameDialog("重命名收藏组", group_name, self)
        if not dialog.exec():
            return

        def change():
            if dialog.value in danbooru_cfg.RESERVED_SEARCH_KEYS:
                raise ValueError(f"收藏组名称不能是 {dialog.value}")
            if dialog.value in self._snapshot.group_names() and dialog.value != group_name:
                raise ValueError(f"收藏组已存在: {dialog.value}")
            group = self._snapshot.group(group_name)
            group.name = dialog.value
            if self._current_group == group_name:
                self._current_group = dialog.value

        self._apply_snapshot_change(change)

    def _delete_group(self, group_name: str):
        def change():
            self._snapshot.custom_groups = [
                group for group in self._snapshot.custom_groups
                if group.name != group_name
            ]
            self._snapshot.ensure_custom_group()
            if self._current_group == group_name or self._current_group not in self._snapshot.group_names():
                self._current_group = self._snapshot.custom_groups[0].name
        self._apply_snapshot_change(change)

    def _move_default_selection_to_current_group(self):
        tags = self._selected_default_tags()
        if not tags:
            return

        def change():
            group = self._snapshot.group(self._current_group)
            selected = set(tags)
            group.tags.extend(tag for tag in tags if tag not in group.tags)
            self._snapshot.set_default_tags(tag for tag in self._snapshot.default_tags if tag not in selected)
        self._apply_snapshot_change(change)

    def _move_custom_selection_to_default(self):
        selected_groups = self._selected_group_names()
        if selected_groups:
            def change():
                moved_tags = []
                remaining_groups = []
                for group in self._snapshot.custom_groups:
                    if group.name in selected_groups:
                        moved_tags.extend(group.tags)
                        continue
                    remaining_groups.append(group)
                self._snapshot.custom_groups = remaining_groups
                self._snapshot.ensure_custom_group()
                self._snapshot.set_default_tags([*self._snapshot.default_tags, *moved_tags])
                if self._current_group in selected_groups or self._current_group not in self._snapshot.group_names():
                    self._current_group = self._snapshot.custom_groups[0].name
            return self._apply_snapshot_change(change)

        group_name, tags = self._selected_group_tags()
        if not group_name or not tags:
            return

        def change():
            group = self._snapshot.group(group_name)
            selected = set(tags)
            group.tags = [tag for tag in group.tags if tag not in selected]
            self._snapshot.set_default_tags([*self._snapshot.default_tags, *tags])
            self._current_group = group.name

        self._apply_snapshot_change(change)

    def _accept_changes(self):
        danbooru_cfg.save_grouped_favorites(
            {"Favorites": list(self._snapshot.default_tags), **{group.name: list(group.tags) for group in self._snapshot.custom_groups}}
        )
        self.favorites_changed.emit()
        self.accept()
