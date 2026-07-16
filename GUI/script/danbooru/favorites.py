from __future__ import annotations

import contextlib
import typing as t

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QSizePolicy,
    QTableWidgetItem, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from shiboken6 import isValid as qt_object_is_valid
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    ComboBox, FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, PrimaryToolButton,
    StrongBodyLabel, TableWidget, TeachingTipTailPosition, TogglePushButton, ToolButton,
    TransparentToolButton, TreeWidget, setCustomStyleSheet,
)

from GUI.uic.qfluent.components import AcceptEdit, CustomTeachingTip
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.config.qc import danbooru_cfg
from utils.script.ai.kernel import is_ai_provider_configured

from .favorite_groups import FavoriteGroupsState, RESERVED_GROUP_NAMES, TagGroup
from .style import build_favorites_tree_item_stylesheet

_ROLE_DATA = Qt.UserRole
_TREE_ROW_SIDE_MARGIN = 6
_TREE_ROW_VERTICAL_MARGIN = 1


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

    def __init__(self, group_name: str, tag: str, parent=None, *, display_text: str | None = None):
        super().__init__(parent)
        self.group_name = group_name
        self.tag = tag
        self.label = StrongBodyLabel(display_text or tag, self)
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

    def set_display_text(self, text: str):
        self.label.setText(text or self.tag)
        self.sync_height()


class GroupChoicePanel(QWidget):
    COLUMNS = 3
    selection_changed = Signal(list)

    def __init__(self, group_names: list[str], selected_names: set[str], parent=None):
        super().__init__(parent)
        self.group_buttons: dict[str, TogglePushButton] = {}
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for offset, group_name in enumerate(group_names):
            button = TogglePushButton(self)
            button.setText(group_name)
            button.setToolTip(group_name)
            button.setCheckable(True)
            button.setChecked(group_name in selected_names)
            button.setMinimumWidth(100)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.toggled.connect(lambda *_args: self._emit_selection_changed())
            grid.addWidget(button, offset // self.COLUMNS, offset % self.COLUMNS)
            self.group_buttons[group_name] = button
        layout.addWidget(grid_host)

    def selected_group_names(self) -> list[str]:
        return [name for name, button in self.group_buttons.items() if button.isChecked()]

    def all_groups_selected(self) -> bool:
        return bool(self.group_buttons) and all(
            button.isChecked()
            for button in self.group_buttons.values()
        )

    def set_all_groups_selected(self, selected: bool):
        for button in self.group_buttons.values():
            button.setChecked(selected)
        self._emit_selection_changed()

    def _emit_selection_changed(self):
        self.selection_changed.emit(self.selected_group_names())


class DanbooruFavoriteManagerDialog(FramelessDialog):
    def __init__(self, groups_state: FavoriteGroupsState, parent=None):
        super().__init__(parent)
        self._loading = False
        self._syncing_custom_selection = False
        self._editing_group: str | None = None
        self._groups_state = groups_state
        self._current_group = self._groups_state.ensure_custom_group()
        self._translate_cache: dict[str, str] = dict(danbooru_cfg.get_translate_map())
        self._active_translate_groups: set[str] = set(self._groups_state.group_names())
        self._group_choice_tip = None
        self._translate_running = False
        self._active_editor_origin: str | None = None
        self.setupUi(self)
        self._configure_tables()
        self._sync_translate_entry_visibility()
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
        self.titleHeadRow = QHBoxLayout()
        self.titleHeadRow.setContentsMargins(0, 0, 0, 0)
        self.titleHeadRow.setSpacing(8)
        self.custom_title = StrongBodyLabel("自定义区", self.custom_frame)
        self.titleHeadRow.addWidget(self.custom_title)
        self.titleHeadRow.addStretch(1)
        self.translateBtnGroup = QWidget(self.custom_frame)
        self.translateBtnGroupLayout = QHBoxLayout(self.translateBtnGroup)
        self.translateBtnGroupLayout.setContentsMargins(0, 0, 0, 0)
        self.translateBtnGroupLayout.setSpacing(6)
        self.transferBtn = TransparentToolButton(CgsIcon.SCRIPT_TRANSLATE_AI, self.translateBtnGroup)
        self.transferBtn.setToolTip("展开标签翻译")
        self.transferBtn.clicked.connect(self._expand_translate_controls)
        self.groupSelectBtn = ToolButton(FIF.MENU, self.translateBtnGroup)
        self.groupSelectBtn.setToolTip("选择要翻译的收藏组")
        self.groupSelectBtn.clicked.connect(self._show_group_choice_tip)
        self.groupSelectBtn.hide()
        self.searchSiteBox = ComboBox(self.translateBtnGroup)
        # Danbooru wiki is always collected; selected engine enriches (no static series maps).
        self.searchSiteBox.addItem("Danbooru Wiki", userData="danbooru")
        self.searchSiteBox.addItem("萌娘百科", userData="moegirl")
        self.searchSiteBox.addItem("百度", userData="baidu")
        self.searchSiteBox.addItem("Google", userData="google")
        self.searchSiteBox.addItem("Bing", userData="bing")
        self.searchSiteBox.setMinimumWidth(108)
        self.searchSiteBox.hide()
        self.languageBox = ComboBox(self.translateBtnGroup)
        self.languageBox.addItem("中文", userData="zh")
        self.languageBox.addItem("日本語", userData="ja")
        self.languageBox.setMinimumWidth(88)
        self.languageBox.hide()
        self.runTranslateBtn = PrimaryToolButton(CgsIcon.SCRIPT_RUN, self.translateBtnGroup)
        self.runTranslateBtn.setToolTip("开始翻译")
        self.runTranslateBtn.clicked.connect(self._run_translate)
        self.runTranslateBtn.hide()
        self.translateBtnGroupLayout.addWidget(self.transferBtn)
        self.translateBtnGroupLayout.addWidget(self.groupSelectBtn)
        self.translateBtnGroupLayout.addWidget(self.searchSiteBox)
        self.translateBtnGroupLayout.addWidget(self.languageBox)
        self.translateBtnGroupLayout.addWidget(self.runTranslateBtn)
        self.translateBtnGroup.hide()
        self.titleHeadRow.addWidget(self.translateBtnGroup)
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
        self.translateEditRow = QHBoxLayout()
        self.translateEditRow.setContentsMargins(0, 0, 0, 0)
        self.translateEditRow.setSpacing(6)
        self.oriTagStrongLabel = StrongBodyLabel("origin:", self.custom_frame)
        self.oriTagLabel = StrongBodyLabel("-", self.custom_frame)
        self.oriTagLabel.setMinimumWidth(120)
        self.translatedTagLabel = StrongBodyLabel("display:", self.custom_frame)
        self.translatedTagInput = LineEdit(self.custom_frame)
        self.translatedTagInput.setClearButtonEnabled(True)
        self.translatedTagInput.setPlaceholderText("显示名")
        self.translateSvBtn = ToolButton(CgsIcon.SCRIPT_GENERATE, self.custom_frame)
        self.translateSvBtn.setToolTip("保存当前显示名到缓存")
        self.translateSvBtn.clicked.connect(self._save_active_translation)
        self.translateEditRow.addWidget(self.oriTagStrongLabel)
        self.translateEditRow.addWidget(self.oriTagLabel, 1)
        self.translateEditRow.addWidget(self.translatedTagLabel)
        self.translateEditRow.addWidget(self.translatedTagInput, 1)
        self.translateEditRow.addWidget(self.translateSvBtn)
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
        self._clear_translate_editor()

    def _display_tag(self, origin: str) -> str:
        canonical = danbooru_cfg.canonicalize_term(origin)
        if not canonical:
            return ""
        return self._translate_cache.get(canonical) or canonical

    def _drop_translate_cache_keys(self, tags: t.Iterable[str], *, force: bool = False):
        living_tags = set() if force else self._groups_state.all_terms()
        dropped: list[str] = []
        for raw_tag in tags:
            canonical = danbooru_cfg.canonicalize_term(str(raw_tag))
            if not canonical:
                continue
            if force or canonical not in living_tags:
                self._translate_cache.pop(canonical, None)
                dropped.append(canonical)
        if dropped:
            # Keep disk map aligned with background-persist UX (do not wait for FavMgr accept).
            danbooru_cfg.drop_translate_keys(dropped)

    def _sync_translate_entry_visibility(self):
        configured = is_ai_provider_configured()
        self.translateBtnGroup.setVisible(configured)
        if not configured:
            self.transferBtn.show()
            self.groupSelectBtn.hide()
            self.searchSiteBox.hide()
            self.languageBox.hide()
            self.runTranslateBtn.hide()
            if self._group_choice_tip is not None:
                self._group_choice_tip.close()
                self._group_choice_tip = None

    def _expand_translate_controls(self):
        self.transferBtn.hide()
        self.groupSelectBtn.show()
        self.searchSiteBox.show()
        self.languageBox.show()
        self.runTranslateBtn.show()
        available = set(self._groups_state.group_names())
        if not self._active_translate_groups:
            self._active_translate_groups = set(available)
        else:
            self._active_translate_groups &= available
            if not self._active_translate_groups:
                self._active_translate_groups = set(available)

    def _apply_translate_group_selection(self, selected_names: t.Iterable[str], *, fallback_all: bool = False):
        available = set(self._groups_state.group_names())
        selected = {
            name
            for raw_name in selected_names
            if (name := str(raw_name or "").strip()) and name in available
        }
        if selected:
            self._active_translate_groups = selected
            return selected
        if fallback_all:
            self._active_translate_groups = set(available)
            return set(available)
        # Empty selection is valid: runTranslate will warn "no tags".
        self._active_translate_groups = set()
        return set()

    def _sync_translate_groups_from_open_tip(self):
        """Flush live panel toggles even if tip is still open when run is clicked."""
        tip = self._group_choice_tip
        if tip is None or not qt_object_is_valid(tip):
            return
        panel = getattr(tip, "_translate_group_panel", None)
        if panel is None or not qt_object_is_valid(panel):
            return
        self._apply_translate_group_selection(panel.selected_group_names(), fallback_all=False)

    def _show_group_choice_tip(self):
        if self._group_choice_tip is not None:
            self._group_choice_tip.close()
            self._group_choice_tip = None
        group_names = self._groups_state.group_names()
        if not group_names:
            return InfoBar.warning(
                title="", content="暂无自定义收藏组",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
        selected = set(self._active_translate_groups) & set(group_names)
        if not selected:
            selected = set(group_names)
            self._active_translate_groups = set(selected)
        panel = GroupChoicePanel(group_names, selected, self)
        select_all_button = TransparentToolButton(FIF.CHECKBOX, self)
        select_all_button.clicked.connect(lambda: panel.set_all_groups_selected(not panel.all_groups_selected()))
        tip = CustomTeachingTip.create(
            [panel],
            target=self.groupSelectBtn,
            parent=self,
            closeButtonBelows=(select_all_button,),
            tailPosition=TeachingTipTailPosition.BOTTOM,
        )
        tip._translate_group_panel = panel  # type: ignore[attr-defined]
        self._group_choice_tip = tip
        tip.destroyed.connect(lambda *_args, current=tip: self._clear_group_choice_tip(current))

        def on_selection_changed(names: list[str]):
            self._apply_translate_group_selection(names, fallback_all=False)

        def on_closed():
            # Last flush when tip closes; keep empty selection if user cleared all.
            if qt_object_is_valid(panel):
                self._apply_translate_group_selection(panel.selected_group_names(), fallback_all=False)

        panel.selection_changed.connect(on_selection_changed)
        tip.destroyed.connect(lambda *_args: on_closed())

    def _clear_group_choice_tip(self, tip):
        if self._group_choice_tip is tip:
            self._group_choice_tip = None

    def _clear_translate_editor(self):
        self._active_editor_origin = None
        self.oriTagLabel.setText("-")
        self.translatedTagInput.setText("")

    def _bind_translate_editor(self, origin: str | None):
        canonical = danbooru_cfg.canonicalize_term(origin or "")
        if not canonical:
            self._clear_translate_editor()
            return
        self._active_editor_origin = canonical
        self.oriTagLabel.setText(canonical)
        self.translatedTagInput.setText(self._translate_cache.get(canonical, ""))

    def _save_active_translation(self):
        origin = self._active_editor_origin
        if not origin:
            return InfoBar.warning(
                title="", content="请先选中自定义区中的标签",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
        translated = danbooru_cfg.canonicalize_term(self.translatedTagInput.text())
        if translated:
            self._translate_cache[origin] = translated
            danbooru_cfg.merge_translate_map({origin: translated})
        else:
            self._translate_cache.pop(origin, None)
            danbooru_cfg.drop_translate_keys([origin])
        self._apply_translate_cache_to_tree({origin: self._display_tag(origin)})
        InfoBar.success(
            title="", content="已保存显示名",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=1800, parent=self,
        )

    def _apply_translate_cache_to_tree(self, origins: dict[str, str] | None = None):
        display_map = origins
        for group_index in range(self.custom_tree.topLevelItemCount()):
            group_item = self.custom_tree.topLevelItem(group_index)
            for child_index in range(group_item.childCount()):
                tag_item = group_item.child(child_index)
                meta = self._item_meta(tag_item)
                if meta.get("kind") != "tag":
                    continue
                origin = meta.get("tag", "")
                if not origin:
                    continue
                if display_map is not None and origin not in display_map:
                    continue
                row = self.custom_tree.itemWidget(tag_item, 0)
                if isinstance(row, FavTagRow):
                    text = display_map[origin] if display_map is not None else self._display_tag(origin)
                    row.set_display_text(text)
                    tag_item.setSizeHint(0, QSize(0, row.height()))

    def _snapshot_translate_tags(self) -> list[str]:
        # Never silently expand to all groups: empty selection means empty job.
        selected_groups = set(self._active_translate_groups)
        if not selected_groups:
            return []
        tags: list[str] = []
        seen: set[str] = set()
        for group in self._groups_state.custom_groups:
            if group.name not in selected_groups:
                continue
            for tag in group.tags:
                canonical = danbooru_cfg.canonicalize_term(tag)
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                tags.append(canonical)
        return tags

    def _existing_translated_origins(self) -> set[str]:
        """Origins that already have a non-empty display name (disk map ∪ dialog cache)."""
        # Refresh local cache from disk so re-runs after background merge stay accurate.
        self._translate_cache.update(danbooru_cfg.get_translate_map())
        existing: set[str] = set()
        merged = dict(danbooru_cfg.get_translate_map())
        merged.update(self._translate_cache)
        for raw_origin, raw_translated in merged.items():
            origin = danbooru_cfg.canonicalize_term(str(raw_origin))
            translated = danbooru_cfg.canonicalize_term(str(raw_translated))
            if origin and translated:
                existing.add(origin)
        return existing

    def _pending_translate_tags(self, snapshot_tags: list[str]) -> tuple[list[str], int]:
        """
        Freeze snapshot first, then set-difference away already-translated origins.
        Returns (pending_ordered, skipped_already_count).
        """
        snapshot_ordered: list[str] = []
        seen: set[str] = set()
        for raw_tag in snapshot_tags:
            canonical = danbooru_cfg.canonicalize_term(raw_tag)
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            snapshot_ordered.append(canonical)
        snapshot_set = set(snapshot_ordered)
        already_translated = self._existing_translated_origins()
        pending_set = snapshot_set - already_translated
        pending_ordered = [tag for tag in snapshot_ordered if tag in pending_set]
        skipped_already = len(snapshot_ordered) - len(pending_ordered)
        return pending_ordered, skipped_already

    def _run_translate(self):
        if self._translate_running:
            return InfoBar.warning(
                title="", content="翻译任务进行中",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
        if not is_ai_provider_configured():
            return InfoBar.error(
                title="", content="请先在设置中配置 AI Provider",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3500, parent=self,
            )
        # Apply tip toggles before snapshot even if user never closed the panel.
        self._sync_translate_groups_from_open_tip()
        selected_groups = sorted(self._active_translate_groups)
        snapshot_tags = self._snapshot_translate_tags()
        if not selected_groups:
            return InfoBar.warning(
                title="", content="请先用组选择按钮勾选至少一个收藏组",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self,
            )
        if not snapshot_tags:
            return InfoBar.warning(
                title="", content=f"所选组无标签: {', '.join(selected_groups)}",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self,
            )
        # Same-group re-run: freeze snapshot, then exclude origins already in FavoritesTranslateMap.
        tags, skipped_already = self._pending_translate_tags(snapshot_tags)
        if not tags:
            return InfoBar.info(
                title="",
                content=(
                    f"所选组共 {len(snapshot_tags)} 个标签均已有译文，已跳过（跳过 {skipped_already}）"
                ),
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3500, parent=self,
            )
        interface = self.parent()
        begin = getattr(interface, "begin_favorite_tag_translate", None)
        if not callable(begin):
            return InfoBar.error(
                title="", content="当前界面不支持翻译任务",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3500, parent=self,
            )
        engine = self.searchSiteBox.currentData() or "danbooru"
        language = self.languageBox.currentData() or "zh"

        def on_success(result):
            # Persistence already done by DanbooruInterface; only refresh UI if dialog still alive.
            if not qt_object_is_valid(self):
                return
            self._translate_running = False
            self.runTranslateBtn.setEnabled(True)
            translations = getattr(result, "translations", None) or {}
            for origin, translated in translations.items():
                canonical = danbooru_cfg.canonicalize_term(origin)
                display = danbooru_cfg.canonicalize_term(translated)
                if canonical and display:
                    self._translate_cache[canonical] = display
            self._translate_cache.update(danbooru_cfg.get_translate_map())
            self._apply_translate_cache_to_tree()
            if self._active_editor_origin:
                self._bind_translate_editor(self._active_editor_origin)

        def on_error(message: str):
            # Error toast is shown on DanbooruInterface; keep dialog controls usable if still open.
            _ = message
            if not qt_object_is_valid(self):
                return
            self._translate_running = False
            self.runTranslateBtn.setEnabled(True)

        self._translate_running = True
        self.runTranslateBtn.setEnabled(False)
        total_tags = len(tags)
        try:
            started = begin(
                tags,
                engine=str(engine),
                language=str(language),
                success_callback=on_success,
                error_callback=on_error,
            )
        except Exception as exc:
            self._translate_running = False
            self.runTranslateBtn.setEnabled(True)
            return InfoBar.error(
                title="", content=f"翻译启动失败: {exc}",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self,
            )
        if not started:
            self._translate_running = False
            self.runTranslateBtn.setEnabled(True)
            return InfoBar.warning(
                title="", content="翻译任务未能启动（可能已在运行）",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
        group_preview = ", ".join(selected_groups)
        if len(group_preview) > 30:
            group_preview = f"{group_preview} …"
        content = (
            f"已提交翻译任务: {len(selected_groups)} 组（{group_preview}），"
            f"待译 {total_tags}/{len(snapshot_tags)}"
        )
        if skipped_already:
            content = f"{content}（已跳过已有译文 {skipped_already}）"
        InfoBar.info(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4000,
            parent=self,
        )

    def _apply_groups_change(self, change: t.Callable[[], None]):
        try:
            change()
        except ValueError as exc:
            return InfoBar.error(
                title="", content=str(exc), orient=Qt.Horizontal, isClosable=True, 
                position=InfoBarPosition.TOP, duration=3500, parent=self)
        available = set(self._groups_state.group_names())
        self._active_translate_groups = (self._active_translate_groups & available) or set(available)
        self.refresh_view()

    def refresh_view(self):
        def delete_default_tag(tag: str):
            def change():
                self._groups_state.set_default_tags(
                    current for current in self._groups_state.default_tags if current != tag
                )
                self._drop_translate_cache_keys([tag])

            self._apply_groups_change(change)

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

        def delete_group_tag(group_name: str, tag: str):
            def change():
                group = self._groups_state.group(group_name)
                group.set_tags(current for current in group.tags if current != tag)
                self._drop_translate_cache_keys([tag])
                self._current_group = group.name
                if self._active_editor_origin == danbooru_cfg.canonicalize_term(tag):
                    self._clear_translate_editor()

            self._apply_groups_change(change)

        def delete_group(group_name: str):
            def change():
                removed_tags = []
                remaining_groups = []
                for group in self._groups_state.custom_groups:
                    if group.name == group_name:
                        removed_tags.extend(group.tags)
                        continue
                    remaining_groups.append(group)
                self._groups_state.custom_groups = remaining_groups
                self._groups_state.ensure_custom_group()
                self._drop_translate_cache_keys(removed_tags)
                if self._editing_group == group_name:
                    self._editing_group = None
                if (
                    self._current_group == group_name
                    or self._current_group not in self._groups_state.group_names()
                ):
                    self._current_group = self._groups_state.group_names()[0]

            self._apply_groups_change(change)

        self._groups_state.ensure_custom_group()
        group_names = self._groups_state.group_names()
        if self._current_group not in group_names:
            self._current_group = group_names[0]
        if self._editing_group not in group_names:
            self._editing_group = None

        self._loading = True
        try:
            self.default_table.clearContents()
            self.default_table.setRowCount(0)
            for row, tag in enumerate(self._groups_state.default_tags):
                self.default_table.insertRow(row)
                self.default_table.setItem(row, 0, _readonly_table_item(tag, tag))
                self.default_table.setCellWidget(row, 1,
                    action_button(
                        FIF.DELETE, lambda checked=False, current=tag: delete_default_tag(current), f"删除 {tag}",
                    ),
                )

            self.custom_tree.clear()
            for group in self._groups_state.custom_groups:
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
                    tag_row = FavTagRow(
                        group.name,
                        tag,
                        self.custom_tree,
                        display_text=self._display_tag(tag),
                    )
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
        if self._active_editor_origin and self._active_editor_origin not in self._groups_state.all_terms():
            self._clear_translate_editor()
        elif self._active_editor_origin:
            self._bind_translate_editor(self._active_editor_origin)

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
            self._clear_translate_editor()
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
        if current_kind == "tag":
            self._bind_translate_editor(current_meta.get("tag"))
        else:
            self._clear_translate_editor()
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
        living_tags = self._groups_state.all_terms()
        pruned = {
            origin: translated
            for origin, translated in self._translate_cache.items()
            if origin in living_tags
        }
        self._translate_cache = pruned
        danbooru_cfg.save_translate_map(pruned)
        self.accept()

    @property
    def groups_state(self) -> FavoriteGroupsState:
        return self._groups_state

    @property
    def translate_cache(self) -> dict[str, str]:
        return dict(self._translate_cache)
