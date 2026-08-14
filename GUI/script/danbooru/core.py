import asyncio
import math
import typing as t
from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QPushButton, QRubberBand, QWidget
from qfluentwidgets import InfoBar

from utils.config.qc import danbooru_cfg
from utils.script.image.danbooru.constants import DANBOORU_BASE_URL, DANBOORU_PAGE_SIZE
from utils.script.image.danbooru.download import DanbooruDownloadSubmitter
from utils.script.image.danbooru.http import DanbooruChallengeRequired
from utils.script.image.danbooru.models import DanbooruAutocompleteCandidate, DanbooruPost, DanbooruSearchQuery

if t.TYPE_CHECKING:
    from utils.script.image.danbooru.client import DanbooruClient
    from . import DanbooruCardWidget, DanbooruInterface, DanbooruTabWidget

DANBOORU_CHALLENGE_ERROR_MARKER = "Danbooru request blocked by browser verification"
DANBOORU_SEARCH_ERROR_STATUS = "search failed"


def run_async(coro):
    return asyncio.run(coro)


def execute_danbooru_task(task_mgr, task, *, success_callback, error_callback, task_id: str):
    task_mgr.execute_simple_task(
        task,
        success_callback=success_callback, error_callback=error_callback, show_success_info=False, 
        show_error_info=False, show_tooltip=False, task_id=task_id,
    )


@dataclass(slots=True)
class DanbooruReqResult:
    value: t.Any = None
    challenge: t.Optional[DanbooruChallengeRequired] = None


def capture_danbooru_request(task: t.Callable[..., t.Any], /, *args: t.Any, **kwargs: t.Any) -> DanbooruReqResult:
    try:
        return DanbooruReqResult(value=task(*args, **kwargs))
    except DanbooruChallengeRequired as exc:
        return DanbooruReqResult(challenge=exc)


@dataclass(frozen=True, slots=True)
class DanbooruViewerFitResult:
    available_bounds: QtCore.QSize
    max_display_bounds: QtCore.QSize
    display_size: QtCore.QSize
    target_area: int
    axis_scale: float


class DanbooruViewerFitCalculator:
    @staticmethod
    def _normalize_bounds(bounds: QtCore.QSize) -> QtCore.QSize:
        return QtCore.QSize(max(1, bounds.width()), max(1, bounds.height()))

    @staticmethod
    def _fit_size_within_bounds(source_size: t.Optional[QtCore.QSize], bounds: QtCore.QSize) -> QtCore.QSize:
        normalized_bounds = DanbooruViewerFitCalculator._normalize_bounds(bounds)
        if source_size is None or source_size.width() <= 0 or source_size.height() <= 0:
            return normalized_bounds
        max_width = max(1, min(normalized_bounds.width(), source_size.width()))
        max_height = max(1, min(normalized_bounds.height(), source_size.height()))
        if source_size.width() <= max_width and source_size.height() <= max_height:
            return QtCore.QSize(source_size)
        if max_width * source_size.height() <= max_height * source_size.width():
            fitted_width = max_width
            fitted_height = max(1, int(round(fitted_width * source_size.height() / source_size.width())))
            return QtCore.QSize(fitted_width, fitted_height)
        fitted_height = max_height
        fitted_width = max(1, int(round(fitted_height * source_size.width() / source_size.height())))
        return QtCore.QSize(fitted_width, fitted_height)

    @classmethod
    def calculate(cls, available_bounds: QtCore.QSize, source_size: t.Optional[QtCore.QSize]) -> DanbooruViewerFitResult:
        normalized_available = cls._normalize_bounds(available_bounds)
        area_ratio = danbooru_cfg.get_view_ratio()
        axis_scale = math.sqrt(area_ratio)
        max_display_bounds = QtCore.QSize(
            max(1, min(normalized_available.width(), int(normalized_available.width() * axis_scale))),
            max(1, min(normalized_available.height(), int(normalized_available.height() * axis_scale))),
        )
        display_size = cls._fit_size_within_bounds(source_size, max_display_bounds)
        return DanbooruViewerFitResult(
            available_bounds=normalized_available, max_display_bounds=max_display_bounds, display_size=display_size,
            target_area=max(1, int(round(normalized_available.width() * normalized_available.height() * area_ratio))),
            axis_scale=axis_scale,
        )


def fetch_pixmap(request_client: "DanbooruClient", url: str, max_width: int = 280) -> bytes:
    raw = request_client.fetch_remote_bytes(url, timeout=20.0)
    image = QtGui.QImage()
    image.loadFromData(raw)
    if image.isNull():
        raise ValueError("invalid image data")
    if max_width and image.width() > max_width:
        image = image.scaledToWidth(max_width, Qt.SmoothTransformation)
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def delete_flow_item(item):
    if item is None:
        return
    if isinstance(item, QWidget):
        item.deleteLater()
        return
    widget = item.widget() if hasattr(item, "widget") else None
    if widget is not None:
        widget.deleteLater()


@dataclass(slots=True)
class DanbooruTabState:
    tab_id: str
    title: str
    query: str = ""
    sort_mode: str = ""
    page_cursor: int = 1
    buffer_start_page: int = 1
    result_list: list[DanbooruPost] = field(default_factory=list)
    selected_post_ids: set[int] = field(default_factory=set)
    request_token: int = 0
    has_more_results: bool = True
    loading: bool = False
    has_loaded_once: bool = False
    total_count: t.Optional[int] = None
    count_query_key: str = ""

    def begin_request(self) -> int:
        self.request_token += 1
        return self.request_token

    def reset_results(self, *, query: t.Optional[str] = None, keep_count: bool = False):
        if query is not None:
            self.query = query
        self.page_cursor = 1
        self.buffer_start_page = 1
        self.result_list.clear()
        self.selected_post_ids.clear()
        self.has_more_results = True
        self.has_loaded_once = False
        if not keep_count:
            self.total_count = None
            self.count_query_key = ""

    def mark_loaded_page(self, posts: t.Sequence[DanbooruPost], page: int, *, replace: bool = False):
        if replace or not self.has_loaded_once or not self.result_list:
            self.buffer_start_page = page
        self.page_cursor = page
        self.has_loaded_once = True
        self.has_more_results = len(posts) >= DANBOORU_PAGE_SIZE

    def count_cache_key(self) -> str:
        return f"{self.query}\n{self.sort_mode}"

    def can_load_next_page(self) -> bool:
        return not self.loading and self.has_more_results and self.has_loaded_once

    def has_pages_before_current(self) -> bool:
        return self.page_cursor > self.buffer_start_page

    def trim_count_before_current_page(self) -> int:
        return (self.page_cursor - self.buffer_start_page) * DANBOORU_PAGE_SIZE

    def retain_current_page_as_buffer_start(self):
        self.buffer_start_page = self.page_cursor


@dataclass(frozen=True, slots=True)
class _DanbooruSearchDispatch:
    tab_id: str
    query: str
    order: str
    page: int
    token: int
    replace: bool
    task_prefix: str

    def task_id(self) -> str:
        return f"danbooru-{self.task_prefix}-{self.tab_id}-{self.token}"

    def challenge_retry_key(self) -> str:
        return f"search:{self.tab_id}:{self.page}:{int(self.replace)}"

    def retry_callback(self, controller: "DanbooruSearchController") -> t.Callable[[], None]:
        if self.task_prefix == "jump" or (self.replace and self.page > 1):
            return lambda dispatch=self: controller.jump_to_page(dispatch.tab_id, dispatch.page)
        if self.replace or self.page <= 1:
            return lambda dispatch=self: controller.start_search(dispatch.tab_id, dispatch.query, order=dispatch.order)
        return lambda dispatch=self: controller.load_next_page(dispatch.tab_id)


class DanbooruTabSelectionController(QtCore.QObject):
    selection_count_changed = Signal(int)

    def __init__(self, tab: "DanbooruTabWidget"):
        super().__init__(tab)
        self.tab = tab
        self._selection_band = QRubberBand(QRubberBand.Rectangle, self.tab.scroll_area.viewport())
        self._selection_band.hide()
        self._drag_select_origin: t.Optional[QtCore.QPoint] = None
        self._drag_select_active = False
        self._drag_select_source: t.Optional[QWidget] = None
        self._drag_select_seed: set[int] = set()
        self._install_drag_select_source(self.tab.scroll_area.viewport())
        self._install_drag_select_source(self.tab.scroll_content)

    def apply_theme(self, *, selection_border: str, selection_background: str):
        self._selection_band.setStyleSheet(f"border: 2px dashed {selection_border}; background: {selection_background};")

    def bind_card(self, card: "DanbooruCardWidget"):
        card.selection_changed.connect(self._on_card_selection_changed)
        self._apply_card_selection(card, card.post.post_id in self.tab.state.selected_post_ids, emit_count=False)
        self._install_drag_select_source(card)
        self._install_drag_select_source(card.preview_frame)
        self._install_drag_select_source(card.preview_button)

    def set_card_selected(self, card: "DanbooruCardWidget", selected: bool):
        self._apply_card_selection(card, selected)

    def sync_selection_count(self):
        self.selection_count_changed.emit(len(self.tab.state.selected_post_ids))

    def selection_count(self) -> int:
        return len(self.tab.state.selected_post_ids)

    def has_selection(self) -> bool:
        return bool(self.tab.state.selected_post_ids)

    def clear(self):
        self._reset_drag_select_state()
        self._set_selected_post_ids(set())

    def mark_downloaded(self, md5_value: str):
        downloaded_post_ids = set()
        for card in self.tab.card_widgets.values():
            if card.post.md5 != md5_value:
                continue
            card.set_already_downloaded(True)
            downloaded_post_ids.add(card.post.post_id)
        self.tab.state.selected_post_ids.difference_update(downloaded_post_ids)
        self.sync_selection_count()

    def _apply_card_selection(self, card: "DanbooruCardWidget", selected: bool, *, sync_widget: bool = True, emit_count: bool = True):
        if sync_widget:
            card.set_selected(selected)
            selected = card.checkbox.isChecked()
        if selected:
            self.tab.state.selected_post_ids.add(card.post.post_id)
        else:
            self.tab.state.selected_post_ids.discard(card.post.post_id)
        if emit_count:
            self.sync_selection_count()

    def _on_card_selection_changed(self, card: "DanbooruCardWidget", selected: bool):
        self._apply_card_selection(card, selected, sync_widget=False)

    def _install_drag_select_source(self, widget: QWidget):
        widget.setProperty("danbooruDragSelectSource", True)
        widget.installEventFilter(self)

    def _set_selected_post_ids(self, post_ids: t.Iterable[int], *, emit_count: bool = True):
        target_post_ids = {
            post_id
            for post_id in post_ids
            if (card := self.tab.card_widgets.get(post_id)) is not None and card.checkbox.isEnabled()
        }
        current_post_ids = set(self.tab.state.selected_post_ids)
        if current_post_ids == target_post_ids:
            return
        for post_id in current_post_ids - target_post_ids:
            card = self.tab.card_widgets.get(post_id)
            if card is None:
                self.tab.state.selected_post_ids.discard(post_id)
                continue
            self._apply_card_selection(card, False, emit_count=False)
        for post_id in target_post_ids - current_post_ids:
            card = self.tab.card_widgets.get(post_id)
            if card is not None:
                self._apply_card_selection(card, True, emit_count=False)
        if emit_count:
            self.sync_selection_count()

    def _viewport_point_from_global(self, global_pos: QtCore.QPoint) -> QtCore.QPoint:
        viewport = self.tab.scroll_area.viewport()
        rect = viewport.rect()
        point = viewport.mapFromGlobal(global_pos)
        return QtCore.QPoint(min(max(point.x(), rect.left()), rect.right()), min(max(point.y(), rect.top()), rect.bottom()))

    def _reset_drag_select_state(self):
        was_active = self._drag_select_active
        self._drag_select_origin = None
        self._drag_select_active = False
        self._drag_select_source = None
        self._drag_select_seed.clear()
        self._selection_band.hide()
        if was_active:
            QApplication.restoreOverrideCursor()

    def _begin_drag_select(self):
        if self._drag_select_active or self._drag_select_origin is None:
            return
        self._drag_select_active = True
        self._selection_band.setGeometry(QtCore.QRect(self._drag_select_origin, QtCore.QSize()))
        self._selection_band.show()
        if isinstance(self._drag_select_source, QPushButton):
            self._drag_select_source.setDown(False)
        QApplication.setOverrideCursor(Qt.CrossCursor)

    def _update_drag_select_band(self, global_pos: QtCore.QPoint):
        if self._drag_select_origin is None:
            return
        self._selection_band.setGeometry(
            QtCore.QRect(self._drag_select_origin, self._viewport_point_from_global(global_pos)).normalized()
        )

    def _selected_post_ids_for_rect(self, selection_rect: QtCore.QRect) -> set[int]:
        if selection_rect.width() < 5 and selection_rect.height() < 5:
            return set(self._drag_select_seed)
        viewport = self.tab.scroll_area.viewport()
        hit_post_ids = set(self._drag_select_seed)
        for card in self.tab.card_widgets.values():
            if not card.checkbox.isEnabled():
                continue
            card_rect = QtCore.QRect(card.mapTo(viewport, QtCore.QPoint(0, 0)), card.size())
            if selection_rect.intersects(card_rect):
                hit_post_ids.add(card.post.post_id)
        return hit_post_ids

    def _preview_drag_selection(self, selection_rect: QtCore.QRect):
        self._set_selected_post_ids(self._selected_post_ids_for_rect(selection_rect))

    def eventFilter(self, obj, event):
        if not bool(getattr(obj, "property", lambda *_args: False)("danbooruDragSelectSource")):
            return super().eventFilter(obj, event)
        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            if event.button() != Qt.LeftButton:
                return super().eventFilter(obj, event)
            self._drag_select_origin = self._viewport_point_from_global(event.globalPosition().toPoint())
            self._drag_select_active = False
            self._drag_select_source = obj
            self._drag_select_seed = set(self.tab.state.selected_post_ids)
            return False
        if event_type == QtCore.QEvent.MouseMove:
            if self._drag_select_origin is None:
                return super().eventFilter(obj, event)
            current_point = self._viewport_point_from_global(event.globalPosition().toPoint())
            if not self._drag_select_active:
                if (current_point - self._drag_select_origin).manhattanLength() < QApplication.startDragDistance():
                    return False
                self._begin_drag_select()
            self._update_drag_select_band(event.globalPosition().toPoint())
            self._preview_drag_selection(self._selection_band.geometry())
            return True
        if event_type == QtCore.QEvent.MouseButtonRelease:
            if event.button() == Qt.RightButton:
                self.tab.show_grid_context_menu(event.globalPosition().toPoint())
                return True
            if event.button() == Qt.MiddleButton:
                self.tab.request_close.emit()
                return True
            if self._drag_select_origin is None:
                return super().eventFilter(obj, event)
            selection_rect = self._selection_band.geometry()
            drag_was_active = self._drag_select_active
            target_post_ids = self._selected_post_ids_for_rect(selection_rect) if drag_was_active else set()
            self._reset_drag_select_state()
            if drag_was_active:
                self._set_selected_post_ids(target_post_ids)
                return True
            return False
        return super().eventFilter(obj, event)


class DanbooruSearchController:
    def __init__(self, interface: "DanbooruInterface"):
        self.interface = interface

    def start_search(self, tab_id: str, query: str, *, order: str | None = None):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None:
            return
        canonical_term = DanbooruSearchQuery.normalize(query)
        token = state.begin_request()
        tab.clear_results(query=canonical_term)
        state.total_count = None
        state.count_query_key = ""
        self.interface.detail_preview_controller.cancel_page_continuation(tab_id)
        if order is not None:
            state.sort_mode = str(order or "")
        tab.set_loading(True)
        self.interface.sync_page_nav(tab_id)
        self._submit_search_request(
            tab_id=tab_id, query=state.query, order=state.sort_mode, page=1,
            token=token, replace=True, task_prefix="search",
        )

    def jump_to_page(self, tab_id: str, page: int) -> bool:
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or state.loading:
            return False
        target_page = max(1, int(page or 1))
        if target_page == state.page_cursor and state.has_loaded_once:
            return False
        token = state.begin_request()
        keep_count = state.count_query_key == state.count_cache_key() and state.total_count is not None
        tab.clear_results(query=state.query, keep_count=keep_count)
        if not keep_count:
            state.total_count = None
            state.count_query_key = ""
        state.page_cursor = target_page
        state.buffer_start_page = target_page
        self.interface.detail_preview_controller.cancel_page_continuation(tab_id)
        tab.set_loading(True)
        self.interface.tab_mgr.set_tip(tab_id, f"jump page {target_page}...", cls="theme-tip")
        self.interface.sync_page_nav(tab_id)
        self._submit_search_request(
            tab_id=tab_id, query=state.query, order=state.sort_mode, page=target_page,
            token=token, replace=True, task_prefix="jump",
        )
        return True

    def load_next_page(self, tab_id: str) -> bool:
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or not state.can_load_next_page():
            return False
        token = state.begin_request()
        next_page = state.page_cursor + 1
        tab.set_loading(True)
        self.interface.tab_mgr.set_tip(tab_id, f"loading page {next_page}...", cls="theme-tip")
        self.interface.sync_page_nav(tab_id)
        self._submit_search_request(
            tab_id=tab_id, query=state.query, order=state.sort_mode, page=next_page,
            token=token, replace=False, task_prefix="page",
        )
        return True

    def _submit_search_request(
        self,
        *,
        tab_id: str,
        query: str,
        order: str,
        page: int,
        token: int,
        replace: bool,
        task_prefix: str,
    ) -> None:
        dispatch = _DanbooruSearchDispatch(
            tab_id=tab_id, query=query, order=order, page=page,
            token=token, replace=replace, task_prefix=task_prefix,
        )
        self.interface._log_search_request(dispatch.tab_id, dispatch.query, dispatch.order, dispatch.page, DANBOORU_PAGE_SIZE)
        execute_danbooru_task(
            self.interface.task_mgr,
            lambda current=dispatch, interface=self.interface: capture_danbooru_request(
                interface.request_client.search_posts, current.query, order=current.order, page=current.page
            ),
            success_callback=lambda result, current=dispatch: self.handle_search_result(current, result),
            error_callback=lambda err, current=dispatch: self.handle_search_error(current, err), task_id=dispatch.task_id(),
        )

    def handle_search_result(self, dispatch: _DanbooruSearchDispatch, result: DanbooruReqResult):
        if result.challenge is not None:
            self.interface.detail_preview_controller.handle_page_load_failed(dispatch.tab_id, "Need browser verification")
            self.handle_search_challenge(dispatch, result.challenge)
            return
        self.handle_search_success(dispatch, result.value or [])

    def handle_search_success(self, dispatch: _DanbooruSearchDispatch, posts: list[DanbooruPost]):
        tab = self.interface.tabs.get(dispatch.tab_id)
        state = self.interface.tab_states.get(dispatch.tab_id)
        if tab is None or state is None or dispatch.token != state.request_token:
            return
        state.mark_loaded_page(posts, dispatch.page, replace=dispatch.replace)
        self.interface.tab_mgr.update_title(dispatch.tab_id, state.query)
        self.interface.tab_mgr.set_httpx_status(dispatch.tab_id, f"httpx 200/{len(posts)}", cls="theme-success")
        if dispatch.replace:
            self._schedule_count_fetch(dispatch)
        if not posts and dispatch.replace:
            tab.set_loading(False)
            self.interface.tab_mgr.set_httpx_status(dispatch.tab_id, "httpx 200/0", cls="theme-tip")
            self.interface.sync_page_nav(dispatch.tab_id)
            return
        if not posts:
            tab.set_loading(False)
            self.interface.detail_preview_controller.handle_page_load_empty(dispatch.tab_id)
            self.interface.tab_mgr.set_tip(dispatch.tab_id, "empty", cls="theme-err")
            self.interface.sync_page_nav(dispatch.tab_id)
            return
        self.interface.tab_mgr.set_tip(dispatch.tab_id, f"rendering {len(posts)} posts...", cls="theme-tip")
        QtCore.QTimer.singleShot(0, lambda current=dispatch, payload=list(posts): self._append_search_success(current, payload))

    def _append_search_success(self, dispatch: _DanbooruSearchDispatch, posts: list[DanbooruPost]):
        tab = self.interface.tabs.get(dispatch.tab_id)
        state = self.interface.tab_states.get(dispatch.tab_id)
        if tab is None or state is None or dispatch.token != state.request_token:
            return
        downloaded_md5s = self.interface.sql_recorder.batch_check_dupe([post.md5 for post in posts if post.md5])
        appended_cards = tab.append_results(posts, downloaded_md5s)
        tab.set_loading(False)
        danbooru_cfg.add_history(state.query)
        self.interface._refresh_completer(tab)
        self.interface.detail_preview_controller.handle_page_appended(dispatch.tab_id, posts)
        self.queue_card_previews(tab, appended_cards)
        if not state.has_more_results:
            self.interface.tab_mgr.set_tip(dispatch.tab_id, "empty", cls="theme-err")
        else:
            self.interface.tab_mgr.set_httpx_status(dispatch.tab_id, f"httpx 200/{len(posts)}", cls="theme-success")
        self.interface.sync_page_nav(dispatch.tab_id)

    def _schedule_count_fetch(self, dispatch: _DanbooruSearchDispatch):
        state = self.interface.tab_states.get(dispatch.tab_id)
        if state is None:
            return
        query_key = f"{dispatch.query}\n{dispatch.order}"
        if state.count_query_key == query_key and state.total_count is not None:
            self.interface.sync_page_nav(dispatch.tab_id)
            return
        token = state.request_token
        execute_danbooru_task(
            self.interface.task_mgr,
            lambda current=dispatch, interface=self.interface: capture_danbooru_request(
                interface.request_client.count_posts, current.query, order=current.order
            ),
            success_callback=lambda result, current=dispatch, request_token=token: self.handle_count_result(
                current, request_token, result
            ),
            error_callback=lambda _err, current=dispatch, request_token=token: self.handle_count_error(
                current, request_token
            ),
            task_id=f"danbooru-count-{dispatch.tab_id}-{token}",
        )

    def handle_count_result(self, dispatch: _DanbooruSearchDispatch, request_token: int, result: DanbooruReqResult):
        state = self.interface.tab_states.get(dispatch.tab_id)
        if state is None or request_token != state.request_token:
            return
        if result.challenge is not None:
            return
        try:
            total_count = int(result.value)
        except (TypeError, ValueError):
            return
        state.total_count = max(0, total_count)
        state.count_query_key = f"{dispatch.query}\n{dispatch.order}"
        self.interface.sync_page_nav(dispatch.tab_id)

    def handle_count_error(self, dispatch: _DanbooruSearchDispatch, request_token: int):
        state = self.interface.tab_states.get(dispatch.tab_id)
        if state is None or request_token != state.request_token:
            return
        self.interface.sync_page_nav(dispatch.tab_id)

    def handle_search_challenge(self, dispatch: _DanbooruSearchDispatch, challenge: DanbooruChallengeRequired):
        tab = self.interface.tabs.get(dispatch.tab_id)
        state = self.interface.tab_states.get(dispatch.tab_id)
        if tab is None or state is None or dispatch.token != state.request_token:
            return
        tab.set_loading(False)
        self.interface.sync_page_nav(dispatch.tab_id)
        self.interface.challenge_controller.submit(
            dispatch.tab_id, challenge, dispatch.retry_callback(self), retry_key=dispatch.challenge_retry_key(),
        )

    def handle_search_error(self, dispatch: _DanbooruSearchDispatch, error: str):
        tab = self.interface.tabs.get(dispatch.tab_id)
        state = self.interface.tab_states.get(dispatch.tab_id)
        if tab is None or state is None or dispatch.token != state.request_token:
            return
        tab.set_loading(False)
        self.interface.sync_page_nav(dispatch.tab_id)
        if DANBOORU_CHALLENGE_ERROR_MARKER in str(error or ""):
            self.interface.detail_preview_controller.handle_page_load_failed(dispatch.tab_id, "Need browser verification")
            self.handle_search_challenge(dispatch, DanbooruChallengeRequired(verify_url=DANBOORU_BASE_URL, status_code=403))
            return
        self.interface.tab_mgr.set_tip(dispatch.tab_id, DANBOORU_SEARCH_ERROR_STATUS, cls="theme-err")
        self.interface.detail_preview_controller.handle_page_load_failed(dispatch.tab_id, DANBOORU_SEARCH_ERROR_STATUS)
        self.interface._show_task_error(error, 6000)

    def load_card_preview(self, tab: "DanbooruTabWidget", card: "DanbooruCardWidget"):
        if card.post.preview_asset_is_video:
            card.preview_button.setText("Video Preview")
            return
        preview_url = card.post.preview_file_url or card.post.file_url
        if not preview_url:
            return
        tab_id, post_id = tab.state.tab_id, card.post.post_id
        execute_danbooru_task(
            self.interface.task_mgr,
            lambda url=preview_url, width=max(card.preview_fetch_width(), 280), interface=self.interface: capture_danbooru_request(
                fetch_pixmap, interface.request_client, url, max_width=width
            ),
            success_callback=lambda payload, tid=tab_id, pid=post_id: self.handle_card_preview_result(tid, pid, payload),
            error_callback=lambda _err, tid=tab_id, pid=post_id: self.handle_card_preview_error(tid, pid),
            task_id=f"danbooru-card-preview-{tab_id}-{post_id}",
        )

    def queue_card_previews(self, tab: "DanbooruTabWidget", cards: list["DanbooruCardWidget"]):
        visible_ids = tab.visible_card_post_ids()
        ordered_post_ids = [card.post.post_id for card in cards if card.post.post_id in visible_ids] + [
            card.post.post_id for card in cards if card.post.post_id not in visible_ids
        ]
        self._queue_card_preview_batch(tab.state.tab_id, ordered_post_ids, 0)

    def _queue_card_preview_batch(self, tab_id: str, post_ids: list[int], index: int):
        tab = self.interface.tabs.get(tab_id)
        if tab is None or index >= len(post_ids):
            return
        end = min(len(post_ids), index + 6)
        for post_id in post_ids[index:end]:
            card = tab.card_for_post(post_id)
            if card is not None:
                self.load_card_preview(tab, card)
        if end < len(post_ids):
            QtCore.QTimer.singleShot(16, lambda tid=tab_id, ids=post_ids, i=end: self._queue_card_preview_batch(tid, ids, i))

    def handle_card_preview_result(self, tab_id: str, post_id: int, payload: DanbooruReqResult):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        card = tab.card_for_post(post_id)
        if card is None:
            return
        if payload.challenge is not None:
            card.preview_button.setText("需要验证")
            self.interface.challenge_controller.submit(
                tab_id, payload.challenge, lambda tid=tab_id, pid=post_id: self.retry_card_preview(tid, pid),
                retry_key=f"card-preview:{tab_id}:{post_id}",
            )
            return
        self.apply_card_preview(card, payload.value)

    def handle_card_preview_error(self, tab_id: str, post_id: int):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        card = tab.card_for_post(post_id)
        if card is None:
            return
        card.preview_button.setText("Preview Error")

    def retry_card_preview(self, tab_id: str, post_id: int):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        card = tab.card_for_post(post_id)
        if card is None:
            return
        self.load_card_preview(tab, card)

    @staticmethod
    def apply_card_preview(card: "DanbooruCardWidget", raw: bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(raw, "PNG")
        if not pixmap.isNull():
            card.set_preview_pixmap(pixmap)

    def convert_term(self, tab_id: str):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        term = DanbooruSearchQuery.normalize(tab.search_edit.text())
        if not term:
            return
        execute_danbooru_task(
            self.interface.task_mgr,
            lambda current_term=term, interface=self.interface: capture_danbooru_request(
                interface.request_client.autocomplete_tags, current_term,
            ),
            success_callback=lambda payload, tid=tab_id: self.handle_conversion_task_result(tid, payload),
            error_callback=lambda err: self.interface._show_task_error(err, 6000), task_id=f"danbooru-convert-{tab_id}",
        )

    def handle_conversion_task_result(self, tab_id: str, payload: DanbooruReqResult):
        if payload.challenge is not None:
            self.handle_conversion_challenge(tab_id, payload.challenge)
            return
        self.handle_conversion_result(tab_id, payload.value)

    def handle_conversion_challenge(self, tab_id: str, challenge: DanbooruChallengeRequired):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        self.interface.challenge_controller.submit(
            tab_id, challenge, lambda tid=tab_id: self.convert_term(tid), retry_key=f"convert:{tab_id}",
        )

    def _search_converted_candidate(self, tab_id: str, candidate: DanbooruAutocompleteCandidate):
        self.start_search(tab_id, candidate.value)

    def handle_conversion_result(self, tab_id: str, result):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        if result.is_single_match:
            self._search_converted_candidate(tab_id, result.matches[0])
            return
        if result.has_matches:
            self.interface.tab_mgr.set_tip(tab_id, f"? {len(result.matches)}", cls="theme-tip")
            tab.show_conversion_candidates(
                result.matches,
                on_selected=lambda candidate, tid=tab_id: self._search_converted_candidate(tid, candidate),
            )
            return
        content = "unknown"
        self.interface.tab_mgr.set_tip(tab_id, content, cls="theme-err")
        self.interface._show_info(InfoBar.warning, content, 4000)


class DanbooruDownloadController:
    def __init__(self, interface: "DanbooruInterface"):
        self.interface = interface

    def selected_posts_for_tab(self, tab_id: str) -> list[DanbooruPost]:
        state = self.interface.tab_states.get(tab_id)
        if state is None:
            return []
        return [post for post in state.result_list if post.post_id in state.selected_post_ids]

    def submit_selected(self):
        tab_id = self.interface.tab_mgr.active_tab_id()
        if not tab_id:
            return
        posts = self.selected_posts_for_tab(tab_id)
        if not posts:
            return
        self._submit_posts(
            list(posts),
            success_callback=lambda plan, tid=tab_id: self.handle_submission_result(tid, plan, True),
            task_id=f"danbooru-batch-submit-{tab_id}",
        )

    def submit_single(self, post: DanbooruPost, tab_id: t.Optional[str] = None):
        effective_tab_id = tab_id or self.interface.detail_preview_controller.current_tab_id or self.interface.tab_mgr.active_tab_id()
        if self.interface.sql_recorder.check_dupe(post.md5):
            self.interface.apply_downloaded_post(post.md5)
            return
        self._submit_posts(
            [post],
            success_callback=lambda plan, tid=effective_tab_id or "viewer": self.handle_submission_result(tid, plan, False),
            task_id=f"danbooru-single-submit-{effective_tab_id or 'viewer'}-{post.post_id}",
        )

    def _submit_posts(self, posts: list[DanbooruPost], *, success_callback, task_id: str):
        def submit_task(progress_callback=None, payload=list(posts)):
            return run_async(
                DanbooruDownloadSubmitter().submit(
                    payload,
                    completion_callback=self.interface.notify_download_result, progress_callback=progress_callback,
                )
            )

        execute_danbooru_task(
            self.interface.task_mgr,
            submit_task, success_callback=success_callback,
            error_callback=lambda err: self.interface._show_task_error(err, 6000), task_id=task_id,
        )

    def handle_submission_result(self, tab_id: str, plan, batch: bool):
        content = f"{len(plan.deduped_skipped)} skipped, {len(plan.to_submit)} completed, {len(plan.failed_pre_submit)} failed"
        self.interface.tab_mgr.set_tip(tab_id, content, cls="theme-success")
        if getattr(plan, "submission_errors", None):
            self.interface._show_info(InfoBar.warning, plan.submission_errors[0], 6000)
        for post in plan.deduped_skipped:
            self.interface.apply_downloaded_post(post.md5)
        if batch:
            self.interface._update_batch_button(tab_id)

    def on_download_result(self, md5_value: str, success: bool):
        if success:
            self.interface.sql_recorder.add(md5_value)
            self.interface.apply_downloaded_post(md5_value)
