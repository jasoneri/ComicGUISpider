import gc
import typing as t

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QCompleter, QFrame, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action, ComboBox, EditableComboBox, FluentIcon as FIF, FlowLayout, PrimaryToolButton, ToolButton, 
    RoundMenu, ScrollArea, SearchLineEdit, TeachingTipTailPosition, TransparentToggleToolButton, TransparentToolButton
)
from qfluentwidgets.components.widgets.line_edit import CompleterMenu

from GUI.uic.qfluent import MonkeyPatch as FluentMonkeyPatch
from GUI.uic.qfluent.components import CustomTeachingTip
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.config.qc import danbooru_cfg
from utils.script.image.danbooru.constants import DANBOORU_SORT_OPTIONS
from utils.script.image.danbooru.models import DanbooruAutocompleteCandidate, DanbooruPost, DanbooruSearchQuery

from .card import DanbooruCardWidget
from .core import DanbooruTabSelectionController, DanbooruTabState, delete_flow_item as _delete_flow_item
from .favorite_groups import build_favorite_groups_state
from .style import DanbooruCardMetrics, DanbooruUiPalette, DEFAULT_CARD_METRICS, build_tab_stylesheet


class DanbooruTabWidget(QFrame):
    selection_count_changed = Signal(int)
    request_search = Signal(str)
    request_conversion = Signal()
    request_single_download = Signal(object)
    request_tag_jump = Signal(str)
    request_next_page = Signal()
    detail_opened = Signal(object)
    request_close = Signal()
    request_extra_search = Signal(str)

    SORT_OPTIONS = list(DANBOORU_SORT_OPTIONS)

    def __init__(self, state: DanbooruTabState, parent=None):
        super().__init__(parent)
        self.gui = parent.gui
        self.state = state
        self.card_metrics = DEFAULT_CARD_METRICS
        self.card_widgets: dict[int, DanbooruCardWidget] = {}
        self._extra_tip = None
        # Completer shows display labels; selection must insert origin search keys.
        self._completer_origin_by_label: dict[str, str] = {}
        self.zoom_mgr = self._InnerZoomMgr(self)
        self._setup_ui()
        self.selection_controller = DanbooruTabSelectionController(self)
        self.selection_controller.selection_count_changed.connect(self.selection_count_changed.emit)
        self.apply_theme()

    class _InnerZoomMgr:
        def __init__(self, tab: "DanbooruTabWidget"):
            self.tab = tab
            self.hidden_target_metrics: t.Optional[DanbooruCardMetrics] = None
            self.hidden_dirty = False
            self.preview_refresh_ids: list[int] = []
            self.preview_refresh_index = 0
            self.preview_refresh_batch_size = 18
            self.preview_refresh_timer = QtCore.QTimer(tab)
            self.preview_refresh_timer.setSingleShot(True)
            self.preview_refresh_timer.timeout.connect(self._drain_preview_refresh_queue)

        def apply_immediate(self, *, metrics: DanbooruCardMetrics, refresh_preview: bool):
            self.cancel_pending()
            self.tab.card_metrics = metrics
            for card in self.tab.card_widgets.values():
                card.apply_metrics(metrics, refresh_preview=refresh_preview)
            self.tab._refresh_grid_layout()

        def apply_active(self, *, metrics: DanbooruCardMetrics, preview_delay_ms: int = 36):
            self.hidden_target_metrics = None
            self.hidden_dirty = False
            self.apply_immediate(metrics=metrics, refresh_preview=False)
            self.request_preview_refresh(refresh_visible_first=True, delay_ms=preview_delay_ms)

        def mark_hidden_target(self, *, metrics: DanbooruCardMetrics):
            self.cancel_pending()
            self.tab.card_metrics = metrics
            self.hidden_target_metrics = metrics
            self.hidden_dirty = True

        def suspend_hidden(self):
            self.cancel_pending()

        def sync_to(self, *, metrics: DanbooruCardMetrics):
            target_metrics = self.hidden_target_metrics if self.hidden_target_metrics is not None else metrics
            if self.tab.card_metrics != target_metrics or self.hidden_dirty:
                self.apply_immediate(metrics=target_metrics, refresh_preview=True)
                self.hidden_target_metrics = None
                self.hidden_dirty = False
                return
            self.hidden_target_metrics = None
            self.hidden_dirty = False
            self.request_preview_refresh(refresh_visible_first=True, delay_ms=0)

        def request_preview_refresh(self, *, refresh_visible_first: bool, delay_ms: int = 0):
            self.preview_refresh_ids = self._build_preview_refresh_order(refresh_visible_first=refresh_visible_first)
            self.preview_refresh_index = 0
            self.preview_refresh_batch_size = 12 if refresh_visible_first else 18
            self.preview_refresh_timer.stop()
            if not self.preview_refresh_ids:
                return
            self.preview_refresh_timer.start(max(0, int(delay_ms)))

        def cancel_pending(self):
            self.preview_refresh_timer.stop()
            self.preview_refresh_ids = []
            self.preview_refresh_index = 0

        def _build_preview_refresh_order(self, *, refresh_visible_first: bool) -> list[int]:
            ordered_ids = list(self.tab.card_widgets.keys())
            if not refresh_visible_first or not ordered_ids:
                return ordered_ids
            visible_ids = self._visible_card_post_ids()
            if not visible_ids:
                return ordered_ids
            return [post_id for post_id in ordered_ids if post_id in visible_ids] + [
                post_id for post_id in ordered_ids if post_id not in visible_ids
            ]

        def _visible_card_post_ids(self) -> set[int]:
            viewport = self.tab.scroll_area.viewport()
            viewport_rect = viewport.rect()
            visible_ids: set[int] = set()
            for post_id, card in self.tab.card_widgets.items():
                card_rect = QtCore.QRect(card.mapTo(viewport, QtCore.QPoint(0, 0)), card.size())
                if viewport_rect.intersects(card_rect):
                    visible_ids.add(post_id)
            return visible_ids

        def _drain_preview_refresh_queue(self):
            if self.preview_refresh_index >= len(self.preview_refresh_ids):
                return
            end = min(len(self.preview_refresh_ids), self.preview_refresh_index + self.preview_refresh_batch_size)
            for post_id in self.preview_refresh_ids[self.preview_refresh_index:end]:
                card = self.tab.card_widgets.get(post_id)
                if card is not None:
                    card.refresh_preview_icon()
            self.preview_refresh_index = end
            if self.preview_refresh_index < len(self.preview_refresh_ids):
                self.preview_refresh_timer.start(16)

    def _create_group_frame(self, object_name: str) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName(object_name)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        return frame, layout

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(12)

        query_frame, query_group = self._create_group_frame("DanbooruSearchQueryGroup")
        self.query_frame = query_frame
        self.query_group = query_group
        self.extraSearchBtn = TransparentToolButton(FIF.ADD, self)
        self.extraSearchBtn.setVisible(False)
        self.extraSearchBtn.clicked.connect(self._on_extra_search_clicked)
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("such as: blue_archive")
        self.search_edit.setMinimumHeight(38)
        self.search_edit.returnPressed.connect(self._submit_search_from_keyboard)
        self.search_edit.searchSignal.connect(lambda text: self.request_search.emit(text))
        self.search_edit.searchButton.clicked.connect(self._submit_empty_search_if_needed)
        self.search_edit.textChanged.connect(self._sync_extra_search_btn_visibility)
        self.search_edit.textChanged.connect(self.sync_favorite_button_state)
        self.set_search_menu()
        self.favorite_btn = TransparentToggleToolButton(FIF.HEART, self)
        self.favorite_btn.setFixedSize(38, 38)
        self.favorite_btn.setDisabled(True)
        self.convert_btn = ToolButton(CgsIcon.SCRIPT_TRANSLATE, self)
        self.convert_btn.setIconSize(QtCore.QSize(24,24))
        self.convert_btn.setMinimumHeight(38)
        self.convert_btn.clicked.connect(self.request_conversion.emit)
        self.sort_box = ComboBox(self)
        self.sort_box.setMinimumHeight(38)
        for label, _ in self.SORT_OPTIONS:
            self.sort_box.addItem(label)
        self.sort_box.currentIndexChanged.connect(self._on_sort_changed)
        query_group.addWidget(self.extraSearchBtn)
        query_group.addWidget(self.search_edit)
        query_group.addWidget(self.favorite_btn)
        query_group.addWidget(self.convert_btn)
        query_group.addWidget(self.sort_box)
        query_frame.setMinimumHeight(58)
        query_frame.setMinimumWidth(420)
        search_row.addWidget(query_frame, 1)

        self.main_layout.addLayout(search_row)

        self.scroll_area = ScrollArea(self)
        self.scroll_area.setObjectName("DanbooruGridScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setToolTip("左键拖拽框选，右键可清空选择")
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("DanbooruGridContent")
        self.flow_layout = FlowLayout(self.scroll_content)
        self.flow_layout.setContentsMargins(2, 2, 2, 2)
        self.flow_layout.setSpacing(4)
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.main_layout.addWidget(self.scroll_area, 1)
        self.refresh_from_state()

    def _sync_extra_search_btn_visibility(self):
        self.extraSearchBtn.setVisible(bool(self.search_edit.text().strip()))

    def sync_favorite_button_state(self):
        term = DanbooruSearchQuery.normalize(self.search_edit.text())
        self.favorite_btn.blockSignals(True)
        self.favorite_btn.setEnabled(bool(term))
        self.favorite_btn.setChecked(bool(term) and self._favorite_groups_state().contains(term))
        self.favorite_btn.blockSignals(False)

    def _favorite_groups_state(self):
        return build_favorite_groups_state(
            danbooru_cfg.searchFavorites.value,
            canonicalize_term=danbooru_cfg.canonicalize_term,
        )

    def _set_search_edit_value(self, value: str):
        self.search_edit.setText(value)
        self.search_edit.setFocus()
        self.search_edit.setCursorPosition(len(value))
        self.sync_favorite_button_state()

    def _submit_search_from_keyboard(self):
        if self.search_edit.text().strip():
            self.search_edit.search()
            return
        self.request_search.emit("")

    def _submit_empty_search_if_needed(self):
        if not self.search_edit.text().strip():
            self.request_search.emit("")

    def set_search_menu(self):
        def _create_search_value_action(text: str, icon, values_getter) -> Action:
            def open_():
                values = [current for value in values_getter() or [] if (current := str(value).strip())]
                self.update_completer(values)
                self._show_search_edit_completer("")
            return Action(icon, text=text, triggered=open_)
        def _create_fav_sub_menu():
            def _show_group_completer(terms: list[str]):
                # Labels may be translated; selecting still inserts origin tags into the search box.
                self.update_completer(terms)
                self._show_search_edit_completer("")
            submenu = RoundMenu("收藏组", self)
            submenu.setIcon(FIF.HEART)
            groups = self._favorite_groups_state().visible_groups()
            if not groups:
                empty_action = Action(text="暂无收藏")
                empty_action.setEnabled(False)
                submenu.addAction(empty_action)
                return submenu

            submenu.addActions([
                Action(
                    text=group.display,
                    triggered=lambda _=False, current=list(group.tags): _show_group_completer(current),
                )
                for group in groups
            ])
            return submenu
        FluentMonkeyPatch.rbutton_menu_lineEdit(
            self.search_edit,
            extra_actions=[_create_search_value_action("打开历史", FIF.HISTORY, danbooru_cfg.get_history)],
            sub_menu=[_create_fav_sub_menu()]
        )

    def show_conversion_candidates(
        self, candidates: list[DanbooruAutocompleteCandidate],
        on_selected: t.Callable[[DanbooruAutocompleteCandidate], None],
    ):
        menu = RoundMenu(parent=self.search_edit)
        if not candidates:
            empty_action = Action(text="empty")
            empty_action.setEnabled(False)
            menu.addAction(empty_action)
        else:
            for candidate in candidates:
                menu.addAction(
                    Action(text=candidate.menu_text,
                        triggered=lambda _=False, current=candidate: on_selected(current),))
        menu.exec(self.search_edit.mapToGlobal(self.search_edit.rect().bottomLeft()))

    def apply_theme(self):
        palette = DanbooruUiPalette.current()
        self.setStyleSheet(build_tab_stylesheet(palette))
        self.selection_controller.apply_theme(
            selection_border=palette.selection_border,
            selection_background=palette.preview_hover,
        )
        for card in self.card_widgets.values():
            card.apply_theme()

    def refresh_from_state(self):
        self.search_edit.setText(self.state.query)
        for idx, (_, value) in enumerate(self.SORT_OPTIONS):
            if value == self.state.sort_mode:
                self.sort_box.blockSignals(True)
                self.sort_box.setCurrentIndex(idx)
                self.sort_box.blockSignals(False)
                break
        self.sync_favorite_button_state()

    def _on_sort_changed(self):
        _, value = self.SORT_OPTIONS[self.sort_box.currentIndex()]
        self.state.sort_mode = value
        self.request_search.emit(self.search_edit.text())

    def apply_first_extra_search(self) -> bool:
        for extra_search_value in danbooru_cfg.get_search_extra():
            if self._apply_extra_search_value(extra_search_value):
                return True
        return False

    def apply_score_sort_search(self) -> bool:
        score_sort_index = next((index for index, (_, value) in enumerate(self.SORT_OPTIONS) if value == "score"), None)
        if score_sort_index is None:
            return False
        if self.sort_box.currentIndex() == score_sort_index:
            self._on_sort_changed()
            return True
        self.sort_box.setCurrentIndex(score_sort_index)
        return True

    def _apply_extra_search_value(self, value: str) -> bool:
        extra_search_value = str(value or "").strip()
        if not extra_search_value:
            return False
        danbooru_cfg.add_search_extra(extra_search_value)
        self.request_extra_search.emit(extra_search_value)
        return True

    def _on_extra_search_clicked(self):
        if self._extra_tip is not None:
            self._extra_tip.close()
        extraCombo = EditableComboBox(self)
        extraCombo.setMinimumWidth(120)
        extraCombo.setPlaceholderText("e.g. score:>50")
        extraCombo.addItems(danbooru_cfg.get_search_extra())
        helpBtn = TransparentToolButton(FIF.HELP, self)
        helpBtn.clicked.connect(lambda: self.gui.open_url_by_browser(
            "https://www.yuque.com/baimusheng/programer/wl9c6nxxdvecm1tg"))
        svBtn = PrimaryToolButton(FIF.ACCEPT_MEDIUM, self)
        tip = CustomTeachingTip.create(
            [extraCombo, svBtn, helpBtn],
            target=self.extraSearchBtn, parent=self,
            tailPosition=TeachingTipTailPosition.BOTTOM_LEFT,
        )
        self._extra_tip = tip
        tip.destroyed.connect(lambda *_args: setattr(self, '_extra_tip', None))
        def _apply():
            self._apply_extra_search_value(extraCombo.currentText())
            tip.close()
        svBtn.clicked.connect(_apply)

    def _on_scroll_changed(self, value: int):
        bar = self.scroll_area.verticalScrollBar()
        if bar.maximum() - value < 200 and not self.state.loading and self.state.has_more_results:
            self.request_next_page.emit()

    @staticmethod
    def _normalize_completer_label(text: str) -> str:
        return " ".join(str(text or "").split())

    @classmethod
    def _completer_label_for_origin(cls, origin: str) -> str:
        canonical = danbooru_cfg.canonicalize_term(origin)
        if not canonical:
            return ""
        display = danbooru_cfg.display_tag(canonical)
        if display and display != canonical:
            # Localized name first; origin kept so MatchContains still finds latin tags.
            return cls._normalize_completer_label(f"{display} · {canonical}")
        return canonical

    def resolve_completer_origin(self, label_or_origin: str) -> str:
        text = self._normalize_completer_label(label_or_origin)
        if not text:
            return ""
        mapped = self._completer_origin_by_label.get(text)
        if mapped:
            return mapped
        # CompleterMenu / whitespace variants may differ slightly; match by suffix origin.
        for label, origin in self._completer_origin_by_label.items():
            if text == label or text.endswith(f"· {origin}") or text.endswith(origin):
                if origin in text or text == label:
                    return origin
        # Bare origin typed/selected.
        canonical = danbooru_cfg.canonicalize_term(text)
        if canonical in set(self._completer_origin_by_label.values()):
            return canonical
        if " · " in text:
            tail = danbooru_cfg.canonicalize_term(text.rsplit(" · ", 1)[-1])
            if tail:
                return tail
        return canonical

    def _on_completer_label_activated(self, label: str):
        origin = self.resolve_completer_origin(label)
        if not origin:
            return
        if self.search_edit.text() != origin:
            self.search_edit.setText(origin)
        self.search_edit.setCursorPosition(len(origin))
        self.sync_favorite_button_state()

    def update_completer(self, terms: list[str]):
        """Build completer from origin tags; popup shows display names, selection writes origin."""
        ordered_origins: list[str] = []
        seen: set[str] = set()
        for raw in terms:
            origin = danbooru_cfg.canonicalize_term(str(raw or ""))
            if not origin or origin in seen:
                continue
            seen.add(origin)
            ordered_origins.append(origin)

        model = QStandardItemModel(self.search_edit)
        label_to_origin: dict[str, str] = {}
        for origin in ordered_origins:
            label = self._completer_label_for_origin(origin)
            if not label:
                continue
            # Disambiguate rare identical display labels.
            if label in label_to_origin and label_to_origin[label] != origin:
                label = self._normalize_completer_label(f"{label} · {origin}")
            item = QStandardItem(label)
            item.setData(origin, Qt.UserRole)
            model.appendRow(item)
            label_to_origin[label] = origin

        self._completer_origin_by_label = label_to_origin
        completer = QCompleter(model, self.search_edit)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionRole(Qt.DisplayRole)
        completer.setCompletionColumn(0)
        # Fallback path when Qt native activated is used instead of CompleterMenu.
        completer.activated[str].connect(self._on_completer_label_activated)
        self.search_edit.setCompleter(completer)

        menu = getattr(self.search_edit, "_completerMenu", None)
        if menu is None:
            menu = CompleterMenu(self.search_edit)
            self.search_edit.setCompleterMenu(menu)
        # CompleterMenu inserts label text; rewrite to origin search key immediately after.
        if getattr(menu, "_cgs_origin_activated_bound", None) is not self:
            menu.activated.connect(self._on_completer_label_activated)
            menu._cgs_origin_activated_bound = self  # type: ignore[attr-defined]
        return completer

    def completer_labels(self) -> list[str]:
        return list(self._completer_origin_by_label.keys())

    def completer_origin_map(self) -> dict[str, str]:
        return dict(self._completer_origin_by_label)

    def _show_search_edit_completer(self, prefix: str):
        completer = self.search_edit.completer()
        if completer is None:
            return
        completer.setCompletionPrefix(prefix)
        menu = getattr(self.search_edit, "_completerMenu", None)
        if menu is None:
            self.search_edit.setCompleterMenu(CompleterMenu(self.search_edit))
            menu = self.search_edit._completerMenu
            if getattr(menu, "_cgs_origin_activated_bound", None) is not self:
                menu.activated.connect(self._on_completer_label_activated)
                menu._cgs_origin_activated_bound = self  # type: ignore[attr-defined]
        changed = menu.setCompletion(completer.completionModel(), completer.completionColumn())
        menu.setMaxVisibleItems(max(completer.maxVisibleItems(),10))
        if changed:
            self.search_edit.setFocus()
            menu.popup()

    def set_loading(self, loading: bool):
        self.state.loading = loading
        self.search_edit.searchButton.setDisabled(loading)
        self.convert_btn.setDisabled(loading)
        self.sort_box.setDisabled(loading)
        self.extraSearchBtn.setDisabled(loading)

    def clear_images_before_current_page(self):
        if not self.state.has_pages_before_current():
            return
        current_page = self.state.page_cursor
        trim_count = self.state.trim_count_before_current_page()
        if trim_count > len(self.state.result_list) or trim_count > self.flow_layout.count():
            raise RuntimeError(
                f"Danbooru grid trim out of range: page={current_page}, start={self.state.buffer_start_page}, trim={trim_count}, "
                f"results={len(self.state.result_list)}, layout={self.flow_layout.count()}"
            )
        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.minimum())
        self.selection_controller.clear()
        del self.state.result_list[:trim_count]
        for _ in range(trim_count):
            item = self.flow_layout.takeAt(0)
            widget = item if isinstance(item, QWidget) else item.widget() if item is not None else None
            if isinstance(widget, DanbooruCardWidget):
                widget.set_pagination_bar(False)
                self.card_widgets.pop(widget.post.post_id, None)
            _delete_flow_item(item)
        self.state.retain_current_page_as_buffer_start()
        self._refresh_grid_layout()
        scroll_bar.setValue(scroll_bar.minimum())
        gc.collect()

    def show_grid_context_menu(self, global_pos: QtCore.QPoint):
        menu = RoundMenu(parent=self.scroll_area)
        clear_previous_pages_action = Action(
            FIF.BROOM,
            text="清除此页前图片",
            triggered=self.clear_images_before_current_page,
        )
        clear_previous_pages_action.setEnabled(self.state.has_pages_before_current())
        selection_count = self.selection_controller.selection_count()
        clear_action = Action(FIF.CANCEL,text="清空选择",triggered=self.selection_controller.clear)
        clear_action.setEnabled(selection_count > 0)
        menu.addAction(clear_previous_pages_action)
        menu.addAction(clear_action)
        menu.exec(global_pos)

    def clear_results(self, *, query: t.Optional[str] = None, keep_count: bool = False):
        self.zoom_mgr.cancel_pending()
        self.selection_controller.clear()
        self.state.reset_results(query=query, keep_count=keep_count)
        if query is not None:
            self.search_edit.setText(self.state.query)
        while self.flow_layout.count():
            _delete_flow_item(self.flow_layout.takeAt(0))
        for card in self.card_widgets.values():
            card.set_pagination_bar(False)
        self.card_widgets.clear()
        self._refresh_grid_layout()

    def append_results(self, posts: list[DanbooruPost], downloaded_md5s: set[str]) -> list[DanbooruCardWidget]:
        appended_cards: list[DanbooruCardWidget] = []
        for idx, post in enumerate(posts):
            card = DanbooruCardWidget(
                post,
                already_downloaded=post.md5 in downloaded_md5s,
                parent=self.scroll_content,
                metrics=self.card_metrics,
            )
            card.open_detail_requested.connect(self.detail_opened.emit)
            self.selection_controller.bind_card(card)
            self.flow_layout.addWidget(card)
            self.card_widgets[post.post_id] = card
            card.set_pagination_bar(idx == 0)
            appended_cards.append(card)
        self.state.result_list.extend(posts)
        self.selection_controller.sync_selection_count()
        self._refresh_grid_layout()
        return appended_cards

    def apply_downloaded_state(self, md5_value: str):
        self.selection_controller.mark_downloaded(md5_value)

    def card_for_post(self, post_id: int) -> t.Optional[DanbooruCardWidget]:
        return self.card_widgets.get(post_id)

    def visible_card_post_ids(self) -> set[int]:
        viewport = self.scroll_area.viewport()
        viewport_rect = viewport.rect()
        visible_ids: set[int] = set()
        for post_id, card in self.card_widgets.items():
            card_rect = QtCore.QRect(card.mapTo(viewport, QtCore.QPoint(0, 0)), card.size())
            if viewport_rect.intersects(card_rect):
                visible_ids.add(post_id)
        return visible_ids

    def _refresh_grid_layout(self):
        viewport_size = self.scroll_area.viewport().size()
        content_width = max(1, viewport_size.width(), self.scroll_content.width())
        target_height = max(1, self.flow_layout.heightForWidth(content_width))
        self.scroll_content.resize(content_width, max(viewport_size.height(), target_height))
        self.flow_layout.invalidate()
        self.flow_layout.setGeometry(QtCore.QRect(0, 0, content_width, target_height))
        self.scroll_content.updateGeometry()
        self.scroll_area.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_grid_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_grid_layout()
