import typing as t

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCompleter, QFrame, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import Action, ComboBox, FluentIcon as FIF, FlowLayout, PushButton, RoundMenu, ScrollArea, SearchLineEdit, TransparentToolButton

from GUI.uic.qfluent import MonkeyPatch as FluentMonkeyPatch
from utils.config.qc import danbooru_cfg
from utils.script.image.danbooru.constants import DANBOORU_SORT_OPTIONS
from utils.script.image.danbooru.models import DanbooruAutocompleteCandidate, DanbooruPost

from .card import DanbooruCardWidget
from .core import DanbooruTabSelectionController, DanbooruTabState, delete_flow_item as _delete_flow_item
from .style import DanbooruCardMetrics, DanbooruUiPalette, DEFAULT_CARD_METRICS, build_tab_stylesheet


class DanbooruTabWidget(QFrame):
    selection_count_changed = Signal(int)
    request_search = Signal(str)
    request_conversion = Signal()
    request_single_download = Signal(object)
    request_tag_jump = Signal(str)
    request_next_page = Signal()
    detail_opened = Signal(object)

    SORT_OPTIONS = list(DANBOORU_SORT_OPTIONS)

    def __init__(self, state: DanbooruTabState, parent=None):
        super().__init__(parent)
        self.state = state
        self.card_metrics = DEFAULT_CARD_METRICS
        self.card_widgets: dict[str, DanbooruCardWidget] = {}
        self._setup_ui()
        self.selection_controller = DanbooruTabSelectionController(self)
        self.selection_controller.selection_count_changed.connect(self.selection_count_changed.emit)
        self.apply_theme()

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
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("such as: blue_archive")
        self.search_edit.setMinimumHeight(38)
        self.search_edit.returnPressed.connect(self._submit_search_from_keyboard)
        self.search_edit.searchSignal.connect(lambda text: self.request_search.emit(text))
        self.search_edit.searchButton.clicked.connect(self._submit_empty_search_if_needed)
        FluentMonkeyPatch.rbutton_menu_lineEdit(
            self.search_edit,
            extra_actions=[
                self._create_search_value_action("打开历史", FIF.HISTORY, danbooru_cfg.get_history, "暂无历史记录"),
                self._create_search_value_action("打开收藏列表", FIF.HEART, lambda: sorted(danbooru_cfg.get_favorites()), "暂无收藏记录"),
            ],
        )
        self.favorite_btn = TransparentToolButton(FIF.HEART, self)
        self.favorite_btn.setFixedSize(38, 38)
        self.convert_btn = PushButton("to Tag", self)
        self.convert_btn.setMinimumHeight(38)
        self.convert_btn.clicked.connect(self.request_conversion.emit)
        self.sort_box = ComboBox(self)
        self.sort_box.setMinimumHeight(38)
        for label, _ in self.SORT_OPTIONS:
            self.sort_box.addItem(label)
        self.sort_box.currentIndexChanged.connect(self._on_sort_changed)
        query_group.addWidget(self.search_edit, 1)
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

    def _set_search_edit_value(self, value: str):
        self.search_edit.setText(value)
        self.search_edit.setFocus()
        self.search_edit.setCursorPosition(len(value))

    def _submit_search_from_keyboard(self):
        if self.search_edit.text().strip():
            self.search_edit.search()
            return
        self.request_search.emit("")

    def _submit_empty_search_if_needed(self):
        if not self.search_edit.text().strip():
            self.request_search.emit("")

    def _create_search_value_action(self, text: str, icon, values_getter, empty_text: str) -> Action:
        def open_menu():
            menu = RoundMenu(parent=self.search_edit)
            values = [current for value in values_getter() or [] if (current := str(value).strip())]
            if not values:
                empty_action = Action(text=empty_text)
                empty_action.setEnabled(False)
                menu.addAction(empty_action)
            else:
                for value in values:
                    menu.addAction(Action(text=value, triggered=lambda _=False, current=value: self._set_search_edit_value(current)))
            menu.exec(self.search_edit.mapToGlobal(self.search_edit.rect().bottomLeft()))

        return Action(icon, text=text, triggered=open_menu)

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

    def _on_sort_changed(self):
        _, value = self.SORT_OPTIONS[self.sort_box.currentIndex()]
        self.state.sort_mode = value
        self.request_search.emit(self.search_edit.text())

    def _on_scroll_changed(self, value: int):
        bar = self.scroll_area.verticalScrollBar()
        if bar.maximum() - value < 200 and not self.state.loading and self.state.has_more_results:
            self.request_next_page.emit()

    def update_completer(self, terms: list[str]):
        completer = QCompleter(terms, self)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.search_edit.setCompleter(completer)

    def set_loading(self, loading: bool):
        self.state.loading = loading
        self.search_edit.searchButton.setDisabled(loading)
        self.convert_btn.setDisabled(loading)
        self.sort_box.setDisabled(loading)

    def show_grid_context_menu(self, global_pos: QtCore.QPoint):
        menu = RoundMenu(parent=self.scroll_area)
        selection_count = self.selection_controller.selection_count()
        clear_action = Action(
            FIF.CANCEL,
            text=f"清空选择 ({selection_count})" if selection_count else "清空选择",
            triggered=self.selection_controller.clear,
        )
        clear_action.setEnabled(selection_count > 0)
        menu.addAction(clear_action)
        menu.exec(global_pos)

    def clear_results(self, *, query: t.Optional[str] = None):
        self.selection_controller.clear()
        self.state.reset_results(query=query)
        if query is not None:
            self.search_edit.setText(self.state.query)
        while self.flow_layout.count():
            _delete_flow_item(self.flow_layout.takeAt(0))
        self.card_widgets.clear()
        self._refresh_grid_layout()

    def append_results(self, posts: list[DanbooruPost], downloaded_md5s: set[str]) -> list[DanbooruCardWidget]:
        appended_cards: list[DanbooruCardWidget] = []
        for post in posts:
            card = DanbooruCardWidget(
                post,
                already_downloaded=post.md5 in downloaded_md5s,
                parent=self.scroll_content,
                metrics=self.card_metrics,
            )
            card.open_detail_requested.connect(self.detail_opened.emit)
            self.selection_controller.bind_card(card)
            self.flow_layout.addWidget(card)
            self.card_widgets[post.md5] = card
            appended_cards.append(card)
        self.state.result_list.extend(posts)
        self.selection_controller.sync_selection_count()
        self.apply_theme()
        self._refresh_grid_layout()
        return appended_cards

    def set_card_metrics(self, metrics: DanbooruCardMetrics):
        self.card_metrics = metrics
        for card in self.card_widgets.values():
            card.apply_metrics(metrics)
        self._refresh_grid_layout()

    def apply_downloaded_state(self, md5_value: str):
        self.selection_controller.mark_downloaded(md5_value)

    def card_for_post(self, post_id: int) -> t.Optional[DanbooruCardWidget]:
        return next((card for card in self.card_widgets.values() if card.post.post_id == post_id), None)

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
