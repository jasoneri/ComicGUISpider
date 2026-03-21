import asyncio
import math
import typing as t
from dataclasses import dataclass, field

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import InfoBar

from utils.config.qc import danbooru_cfg
from utils.script.image.danbooru import (
    DANBOORU_PAGE_SIZE,
    DanbooruPost,
    build_danbooru_search_params,
    canonicalize_search_term,
    convert_moegirl_term,
    fetch_remote_bytes,
    search_danbooru_posts,
    submit_downloads,
)

if t.TYPE_CHECKING:
    from . import DanbooruCardWidget, DanbooruInterface, DanbooruTabWidget


def run_async(coro):
    return asyncio.run(coro)


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


class DanbooruSearchController:
    def __init__(self, interface: "DanbooruInterface"):
        self.interface = interface

    def start_search(self, tab_id: str, query: str):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None:
            return
        canonical_term = canonicalize_search_term(query)
        state.request_token += 1
        token = state.request_token
        state.query = canonical_term
        state.page_cursor = 1
        state.has_loaded_once = False
        state.result_list.clear()
        state.selected_md5_set.clear()
        state.has_more_results = True
        tab.clear_results()
        tab.search_edit.setText(canonical_term)
        tab.set_loading(True)
        self.interface._set_tab_tip(tab_id, "加载中...", cls="theme-tip")
        self.interface._log_search_request(tab_id, canonical_term, state.sort_mode, 1, DANBOORU_PAGE_SIZE)
        self.interface.task_mgr.execute_simple_task(
            lambda: run_async(search_danbooru_posts(canonical_term, order=state.sort_mode, page=1)),
            success_callback=lambda posts, tid=tab_id, tkn=token: self.handle_search_success(tid, tkn, posts, 1, True),
            error_callback=lambda err, tid=tab_id, tkn=token: self.handle_search_error(tid, tkn, err),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-search-{tab_id}-{token}",
        )

    def load_next_page(self, tab_id: str):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or state.loading or not state.has_more_results or not state.has_loaded_once:
            return
        state.request_token += 1
        token = state.request_token
        next_page = state.page_cursor + 1
        tab.set_loading(True)
        self.interface._set_tab_tip(tab_id, "加载中...", cls="theme-tip")
        self.interface._log_search_request(tab_id, state.query, state.sort_mode, next_page, DANBOORU_PAGE_SIZE)
        self.interface.task_mgr.execute_simple_task(
            lambda: run_async(search_danbooru_posts(state.query, order=state.sort_mode, page=next_page)),
            success_callback=lambda posts, tid=tab_id, tkn=token, pg=next_page: self.handle_search_success(tid, tkn, posts, pg, False),
            error_callback=lambda err, tid=tab_id, tkn=token: self.handle_search_error(tid, tkn, err),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-page-{tab_id}-{token}",
        )

    def handle_search_success(self, tab_id: str, token: int, posts: list[DanbooruPost], page: int, replace: bool):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or token != state.request_token:
            return
        tab.set_loading(False)
        state.page_cursor = page
        state.has_loaded_once = True
        state.has_more_results = len(posts) >= DANBOORU_PAGE_SIZE
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

    def handle_search_error(self, tab_id: str, token: int, error: str):
        tab = self.interface.tabs.get(tab_id)
        state = self.interface.tab_states.get(tab_id)
        if tab is None or state is None or token != state.request_token:
            return
        tab.set_loading(False)
        msg = f"搜索失败: {error.splitlines()[0]}"
        self.interface._set_tab_tip(tab_id, msg, cls="theme-err")
        self.interface._show_info(InfoBar.error, msg, 6000)

    def load_card_preview(self, tab: "DanbooruTabWidget", card: "DanbooruCardWidget"):
        preview_url = card.post.preview_file_url or card.post.file_url
        if not preview_url:
            return
        self.interface.task_mgr.execute_simple_task(
            lambda width=max(card.preview_fetch_width(), 280): fetch_pixmap(preview_url, width),
            success_callback=lambda raw, current_card=card: self.apply_card_preview(current_card, raw),
            error_callback=lambda _err, current_card=card: current_card.preview_button.setText("Preview Error"),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-card-preview-{tab.state.tab_id}-{card.post.md5}",
        )

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
        term = canonicalize_search_term(tab.search_edit.text())
        if not term:
            return
        self.interface.task_mgr.execute_simple_task(
            lambda: run_async(convert_moegirl_term(term)),
            success_callback=lambda result, tid=tab_id: self.handle_conversion_result(tid, result),
            error_callback=lambda err: self.interface._show_info(InfoBar.error, f"转换失败: {err.splitlines()[0]}", 6000),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-convert-{tab_id}",
        )

    def handle_conversion_result(self, tab_id: str, result):
        tab = self.interface.tabs.get(tab_id)
        if tab is None:
            return
        if result.success and result.converted_term:
            tab.search_edit.setText(result.converted_term)
            self.interface._update_tab_title(tab_id, result.converted_term)
            self.interface._set_tab_tip(tab_id, f"已转换为: {result.converted_term}", cls="theme-success")
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

        def submit_task(progress_callback=None, payload=list(posts)):
            return run_async(
                submit_downloads(
                    payload,
                    completion_callback=self.interface.notify_download_result,
                    progress_callback=progress_callback,
                )
            )

        self.interface.task_mgr.execute_simple_task(
            submit_task,
            success_callback=lambda plan, tid=tab_id: self.handle_submission_result(tid, plan, True),
            error_callback=lambda err: self.interface._show_info(InfoBar.error, f"提交失败: {err.splitlines()[0]}", 6000),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-batch-submit-{tab_id}",
        )

    def submit_single(self, post: DanbooruPost, tab_id: t.Optional[str] = None):
        effective_tab_id = tab_id or self.interface._viewer_tab_id or self.interface._active_tab_id()
        tab = self.interface.tabs.get(effective_tab_id) if effective_tab_id else None
        if self.interface.sql_recorder.check_dupe(post.md5):
            if tab is not None:
                tab.apply_downloaded_state(post.md5)
            if self.interface.image_viewer.post is not None and self.interface.image_viewer.post.md5 == post.md5:
                self.interface.image_viewer.set_download_state(True)
            return

        def submit_task(progress_callback=None, payload=post):
            return run_async(
                submit_downloads(
                    [payload],
                    completion_callback=self.interface.notify_download_result,
                    progress_callback=progress_callback,
                )
            )

        self.interface.task_mgr.execute_simple_task(
            submit_task,
            success_callback=lambda plan, tid=effective_tab_id or "viewer": self.handle_submission_result(tid, plan, False),
            error_callback=lambda err: self.interface._show_info(InfoBar.error, f"提交失败: {err.splitlines()[0]}", 6000),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-single-submit-{effective_tab_id or 'viewer'}-{post.post_id}",
        )

    def handle_submission_result(self, tab_id: str, plan, batch: bool):
        content = f"{len(plan.deduped_skipped)} skipped, {len(plan.to_submit)} completed, {len(plan.failed_pre_submit)} failed"
        self.interface._show_info(InfoBar.success, content, 4000)
        if getattr(plan, "submission_errors", None):
            self.interface._show_info(InfoBar.warning, plan.submission_errors[0], 6000)
        for post in plan.deduped_skipped:
            self.apply_downloaded_to_all_tabs(post.md5)
        if batch:
            self.interface._update_batch_button(tab_id)

    def on_download_result(self, md5_value: str, success: bool):
        if success:
            self.interface.sql_recorder.add(md5_value)
            self.apply_downloaded_to_all_tabs(md5_value)

    def apply_downloaded_to_all_tabs(self, md5_value: str):
        for tab in self.interface.tabs.values():
            tab.apply_downloaded_state(md5_value)
        if self.interface.image_viewer.post is not None and self.interface.image_viewer.post.md5 == md5_value:
            self.interface.image_viewer.set_download_state(True)
        self.interface._sync_viewer_navigation()
