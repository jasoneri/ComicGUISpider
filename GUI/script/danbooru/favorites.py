from __future__ import annotations

import contextlib
import typing as t

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QSizePolicy,
    QTableWidgetItem, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    FluentIcon as FIF, InfoBar, InfoBarPosition, PrimaryToolButton,
    StrongBodyLabel, TableWidget, ToolButton, TransparentToolButton, TreeWidget, setCustomStyleSheet,
)

from GUI.uic.qfluent.components import AcceptEdit
from utils.config.qc import danbooru_cfg

from .favorite_groups import FavoriteGroupsState, RESERVED_GROUP_NAMES, TagGroup
from .favorite_translate import FavoriteTagTranslateDialogSession
from .style import build_favorites_tree_item_stylesheet

_ROLE_DATA = Qt.UserRole
_TREE_ROW_SIDE_MARGIN = 6
# Compact desktop list: ~28–32px total row (not 44px touch). Was 1 after delBtn removal → cramped.
_TREE_ROW_VERTICAL_MARGIN = 4
_TAG_ROW_MIN_CONTENT_HEIGHT = 22


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


class _PassThroughFrame(QFrame):
    """Layout host that never steals mouse from QTreeWidget ExtendedSelection."""

    def mousePressEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()


class _SelectableTreeRow(QWidget):
    """Display shell for tree item widgets.

    Selection (incl. Ctrl/Shift multi-select) must stay on QTreeWidget like default_table.
    Row chrome therefore does not consume mouse events except real controls (rename).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content = _PassThroughFrame(self)
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

    def __init__(self, group_name: str, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.edit = FavTagGpEdit(group_name, self)
        self.rename_btn = TransparentToolButton(FIF.EDIT, self)
        layout = self.content_layout
        layout.setSpacing(2)
        layout.addWidget(self.edit, 1, Qt.AlignVCenter)
        layout.addWidget(self.rename_btn, 0, Qt.AlignVCenter)

        def request_rename():
            self.rename_requested.emit(self.group_name)

        def submit_rename(_text: str):
            self.rename_submitted.emit(self.group_name)

        self.rename_btn.clicked.connect(request_rename)
        self.edit.custSignal.connect(submit_rename)
        self.sync_height()

    def _hits_interactive_control(self, position) -> bool:
        hit_widget = self.childAt(position)
        while hit_widget is not None and hit_widget is not self:
            if hit_widget is self.rename_btn:
                return True
            if hit_widget is self.edit and not self.edit.isReadOnly():
                return True
            if hit_widget is getattr(self.edit, "btn", None) and self.edit.btn.isVisible():
                return True
            hit_widget = hit_widget.parentWidget()
        return False

    def mousePressEvent(self, event):
        # Pass through to QTreeWidget for ExtendedSelection (Ctrl/Shift), keep rename/edit.
        if not self._hits_interactive_control(event.position().toPoint()):
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._hits_interactive_control(event.position().toPoint()):
            event.ignore()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self._hits_interactive_control(event.position().toPoint()):
            event.ignore()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if not self._hits_interactive_control(event.position().toPoint()):
            event.ignore()
            return
        super().mouseMoveEvent(event)

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
    def __init__(self, group_name: str, tag: str, parent=None, *, display_text: str | None = None):
        super().__init__(parent)
        # Entire tag row is display-only: let tree own selection like default_table cells.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.group_name = group_name
        self.tag = tag
        self.label = StrongBodyLabel(display_text or tag, self)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Label-only rows collapse after delBtn removal; floor keeps scannable density.
        self.label.setMinimumHeight(_TAG_ROW_MIN_CONTENT_HEIGHT)
        layout = self.content_layout
        layout.setSpacing(2)
        layout.addWidget(self.label, 1, Qt.AlignVCenter)
        self.sync_height()

    def set_display_text(self, text: str):
        self.label.setText(text or self.tag)
        self.sync_height()


class DanbooruFavoriteManagerDialog(FramelessDialog):
    def __init__(self, groups_state: FavoriteGroupsState, parent=None):
        super().__init__(parent)
        self._loading = False
        self._syncing_custom_selection = False
        self._editing_group: str | None = None
        self._custom_selection_anchor: QTreeWidgetItem | None = None
        self._groups_state = groups_state
        self._current_group = self._groups_state.ensure_custom_group()
        self.setupUi(self)
        self.translate_session = FavoriteTagTranslateDialogSession(self)
        self.translate_session.install_into_dialog()
        self._configure_tables()
        self.refresh_view()

    def setupUi(self, dialog):
        self.titleBar.closeBtn.hide()
        _ = dialog
        self.resize(880, 560)
        self.setMinimumSize(880, 560)
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
        default_hea_layout = QHBoxLayout(self.default_frame)
        self.default_title = StrongBodyLabel("默认区", self.default_frame)
        self.default_table = TableWidget(self.default_frame)
        self.defaultDelBtn = TransparentToolButton(FIF.DELETE, self.default_frame)
        self.defaultDelBtn.setToolTip("删除选中标签")
        self.defaultDelBtn.clicked.connect(self._delete_selected_default_tags)
        default_hea_layout.addWidget(self.default_title)
        default_hea_layout.addStretch(1)
        default_hea_layout.addWidget(self.defaultDelBtn)
        self.default_layout.addLayout(default_hea_layout)
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
        self.titleHeadRow = QHBoxLayout()
        self.titleHeadRow.setContentsMargins(0, 0, 0, 0)
        self.titleHeadRow.setSpacing(8)
        self.custom_title = StrongBodyLabel("自定义区", self.custom_frame)
        self.titleHeadRow.addWidget(self.custom_title)
        self.titleHeadRow.addStretch(1)
        self.headRow = QHBoxLayout()
        self.headRow.setContentsMargins(0, 0, 0, 0)
        self.headRow.setSpacing(8)
        curr_tip_label = StrongBodyLabel("target group: ", self.custom_frame)
        self.curr_group_label = StrongBodyLabel("", self.custom_frame)
        self.custDelBtn = TransparentToolButton(FIF.DELETE, self.custom_frame)
        self.custDelBtn.setToolTip("删除选中组或标签")
        self.custDelBtn.clicked.connect(self._delete_selected_custom)
        self.new_group_btn = ToolButton(FIF.ADD, self.custom_frame)
        self.new_group_btn.clicked.connect(self._create_group)
        self.headRow.addWidget(curr_tip_label)
        self.headRow.addWidget(self.curr_group_label)
        self.headRow.addStretch(1)
        self.headRow.addWidget(self.custDelBtn)
        self.headRow.addWidget(self.new_group_btn)
        self.custom_tree = TreeWidget(self.custom_frame)
        self.translateEditRow = QHBoxLayout()
        self.translateEditRow.setContentsMargins(0, 0, 0, 0)
        self.translateEditRow.setSpacing(6)
        self.custom_layout.addLayout(self.titleHeadRow)
        self.custom_layout.addLayout(self.headRow)
        self.custom_layout.addWidget(self.custom_tree, 1)
        self.custom_layout.addLayout(self.translateEditRow)

        self.content_layout.addWidget(self.default_frame, 1)
        self.content_layout.addWidget(self.middle_buttons_widget, 0, Qt.AlignVCenter)
        self.content_layout.addWidget(self.custom_frame, 1)
        self.main_layout.addLayout(self.head_layout)
        self.main_layout.addWidget(self.content_widget)

    def _configure_tables(self):
        self.default_table.setColumnCount(1)
        self.default_table.setHorizontalHeaderLabels(["标签"])
        self.default_table.horizontalHeader().hide()
        self.default_table.verticalHeader().hide()
        self.default_table.setBorderVisible(True)
        self.default_table.setWordWrap(False)
        self.default_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.default_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.default_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.default_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
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
        self.translate_session.clear_editor()

    def _apply_groups_change(self, change: t.Callable[[], None]):
        try:
            change()
        except ValueError as exc:
            return InfoBar.error(
                title="", content=str(exc), orient=Qt.Horizontal, isClosable=True, 
                position=InfoBarPosition.TOP, duration=3500, parent=self)
        self.translate_session.on_groups_changed()
        self.refresh_view()

    def _delete_selected_default_tags(self):
        tags = self._selected_default_tags()
        if not tags:
            return InfoBar.warning(
                title="", content="请先选中默认区标签",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
        selected = set(tags)

        def change():
            self._groups_state.set_default_tags(
                current for current in self._groups_state.default_tags if current not in selected
            )
            self.translate_session.drop_cache_keys(tags)

        self._apply_groups_change(change)

    def _delete_selected_custom(self):
        selected_groups = self._selected_group_names()
        if selected_groups:
            selected_group_set = set(selected_groups)

            def change_groups():
                removed_tags = []
                remaining_groups = []
                for group in self._groups_state.custom_groups:
                    if group.name in selected_group_set:
                        removed_tags.extend(group.tags)
                        continue
                    remaining_groups.append(group)
                self._groups_state.custom_groups = remaining_groups
                self._groups_state.ensure_custom_group()
                self.translate_session.drop_cache_keys(removed_tags)
                if self._editing_group in selected_group_set:
                    self._editing_group = None
                if (
                    self._current_group in selected_group_set
                    or self._current_group not in self._groups_state.group_names()
                ):
                    self._current_group = self._groups_state.group_names()[0]

            self._apply_groups_change(change_groups)
            return

        group_name, tags = self._selected_group_tags()
        if not group_name or not tags:
            return InfoBar.warning(
                title="", content="请先选中自定义区的组或标签",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
        selected = set(tags)

        def change_tags():
            group = self._groups_state.group(group_name)
            group.set_tags(current for current in group.tags if current not in selected)
            self.translate_session.drop_cache_keys(tags)
            self._current_group = group.name
            active_origin = self.translate_session.active_editor_origin
            if active_origin and any(
                danbooru_cfg.canonicalize_term(tag) == active_origin for tag in tags
            ):
                self.translate_session.clear_editor()

        self._apply_groups_change(change_tags)

    def _custom_tree_scroll_value(self) -> int:
        scroll_bar = self.custom_tree.verticalScrollBar()
        return scroll_bar.value() if scroll_bar is not None else 0

    def _restore_custom_tree_scroll(self, scroll_value: int):
        scroll_bar = self.custom_tree.verticalScrollBar()
        if scroll_bar is None:
            return
        maximum = scroll_bar.maximum()
        scroll_bar.setValue(max(0, min(scroll_value, maximum)))

    def _find_custom_tree_item(
        self,
        *,
        kind: str | None = None,
        group: str | None = None,
        tag: str | None = None,
    ) -> QTreeWidgetItem | None:
        for group_index in range(self.custom_tree.topLevelItemCount()):
            group_item = self.custom_tree.topLevelItem(group_index)
            group_meta = self._item_meta(group_item)
            group_name = group_meta.get("group", "")
            if group is not None and group_name != group:
                continue
            if kind in (None, "group") and tag is None:
                if kind == "group" or group is not None:
                    return group_item
            for child_index in range(group_item.childCount()):
                tag_item = group_item.child(child_index)
                tag_meta = self._item_meta(tag_item)
                if kind is not None and tag_meta.get("kind") != kind:
                    continue
                if group is not None and tag_meta.get("group") != group:
                    continue
                if tag is not None and tag_meta.get("tag") != tag:
                    continue
                if tag is not None or kind == "tag":
                    return tag_item
        return None

    def _select_custom_item(
        self,
        item: QTreeWidgetItem | None,
        *,
        preserve_scroll: bool = False,
        scroll_hint: int | None = None,
    ):
        """Programmatic single-select (refresh restore / rename). Interactive multi-select is native."""
        if item is None:
            return
        saved_scroll = self._custom_tree_scroll_value() if preserve_scroll else None
        self._syncing_custom_selection = True
        try:
            self.custom_tree.clearSelection()
            item.setSelected(True)
            self.custom_tree.setCurrentItem(item, 0, QItemSelectionModel.NoUpdate)
            item.setSelected(True)
            self._custom_selection_anchor = item
        finally:
            self._syncing_custom_selection = False
        self._handle_custom_selection_changed()
        if preserve_scroll and saved_scroll is not None:
            self._restore_custom_tree_scroll(
                saved_scroll if scroll_hint is None else scroll_hint
            )
            return
        self.custom_tree.scrollToItem(item, QAbstractItemView.EnsureVisible)

    def refresh_view(self):
        def select_group_item(group_name: str, *, preserve_scroll: bool = False, scroll_hint: int | None = None):
            item = self._find_custom_tree_item(kind="group", group=group_name)
            if item is not None:
                self._select_custom_item(
                    item,
                    preserve_scroll=preserve_scroll,
                    scroll_hint=scroll_hint,
                )

        def lookup_group_row(group_name: str) -> FavTagGpRow | None:
            item = self._find_custom_tree_item(kind="group", group=group_name)
            if item is None:
                return None
            row = self.custom_tree.itemWidget(item, 0)
            return row if isinstance(row, FavTagGpRow) else None

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
                if new_name in RESERVED_GROUP_NAMES:
                    raise ValueError(f"收藏组名称不能是 {new_name}")
                if new_name in self._groups_state.group_names() and new_name != group_name:
                    raise ValueError(f"收藏组已存在: {new_name}")
                group = self._groups_state.group(group_name)
                group.name = new_name
                if self._current_group == group_name:
                    self._current_group = new_name
                if self._editing_group == group_name:
                    self._editing_group = None

            self._apply_groups_change(change)

        # Spatial stability: capture focus + scroll before O(n) rebuild.
        pre_scroll = self._custom_tree_scroll_value()
        pre_current = self.custom_tree.currentItem()
        pre_meta = self._item_meta(pre_current)
        restore_kind = pre_meta.get("kind") or "group"
        restore_group = pre_meta.get("group") or self._current_group
        restore_tag = pre_meta.get("tag") if restore_kind == "tag" else None

        self._groups_state.ensure_custom_group()
        group_names = self._groups_state.group_names()
        if self._current_group not in group_names:
            self._current_group = group_names[0]
        if restore_group not in group_names:
            restore_group = self._current_group
            restore_kind = "group"
            restore_tag = None
        if self._editing_group not in group_names:
            self._editing_group = None

        self._loading = True
        try:
            self.default_table.clearContents()
            self.default_table.setRowCount(0)
            for row, tag in enumerate(self._groups_state.default_tags):
                self.default_table.insertRow(row)
                self.default_table.setItem(row, 0, _readonly_table_item(tag, tag))

            self.custom_tree.clear()
            for group in self._groups_state.custom_groups:
                group_row_widget = FavTagGpRow(group.name, self.custom_tree)
                group_item = _tree_item(
                    {"kind": "group", "group": group.name},
                    group_row_widget.height(),
                )
                self.custom_tree.addTopLevelItem(group_item)
                # Selection is native ExtendedSelection on the tree (like default_table).
                # Item widgets only paint / rename; they must not intercept multi-select.
                group_row_widget.rename_requested.connect(begin_group_rename)
                group_row_widget.rename_submitted.connect(
                    lambda current=group.name, editor=group_row_widget.edit: submit_group_rename(current, editor)
                )
                if self._editing_group == group.name:
                    group_row_widget.set_editing(True)
                self.custom_tree.setItemWidget(group_item, 0, group_row_widget)

                for tag in group.tags:
                    tag_row = FavTagRow(
                        group.name,
                        tag,
                        self.custom_tree,
                        display_text=self.translate_session.display_tag(tag),
                    )
                    tag_item = _tree_item(
                        {"kind": "tag", "group": group.name, "tag": tag},
                        tag_row.height(),
                    )
                    group_item.addChild(tag_item)
                    self.custom_tree.setItemWidget(tag_item, 0, tag_row)
            self.custom_tree.expandAll()
        finally:
            self._loading = False

        self.curr_group_label.setText(self._current_group)
        focus_item = None
        if restore_kind == "tag" and restore_tag:
            focus_item = self._find_custom_tree_item(
                kind="tag", group=restore_group, tag=restore_tag
            )
        if focus_item is None and restore_group:
            focus_item = self._find_custom_tree_item(kind="group", group=restore_group)
        if focus_item is None:
            focus_item = self._find_custom_tree_item(kind="group", group=self._current_group)
        if focus_item is not None:
            self._select_custom_item(
                focus_item,
                preserve_scroll=True,
                scroll_hint=pre_scroll,
            )
            self._custom_selection_anchor = focus_item
        else:
            select_group_item(self._current_group, preserve_scroll=True, scroll_hint=pre_scroll)
            self._custom_selection_anchor = self.custom_tree.currentItem()
        self._update_move_buttons()
        if self.translate_session.active_editor_origin and self.translate_session.active_editor_origin not in self._groups_state.all_terms():
            self.translate_session.clear_editor()
        elif self.translate_session.active_editor_origin:
            self.translate_session.bind_editor(self.translate_session.active_editor_origin)

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
            self.translate_session.clear_editor()
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
                self.custom_tree.setCurrentItem(
                    current_item, 0, QItemSelectionModel.NoUpdate
                )
                current_item.setSelected(True)
            finally:
                self._syncing_custom_selection = False

        self._current_group = target_group
        self.curr_group_label.setText(target_group)
        if current_kind == "tag":
            self.translate_session.bind_editor(current_meta.get("tag"))
        else:
            self.translate_session.clear_editor()
        self._update_move_buttons()

    def _create_group(self):
        def change():
            index = 1
            while f"custom{index}" in self._groups_state.group_names():
                index += 1
            self._current_group = f"custom{index}"
            self._groups_state.custom_groups.append(TagGroup(self._current_group, []))

        self._apply_groups_change(change)

    def _move_default_selection_to_current_group(self):
        tags = self._selected_default_tags()
        if not tags:
            return

        def change():
            group = self._groups_state.group(self._current_group)
            selected = set(tags)
            group.add_tags(tags)
            self._groups_state.set_default_tags(
                tag for tag in self._groups_state.default_tags if tag not in selected
            )

        self._apply_groups_change(change)

    def _move_custom_selection_to_default(self):
        selected_groups = self._selected_group_names()
        if selected_groups:
            def change1():
                moved_tags = []
                remaining_groups = []
                for group in self._groups_state.custom_groups:
                    if group.name in selected_groups:
                        moved_tags.extend(group.tags)
                        continue
                    remaining_groups.append(group)
                self._groups_state.custom_groups = remaining_groups
                self._groups_state.ensure_custom_group()
                self._groups_state.set_default_tags(
                    [*self._groups_state.default_tags, *moved_tags]
                )
                if self._editing_group in selected_groups:
                    self._editing_group = None
                if (
                    self._current_group in selected_groups
                    or self._current_group not in self._groups_state.group_names()
                ):
                    self._current_group = self._groups_state.group_names()[0]

            self._apply_groups_change(change1)
            return

        group_name, tags = self._selected_group_tags()
        if not group_name or not tags:
            return

        def change():
            group = self._groups_state.group(group_name)
            selected = set(tags)
            group.set_tags(tag for tag in group.tags if tag not in selected)
            self._groups_state.set_default_tags([*self._groups_state.default_tags, *tags])
            self._current_group = group.name

        self._apply_groups_change(change)

    def _accept_changes(self):
        pruned = self.translate_session.prune_to_living()
        danbooru_cfg.save_translate_map(pruned)
        self.accept()

    @property
    def groups_state(self) -> FavoriteGroupsState:
        return self._groups_state

    @property
    def translate_cache(self) -> dict[str, str]:
        return dict(self.translate_session.cache)
