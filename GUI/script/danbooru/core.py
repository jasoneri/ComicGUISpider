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
from utils.script.image.danbooru.client import (
    autocomplete_danbooru_tags,
    fetch_remote_bytes,
    fetch_remote_image_size,
    search_danbooru_posts,
)
from utils.script.image.danbooru.constants import DANBOORU_PAGE_SIZE
from utils.script.image.danbooru.download import DanbooruDownloadSubmitter
from utils.script.image.danbooru.http import DanbooruChallengeRequired
from utils.script.image.danbooru.models import DanbooruAutocompleteCandidate, DanbooruPost, DanbooruSearchQuery

if t.TYPE_CHECKING:
    from . import DanbooruCardWidget, DanbooruInterface, DanbooruTabWidget


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


class DanbooruReq:
    @staticmethod
    def _run(coro) -> DanbooruReqResult:
        try:
            return DanbooruReqResult(value=run_async(coro))
        except DanbooruChallengeRequired as exc:
            return DanbooruReqResult(challenge=exc)

    @staticmethod
    def search(query: str, *, order: str = "", page: int = 1) -> DanbooruReqResult:
        return DanbooruReq._run(search_danbooru_posts(query, order=order, page=page))

    @staticmethod
    def autocomplete(term: str) -> DanbooruReqResult:
        return DanbooruReq._run(autocomplete_danbooru_tags(term))

    @staticmethod
    def fetch_preview(url: str, *, max_width: int = 280) -> DanbooruReqResult:
        try:
            return DanbooruReqResult(value=fetch_pixmap(url, max_width))
        except DanbooruChallengeRequired as exc:
            return DanbooruReqResult(challenge=exc)

    @staticmethod
    def fetch_image_size(url: str) -> DanbooruReqResult:
        return DanbooruReq._run(fetch_remote_image_size(url))


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
            available_bounds=normalized_available,
            max_display_bounds=max_display_bounds,
            display_size=display_size,
            target_area=max(1, int(round(normalized_available.width() * normalized_available.height() * area_ratio))),
            axis_scale=axis_scale,
        )


def fetch_pixmap(url: str, max_width: int = 280) -> bytes:
    raw = run_async(fetch_remote_bytes(url, timeout=20.0))
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
    result_list: list[DanbooruPost] = field(default_factory=list)
    selected_md5_set: set[str] = field(default_factory=set)
    request_token: int = 0
    has_more_results: bool = True
    loading: bool = False
    has_loaded_once: bool = False

    def begin_request(self) -> int:
        self.request_token += 1
        return self.request_token

    def reset_results(self, *, query: t.Optional[str] = None):
        if query is not None:
            self.query = query
        self.page_cursor = 1
        self.result_list.clear()
        self.selected_md5_set.clear()
        self.has_more_results = True
        self.has_loaded_once = False

    def mark_loaded_page(self, posts: t.Sequence[DanbooruPost], page: int):
        self.page_cursor = page
        self.has_loaded_once = True
        self.has_more_results = len(posts) >= DANBOORU_PAGE_SIZE

    def can_load_next_page(self) -> bool:
        return not self.loading and self.has_more_results and self.has_loaded_once


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
        self._drag_select_seed: set[str] = set()
        self._install_drag_select_source(self.tab.scroll_area.viewport())
        self._install_drag_select_source(self.tab.scroll_content)

    def apply_theme(self, *, selection_border: str, selection_background: str):
        self._selection_band.setStyleSheet(
            f"border: 2px dashed {selection_border}; background: {selection_background};"
        )

    def bind_card(self, card: "DanbooruCardWidget"):
        card.selection_changed.connect(self._on_card_selection_changed)
        self._apply_card_selection(card, card.post.md5 in self.tab.state.selected_md5_set, emit_count=False)
        self._install_drag_select_source(card)
        self._install_drag_select_source(card.preview_frame)
        self._install_drag_select_source(card.preview_button)

    def set_card_selected(self, card: "DanbooruCardWidget", selected: bool):
        self._apply_card_selection(card, selected)

    def sync_selection_count(self):
        self.selection_count_changed.emit(len(self.tab.state.selected_md5_set))

    def selection_count(self) -> int:
        return len(self.tab.state.selected_md5_set)

    def has_selection(self) -> bool:
        return bool(self.tab.state.selected_md5_set)

    def clear(self):
        self._reset_drag_select_state()
        self._set_selected_md5s(set())

    def mark_downloaded(self, md5_value: str):
        card = self.tab.card_widgets.get(md5_value)
        if card is not None:
            card.set_already_downloaded(True)
        self.tab.state.selected_md5_set.discard(md5_value)
        self.sync_selection_count()

    def _apply_card_selection(
        self,
        card: "DanbooruCardWidget",
        selected: bool,
        *,
        sync_widget: bool = True,
        emit_count: bool = True,
    ):
        if sync_widget:
            card.set_selected(selected)
            selected = card.checkbox.isChecked()
        if selected:
            self.tab.state.selected_md5_set.add(card.post.md5)
        else:
            self.tab.state.selected_md5_set.discard(card.post.md5)
        if emit_count:
            self.sync_selection_count()

    def _on_card_selection_changed(self, card: "DanbooruCardWidget", selected: bool):
        self._apply_card_selection(card, selected, sync_widget=False)

    def _install_drag_select_source(self, widget: QWidget):
        widget.setProperty("danbooruDragSelectSource", True)
        widget.installEventFilter(self)

    def _set_selected_md5s(self, md5_values: t.Iterable[str], *, emit_count: bool = True):
        target_md5s = {
            md5
            for md5 in md5_values
            if (card := self.tab.card_widgets.get(md5)) is not None and card.checkbox.isEnabled()
        }
        current_md5s = set(self.tab.state.selected_md5_set)
        if current_md5s == target_md5s:
            return
        for md5 in current_md5s - target_md5s:
            card = self.tab.card_widgets.get(md5)
            if card is None:
                self.tab.state.selected_md5_set.discard(md5)
                continue
            self._apply_card_selection(card, False, emit_count=False)
        for md5 in target_md5s - current_md5s:
            card = self.tab.card_widgets.get(md5)
            if card is not None:
                self._apply_card_selection(card, True, emit_count=False)
        if emit_count:
            self.sync_selection_count()

    def _viewport_point_from_global(self, global_pos: QtCore.QPoint) -> QtCore.QPoint:
        viewport = self.tab.scroll_area.viewport()
        rect = viewport.rect()
        point = viewport.mapFromGlobal(global_pos)
        return QtCore.QPoint(
            min(max(point.x(), rect.left()), rect.right()),
            min(max(point.y(), rect.top()), rect.bottom()),
        )

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

    def _selected_md5s_for_rect(self, selection_rect: QtCore.QRect) -> set[str]:
        if selection_rect.width() < 5 and selection_rect.height() < 5:
            return set(self._drag_select_seed)
        viewport = self.tab.scroll_area.viewport()
        hit_md5s = set(self._drag_select_seed)
        for card in self.tab.card_widgets.values():
            if not card.checkbox.isEnabled():
                continue
            card_rect = QtCore.QRect(card.mapTo(viewport, QtCore.QPoint(0, 0)), card.size())
            if selection_rect.intersects(card_rect):
                hit_md5s.add(card.post.md5)
        return hit_md5s

    def _preview_drag_selection(self, selection_rect: QtCore.QRect):
        self._set_selected_md5s(self._selected_md5s_for_rect(selection_rect))

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
            self._drag_select_seed = set(self.tab.state.selected_md5_set)
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
            if self._drag_select_origin is None:
                return super().eventFilter(obj, event)
            selection_rect = self._selection_band.geometry()
            drag_was_active = self._drag_select_active
            target_md5s = self._selected_md5s_for_rect(selection_rect) if drag_was_active else set()
            self._reset_drag_select_state()
            if drag_was_active:
                self._set_selected_md5s(target_md5s)
                return True
            return False
        return super().eventFilter(obj, event)


class DanbooruSearchController:
    def __init__(self, interface: "DanbooruInterface"):
        self.interface = interface

    def start_search(self, tab_id: str, query: str):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None:
            return
        canonical_term = DanbooruSearchQuery.normalize(query)
        token = state.begin_request()
        tab.clear_results(query=canonical_term)
        tab.set_loading(True)
        self._submit_search_request(
            tab_id=tab_id,
            query=state.query,
            order=state.sort_mode,
            page=1,
            token=token,
            replace=True,
            task_prefix="search",
        )

    def load_next_page(self, tab_id: str):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or not state.can_load_next_page():
            return
        token = state.begin_request()
        next_page = state.page_cursor + 1
        tab.set_loading(True)
        self._submit_search_request(
            tab_id=tab_id,
            query=state.query,
            order=state.sort_mode,
            page=next_page,
            token=token,
            replace=False,
            task_prefix="page",
        )

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
    ):
        self.interface._set_tab_tip(tab_id, "加载中...", cls="theme-tip")
        self.interface._log_search_request(tab_id, query, order, page, DANBOORU_PAGE_SIZE)
        execute_danbooru_task(
            self.interface.task_mgr,
            lambda current_query=query, current_order=order, current_page=page: DanbooruReq.search(
                current_query,
                order=current_order,
                page=current_page,
            ),
            success_callback=lambda result, tid=tab_id, tkn=token, pg=page, do_replace=replace: self.handle_search_result(tid, tkn, result, pg, do_replace),
            error_callback=lambda err, tid=tab_id, tkn=token: self.handle_search_error(tid, tkn, err),
            task_id=f"danbooru-{task_prefix}-{tab_id}-{token}",
        )

    def handle_search_result(
        self, tab_id: str, token: int,
        result: DanbooruReqResult, page: int, replace: bool,
    ):
        if result.challenge is not None:
            self.handle_search_challenge(tab_id, token, result.challenge, page=page, replace=replace)
            return
        self.handle_search_success(tab_id, token, result.value or [], page, replace)

    def handle_search_success(self, tab_id: str, token: int, posts: list[DanbooruPost], page: int, replace: bool):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or token != state.request_token:
            return
        tab.set_loading(False)
        state.mark_loaded_page(posts, page)
        self.interface._update_tab_title(tab_id, state.query)
        if not posts and replace:
            self.interface._set_tab_tip(tab_id, "无结果", cls="theme-tip")
            return
        downloaded_md5s = self.interface.sql_recorder.batch_check_dupe([post.md5 for post in posts if post.md5])
        appended_cards = tab.append_results(posts, downloaded_md5s)
        if replace:
            self.interface._set_tab_tip(tab_id, "已进入 Danbooru 首页" if not state.query else "已加载结果", cls="theme-success")
        else:
            self.interface._set_tab_tip(tab_id, "已追加内容" if not state.query else "已追加更多结果", cls="theme-success")
        danbooru_cfg.add_history(state.query)
        self.interface._refresh_completer(tab)
        for card in appended_cards:
            self.load_card_preview(tab, card)
        if not state.has_more_results:
            self.interface._set_tab_tip(tab_id, "没有更多结果", cls="theme-tip")

    def handle_search_challenge(
        self, tab_id: str, token: int, challenge: DanbooruChallengeRequired,
        *, page: int, replace: bool,
    ):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or token != state.request_token:
            return
        tab.set_loading(False)
        self.interface._set_tab_tip(tab_id, "Danbooru 需要网页验证，完成后会自动重试", cls="theme-tip")
        self.interface._show_info(InfoBar.warning, "Danbooru 需要网页验证，验证通过后会自动重试", 7000)
        retry_callback = (
            (lambda tid=tab_id, query=state.query: self.start_search(tid, query))
            if replace or page <= 1
            else (lambda tid=tab_id: self.load_next_page(tid))
        )
        self.interface.challenge_controller.submit(
            tab_id,
            challenge,
            retry_callback,
            reason="搜索请求",
            retry_key=f"search:{tab_id}:{page}:{int(replace)}",
        )

    def handle_search_error(self, tab_id: str, token: int, error: str):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or token != state.request_token:
            return
        tab.set_loading(False)
        summary = (error.splitlines() or ["unknown error"])[0]
        msg = f"搜索失败: {summary}"
        self.interface._set_tab_tip(tab_id, msg, cls="theme-err")
        self.interface._show_task_error("搜索失败", error, 6000)

    def load_card_preview(self, tab: "DanbooruTabWidget", card: "DanbooruCardWidget"):
        preview_url = card.post.preview_file_url or card.post.file_url
        if not preview_url:
            return
        execute_danbooru_task(
            self.interface.task_mgr,
            lambda width=max(card.preview_fetch_width(), 280): DanbooruReq.fetch_preview(preview_url, max_width=width),
            success_callback=lambda payload, tid=tab.state.tab_id, pid=card.post.post_id: self.handle_card_preview_result(tid, pid, payload),
            error_callback=lambda _err, current_card=card: current_card.preview_button.setText("Preview Error"),
            task_id=f"danbooru-card-preview-{tab.state.tab_id}-{card.post.md5}",
        )

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
                tab_id,
                payload.challenge,
                lambda tid=tab_id, pid=post_id: self.retry_card_preview(tid, pid),
                reason="缩略图加载",
                retry_key=f"card-preview:{tab_id}:{post_id}",
            )
            return
        self.apply_card_preview(card, payload.value)

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
            lambda: DanbooruReq.autocomplete(term),
            success_callback=lambda payload, tid=tab_id: self.handle_conversion_task_result(tid, payload),
            error_callback=lambda err: self.interface._show_task_error("转换失败", err, 6000),
            task_id=f"danbooru-convert-{tab_id}",
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
            tab_id,
            challenge,
            lambda tid=tab_id: self.convert_term(tid),
            reason="标签转换",
            retry_key=f"convert:{tab_id}",
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
            self.interface._set_tab_tip(tab_id, f"找到 {len(result.matches)} 个候选，请选择", cls="theme-tip")
            tab.show_conversion_candidates(
                result.matches,
                on_selected=lambda candidate, tid=tab_id: self._search_converted_candidate(tid, candidate),
            )
            return
        reason = result.reason or "unknown"
        self.interface._set_tab_tip(tab_id, f"转换失败: {reason}", cls="theme-err")
        self.interface._show_info(InfoBar.warning, f"转换失败: {reason}", 4000)


class DanbooruDownloadController:
    def __init__(self, interface: "DanbooruInterface"):
        self.interface = interface

    def selected_posts_for_tab(self, tab_id: str) -> list[DanbooruPost]:
        state = self.interface.tab_states.get(tab_id)
        if state is None:
            return []
        return [post for post in state.result_list if post.md5 in state.selected_md5_set]

    def submit_selected(self):
        tab_id = self.interface._active_tab_id()
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
        effective_tab_id = tab_id or self.interface.detail_preview_controller.current_tab_id or self.interface._active_tab_id()
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
                    completion_callback=self.interface.notify_download_result,
                    progress_callback=progress_callback,
                )
            )

        execute_danbooru_task(
            self.interface.task_mgr,
            submit_task,
            success_callback=success_callback,
            error_callback=lambda err: self.interface._show_task_error("提交失败", err, 6000),
            task_id=task_id,
        )

    def handle_submission_result(self, tab_id: str, plan, batch: bool):
        content = f"{len(plan.deduped_skipped)} skipped, {len(plan.to_submit)} completed, {len(plan.failed_pre_submit)} failed"
        self.interface._show_info(InfoBar.success, content, 4000)
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
