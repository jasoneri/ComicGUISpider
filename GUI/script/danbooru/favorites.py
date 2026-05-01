from __future__ import annotations

import contextlib
import typing as t
from dataclasses import dataclass, field

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QSizePolicy,
    QTableWidgetItem, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    FluentIcon as FIF, InfoBar, InfoBarPosition, PrimaryToolButton, StrongBodyLabel,
    TableWidget, ToolButton, TransparentToolButton, TreeWidget, setCustomStyleSheet,
)

from GUI.uic.qfluent.components import AcceptEdit
from utils.config.qc import danbooru_cfg

from .favorite_groups import DefaultTagGroup, TagGroup, build_tag_groups
from .style import build_favorites_tree_item_stylesheet

_ROLE_DATA = Qt.UserRole
_TREE_ROW_SIDE_MARGIN = 6
_TREE_ROW_VERTICAL_MARGIN = 1


@dataclass(slots=True)
class FavoriteDialogSnapshot:
    default_group: DefaultTagGroup = field(default_factory=DefaultTagGroup)
    custom_groups: list[TagGroup] = field(default_factory=list)

    @property
    def default_tags(self) -> list[str]:
        return list(self.default_group.tags)

    @property
    def groups(self) -> list[TagGroup]:
        return [self.default_group, *self.custom_groups]

    @property
    def output(self) -> dict[str, list[str]]:
        payload: dict[str, list[str]] = {}
        for group in self.groups:
            payload.update(group.output)
        return payload

    def ensure_custom_group(self) -> str:
        if not self.custom_groups:
            self.custom_groups.append(TagGroup("custom1", []))
        return self.custom_groups[0].name

    def group_names(self) -> list[str]:
        return [group.name for group in self.custom_groups]

    def group(self, group_name: str) -> TagGroup:
        if group_name == self.default_group.name:
            return self.default_group
        for group in self.custom_groups:
            if group.name == group_name:
                return group
        raise ValueError(f"收藏组不存在: {group_name}")

    def set_default_tags(self, tags: t.Iterable[str]):
        self.default_group.set_tags(sorted(tag for tag in tags if tag))


def _readonly_table_item(text: str, role_data: object) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setData(_ROLE_DATA, role_data)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return item


def _tree_item(role_data: object, row_height: int) -> QTreeWidgetItem:
    item = QTreeWidgetItem([""])
    item.setData(0, _ROLE_DATA, role_data)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    item.setSizeHint(0, QSize(0, row_height))
    return item


class _SelectableTreeRow(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content = QFrame(self)
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content.setFrameShape(QFrame.NoFrame)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            _TREE_ROW_SIDE_MARGIN,
            _TREE_ROW_VERTICAL_MARGIN,
            _TREE_ROW_SIDE_MARGIN,
            _TREE_ROW_VERTICAL_MARGIN,
        )
        layout.setSpacing(0)
        layout.addWidget(self.content, 1, Qt.AlignVCenter)
        self.content_layout = QHBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

    def sync_height(self) -> int:
        content_height = self.content.sizeHint().height()
        self.content.setFixedHeight(content_height)
        row_height = content_height + self.layout().contentsMargins().top() + self.layout().contentsMargins().bottom()
        self.setFixedHeight(row_height)
        return row_height

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FavTagGpEdit(AcceptEdit):
    def __init__(self, group_name: str, parent=None):
        super().__init__(parent)
        self.setClearButtonEnabled(False)
        self.setText(group_name)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_editing_state(False)

    def set_editing_state(self, editing: bool):
        self.setReadOnly(not editing)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not editing)
        self.setFocusPolicy(Qt.StrongFocus if editing else Qt.NoFocus)
        self.btn.setVisible(editing)


class FavTagGpRow(_SelectableTreeRow):
    rename_requested = Signal(str)
    rename_submitted = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, group_name: str, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.edit = FavTagGpEdit(group_name, self)
        self.rename_btn = TransparentToolButton(FIF.EDIT, self)
        self.delete_btn = TransparentToolButton(FIF.DELETE, self)
        layout = self.content_layout
        layout.setSpacing(2)
        layout.addWidget(self.edit, 1, Qt.AlignVCenter)
        layout.addWidget(self.rename_btn, 0, Qt.AlignVCenter)
        layout.addWidget(self.delete_btn, 0, Qt.AlignVCenter)
        def request_rename():
            self.clicked.emit()
            self.rename_requested.emit(self.group_name)

        def request_delete():
            self.clicked.emit()
            self.delete_requested.emit(self.group_name)

        def submit_rename(_text: str):
            self.rename_submitted.emit(self.group_name)

        self.rename_btn.clicked.connect(request_rename)
        self.delete_btn.clicked.connect(request_delete)
        self.edit.custSignal.connect(submit_rename)
        self.sync_height()

    def set_editing(self, editing: bool):
        self.edit.set_editing_state(editing)
        self.rename_btn.setEnabled(not editing)
        if editing:
            self.edit.setFocus()
            self.edit.selectAll()
            return
        self.edit.setText(self.group_name)
        self.edit.clearFocus()


class FavTagRow(_SelectableTreeRow):
    delete_requested = Signal(str, str)

    def __init__(self, group_name: str, tag: str, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.tag = tag
        self.label = StrongBodyLabel(tag, self)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.delete_btn = TransparentToolButton(FIF.DELETE, self)
        layout = self.content_layout
        layout.setSpacing(2)
        layout.addWidget(self.label, 1, Qt.AlignVCenter)
        layout.addWidget(self.delete_btn, 0, Qt.AlignVCenter)
        def request_delete():
            self.clicked.emit()
            self.delete_requested.emit(self.group_name, self.tag)

        self.delete_btn.clicked.connect(request_delete)
        self.sync_height()


class DanbooruFavoriteManagerDialog(FramelessDialog):
    favorites_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._syncing_custom_selection = False
        self._editing_group: str | None = None
        self._snapshot = self._load_snapshot()
        self._current_group = self._snapshot.ensure_custom_group()
        self.setupUi(self)
        self._configure_tables()
        self.refresh_view()

    def setupUi(self, dialog):
        self.titleBar.closeBtn.hide()
        _ = dialog
        self.resize(860, 560)
        self.setMinimumSize(860, 560)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 4, 0, 0)
        self.main_layout.setSpacing(8)

        self.content_widget = QWidget(self)
        self.content_layout = QHBoxLayout(self.content_widget)
        self.closeBtn = TransparentToolButton(self)
        self.closeBtn.setIconSize(QSize(20, 20))
        self.closeBtn.setIcon(QIcon(":/close.svg"))
        self.closeBtn.clicked.connect(self.close)
        self.acceptBtn = PrimaryToolButton(FIF.SAVE, dialog)
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
        self.mv_right_btn = ToolButton(FIF.RIGHT_ARROW, self.middle_buttons_widget)
        self.mv_left_btn = ToolButton(FIF.LEFT_ARROW, self.middle_buttons_widget)
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
        curr_tip_label = StrongBodyLabel("target group: ", self.custom_frame)
        self.curr_group_label = StrongBodyLabel("", self.custom_frame)
        self.new_group_btn = ToolButton(FIF.ADD, self.custom_frame)
        self.new_group_btn.clicked.connect(self._create_group)
        self.headRow.addWidget(curr_tip_label)
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
        self.default_table.setHorizontalHeaderLabels(["标签", ""])
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
        self.default_table.itemSelectionChanged.connect(self._update_move_buttons)

        self.custom_tree.setColumnCount(1)
        self.custom_tree.setHeaderLabels(["标签"])
        self.custom_tree.header().hide()
        self.custom_tree.setBorderVisible(True)
        self.custom_tree.setWordWrap(False)
        self.custom_tree.setUniformRowHeights(False)
        self.custom_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.custom_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.custom_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.custom_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        tree_item_qss = build_favorites_tree_item_stylesheet()
        setCustomStyleSheet(self.custom_tree, tree_item_qss, tree_item_qss)
        self.custom_tree.itemSelectionChanged.connect(self._handle_custom_selection_changed)

    def _load_snapshot(self) -> FavoriteDialogSnapshot:
        groups = build_tag_groups(
            sorted(danbooru_cfg.get_favorites()),
            danbooru_cfg.get_grouped_favorites(),
        )
        return FavoriteDialogSnapshot(
            default_group=t.cast(DefaultTagGroup, groups[0]),
            custom_groups=[t.cast(TagGroup, group) for group in groups[1:]],
        )

    def _apply_snapshot_change(self, change: t.Callable[[], None]):
        try:
            change()
        except ValueError as exc:
            return InfoBar.error(
                title="", content=str(exc), orient=Qt.Horizontal, isClosable=True, 
                position=InfoBarPosition.TOP, duration=3500, parent=self)
        self.refresh_view()

    def refresh_view(self):
        def delete_default_tag(tag: str):
            self._apply_snapshot_change(
                lambda: self._snapshot.set_default_tags(
                    current for current in self._snapshot.default_tags if current != tag
                )
            )

        def action_button(icon, callback: t.Callable[[], None], tooltip: str | None = None):
            button = TransparentToolButton(icon, self)
            button.setFixedSize(32, 32)
            if tooltip:
                button.setToolTip(tooltip)
            button.clicked.connect(callback)
            return button

        def select_group_item(group_name: str):
            for index in range(self.custom_tree.topLevelItemCount()):
                item = self.custom_tree.topLevelItem(index)
                if self._item_meta(item).get("group") == group_name:
                    self._select_custom_item(item)
                    return

        def lookup_group_row(group_name: str) -> FavTagGpRow | None:
            for index in range(self.custom_tree.topLevelItemCount()):
                item = self.custom_tree.topLevelItem(index)
                if self._item_meta(item).get("group") != group_name:
                    continue
                row = self.custom_tree.itemWidget(item, 0)
                return row if isinstance(row, FavTagGpRow) else None
            return None

        def begin_group_rename(group_name: str):
            if self._editing_group and self._editing_group != group_name:
                previous_row = lookup_group_row(self._editing_group)
                if previous_row is not None:
                    previous_row.set_editing(False)
            self._editing_group = group_name
            self._current_group = group_name
            self.curr_group_label.setText(group_name)
            select_group_item(group_name)
            row = lookup_group_row(group_name)
            if row is not None:
                row.set_editing(True)

        def submit_group_rename(group_name: str, editor: FavTagGpEdit):
            new_name = danbooru_cfg.canonicalize_term(editor.text())

            def change():
                if not new_name:
                    raise ValueError("收藏组名称不能为空")
                if new_name in danbooru_cfg.RESERVED_SEARCH_KEYS:
                    raise ValueError(f"收藏组名称不能是 {new_name}")
                if new_name in self._snapshot.group_names() and new_name != group_name:
                    raise ValueError(f"收藏组已存在: {new_name}")
                group = self._snapshot.group(group_name)
                group.name = new_name
                if self._current_group == group_name:
                    self._current_group = new_name
                if self._editing_group == group_name:
                    self._editing_group = None

            self._apply_snapshot_change(change)

        def delete_group_tag(group_name: str, tag: str):
            def change():
                group = self._snapshot.group(group_name)
                group.set_tags(current for current in group.tags if current != tag)
                self._current_group = group.name

            self._apply_snapshot_change(change)

        def delete_group(group_name: str):
            def change():
                self._snapshot.custom_groups = [
                    group
                    for group in self._snapshot.custom_groups
                    if group.name != group_name
                ]
                self._snapshot.ensure_custom_group()
                if self._editing_group == group_name:
                    self._editing_group = None
                if (
                    self._current_group == group_name
                    or self._current_group not in self._snapshot.group_names()
                ):
                    self._current_group = self._snapshot.group_names()[0]

            self._apply_snapshot_change(change)

        self._snapshot.ensure_custom_group()
        group_names = self._snapshot.group_names()
        if self._current_group not in group_names:
            self._current_group = group_names[0]
        if self._editing_group not in group_names:
            self._editing_group = None

        self._loading = True
        try:
            self.default_table.clearContents()
            self.default_table.setRowCount(0)
            for row, tag in enumerate(self._snapshot.default_tags):
                self.default_table.insertRow(row)
                self.default_table.setItem(row, 0, _readonly_table_item(tag, tag))
                self.default_table.setCellWidget(row, 1,
                    action_button(
                        FIF.DELETE, lambda checked=False, current=tag: delete_default_tag(current), f"删除 {tag}",
                    ),
                )

            self.custom_tree.clear()
            for group in self._snapshot.custom_groups:
                group_row_widget = FavTagGpRow(group.name, self.custom_tree)
                group_item = _tree_item(
                    {"kind": "group", "group": group.name},
                    group_row_widget.height(),
                )
                self.custom_tree.addTopLevelItem(group_item)
                group_row_widget.clicked.connect(
                    lambda current=group_item: self._select_custom_item(current)
                )
                group_row_widget.rename_requested.connect(begin_group_rename)
                group_row_widget.rename_submitted.connect(
                    lambda current=group.name, editor=group_row_widget.edit: submit_group_rename(current, editor)
                )
                group_row_widget.delete_requested.connect(delete_group)
                if self._editing_group == group.name:
                    group_row_widget.set_editing(True)
                self.custom_tree.setItemWidget(group_item, 0, group_row_widget)

                for tag in group.tags:
                    tag_row = FavTagRow(group.name, tag, self.custom_tree)
                    tag_item = _tree_item(
                        {"kind": "tag", "group": group.name, "tag": tag},
                        tag_row.height(),
                    )
                    group_item.addChild(tag_item)
                    tag_row.clicked.connect(
                        lambda current=tag_item: self._select_custom_item(current)
                    )
                    tag_row.delete_requested.connect(delete_group_tag)
                    self.custom_tree.setItemWidget(tag_item, 0, tag_row)
            self.custom_tree.expandAll()
        finally:
            self._loading = False

        self.curr_group_label.setText(self._current_group)
        select_group_item(self._current_group)
        self._update_move_buttons()

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

    def _select_custom_item(self, item: QTreeWidgetItem | None):
        if item is None:
            return
        self._syncing_custom_selection = True
        try:
            self.custom_tree.clearSelection()
            item.setSelected(True)
            self.custom_tree.setCurrentItem(item)
        finally:
            self._syncing_custom_selection = False
        self._handle_custom_selection_changed()

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

    def _update_move_buttons(self):
        self.mv_right_btn.setEnabled(bool(self._selected_default_tags()))
        selected_groups = self._selected_group_names()
        group_name, tags = self._selected_group_tags()
        self.mv_left_btn.setEnabled(bool(selected_groups or group_name or tags))

    def _handle_custom_selection_changed(self):
        if self._loading or self._syncing_custom_selection:
            self._update_move_buttons()
            return
        selected_items = self.custom_tree.selectedItems()
        if not selected_items:
            self._update_move_buttons()
            return
        current_item = self.custom_tree.currentItem() or selected_items[-1]
        current_meta = self._item_meta(current_item)
        target_group = current_meta.get("group", "")
        current_kind = current_meta.get("kind", "")
        if not target_group or not current_kind:
            self._update_move_buttons()
            return

        filtered = [
            item
            for item in selected_items
            if self._item_meta(item).get("kind") == current_kind
            and (
                current_kind != "tag"
                or self._item_meta(item).get("group") == target_group
            )
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
        self.curr_group_label.setText(target_group)
        self._update_move_buttons()

    def _create_group(self):
        def change():
            index = 1
            while f"custom{index}" in self._snapshot.group_names():
                index += 1
            self._current_group = f"custom{index}"
            self._snapshot.custom_groups.append(TagGroup(self._current_group, []))

        self._apply_snapshot_change(change)

    def _move_default_selection_to_current_group(self):
        tags = self._selected_default_tags()
        if not tags:
            return

        def change():
            group = self._snapshot.group(self._current_group)
            selected = set(tags)
            group.add_tags(tags)
            self._snapshot.set_default_tags(
                tag for tag in self._snapshot.default_tags if tag not in selected
            )

        self._apply_snapshot_change(change)

    def _move_custom_selection_to_default(self):
        selected_groups = self._selected_group_names()
        if selected_groups:
            def change1():
                moved_tags = []
                remaining_groups = []
                for group in self._snapshot.custom_groups:
                    if group.name in selected_groups:
                        moved_tags.extend(group.tags)
                        continue
                    remaining_groups.append(group)
                self._snapshot.custom_groups = remaining_groups
                self._snapshot.ensure_custom_group()
                self._snapshot.set_default_tags(
                    [*self._snapshot.default_tags, *moved_tags]
                )
                if self._editing_group in selected_groups:
                    self._editing_group = None
                if (
                    self._current_group in selected_groups
                    or self._current_group not in self._snapshot.group_names()
                ):
                    self._current_group = self._snapshot.group_names()[0]

            self._apply_snapshot_change(change1)
            return

        group_name, tags = self._selected_group_tags()
        if not group_name or not tags:
            return

        def change():
            group = self._snapshot.group(group_name)
            selected = set(tags)
            group.set_tags(tag for tag in group.tags if tag not in selected)
            self._snapshot.set_default_tags([*self._snapshot.default_tags, *tags])
            self._current_group = group.name

        self._apply_snapshot_change(change)

    def _accept_changes(self):
        danbooru_cfg.save_grouped_favorites(self._snapshot.output)
        self.favorites_changed.emit()
        self.accept()
