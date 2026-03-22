from copy import deepcopy
import httpx
import os
import typing as t

from PySide6.QtCore import Qt, QEvent, QObject, QSize, QUrl
from PySide6.QtWidgets import QWidget, QLabel, QFrame
from PySide6.QtGui import QGuiApplication, QPixmap, QDesktopServices
from qfluentwidgets import (
    ProgressBar, VBoxLayout, PrimaryToolButton, TransparentToolButton,
    FluentIcon as FIF, TeachingTipTailPosition, ImageLabel
)

from GUI.core.anim import ExpandCollapseOrchestrator, ContentTarget
from GUI.core.timer import safe_single_shot
from GUI.manager.async_task import AsyncTaskManager, TaskConfig
from GUI.uic.qfluent.components import DlStatusBadge, CustomTeachingTip
from utils import conf, TaskObj, TasksObj, curr_os, get_httpx_verify
from utils.sql import SqlRecorder


class TaskProgress:
    """任务进度状态（不依赖 Qt）"""
    __slots__ = ('tasks_obj', '_downloaded_count', 'last_percent', 'completed')

    def __init__(self, tasks_obj: TasksObj):
        self.tasks_obj = tasks_obj
        self._downloaded_count = len(tasks_obj.downloaded)
        self.last_percent = (
            int(self._downloaded_count / tasks_obj.tasks_count * 100)
            if tasks_obj.tasks_count > 0 else 0
        )
        self.completed = self.last_percent >= 100

    @property
    def taskid(self) -> str:
        return self.tasks_obj.taskid

    @property
    def tasks_count(self) -> int:
        return self.tasks_obj.tasks_count

    @property
    def name(self) -> int:
        return self.tasks_obj.display_title

    @property
    def downloaded(self) -> int:
        return self._downloaded_count

    def apply(self, event: TaskObj) -> int:
        """接收一个下载事件，更新进度，返回百分比"""
        self._downloaded_count += 1
        self.last_percent = int(self._downloaded_count / self.tasks_obj.tasks_count * 100)
        if self.last_percent >= 100:
            self.completed = True
        return self.last_percent


class CoverBadgeGroup:
    BADGE_MARGIN = 4
    BADGE_SPACING = 3
    ACTION_BUTTON_SIZE = 18
    PAGE_BADGE_STYLE = (
        "background: rgba(0, 0, 0, 0.6);"
        "color: white;"
        "font-size: 9pt;"
        "padding: 1px 4px;"
        "border-radius: 3px;"
    )

    def __init__(self, parent: QWidget, tasks_count: int, tasks_obj: TasksObj):
        self.tasks_obj = tasks_obj
        self.folder_btn = self._create_action_badge(FIF.FOLDER, parent, self._open_task_folder)
        self.link_btn = self._create_action_badge(FIF.LINK, parent, self._open_task_link)
        self.page_badge = QLabel(parent)
        self.page_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.page_badge.setStyleSheet(self.PAGE_BADGE_STYLE)
        self.page_badge.setText(f"{tasks_count}P")
        self.page_badge.adjustSize()
        self.set_tasks_obj(tasks_obj)

    def _create_action_badge(self, icon, parent: QWidget, callback):
        btn = TransparentToolButton(icon, parent)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
        btn.setIconSize(QSize(12, 12))
        btn.setStyleSheet("background: rgba(20, 20, 20, 0.4);")
        btn.clicked.connect(callback)
        return btn

    def set_tasks_obj(self, tasks_obj: TasksObj):
        self.tasks_obj = tasks_obj
        self.folder_btn.setEnabled(bool(tasks_obj.local_path))
        self.link_btn.setEnabled(bool(tasks_obj.title_url))

    def relocate(self, cover_label: QWidget):
        self.page_badge.adjustSize()
        badge_y = cover_label.height() - self.page_badge.height() - self.BADGE_MARGIN
        curr_x = self.BADGE_MARGIN
        for widget in (self.folder_btn, self.link_btn, self.page_badge):
            widget.move(curr_x, badge_y)
            curr_x += widget.width() + self.BADGE_SPACING

    def _open_task_folder(self):
        curr_os.open_folder(self.tasks_obj.local_path)

    def _open_task_link(self):
        QDesktopServices.openUrl(QUrl(self.tasks_obj.title_url))


class ProgressClass(QFrame):
    MAX_TITLE_LENGTH = 70
    COVER_HEIGHT = 110
    DEFAULT_COVER_WIDTH = 130

    def __init__(
        self,
        taskid: str,
        tasks_count: int,
        parent: QWidget,
        tasks_obj: TasksObj,
        task_name: str = None,
    ):
        super().__init__(parent)
        self.taskid = taskid
        self.tasks_count = tasks_count
        self.is_completed = False
        self._last_percent = 0
        self._cover_source = None

        layout = VBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.cover_label = ImageLabel(self)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setStyleSheet("background: rgba(0, 0, 0, 0.08); border-radius: 4px;")
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setFixedSize(self.DEFAULT_COVER_WIDTH, self.COVER_HEIGHT)

        self.cbg = CoverBadgeGroup(self.cover_label, tasks_count, tasks_obj)
        self._relocate_badge()

        task_name = task_name or taskid
        display_name = self._clip_task_name(task_name)
        self.title_label = QLabel(display_name, self)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setWordWrap(False)
        self.title_label.setToolTip(task_name)

        self.progress_bar = ProgressBar(self)

        layout.addWidget(self.cover_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress_bar)

        self.setFixedWidth(self.DEFAULT_COVER_WIDTH + 8)

    @classmethod
    def _clip_task_name(cls, task_name: str) -> str:
        if len(task_name) <= cls.MAX_TITLE_LENGTH:
            return task_name
        split_mark = ' - '
        if split_mark not in task_name:
            return f"{task_name[:cls.MAX_TITLE_LENGTH - 3]}..."
        title, episode_name = task_name.rsplit(split_mark, 1)
        suffix = f"{split_mark}{episode_name}"
        remain = cls.MAX_TITLE_LENGTH - len(suffix) - 3
        if remain > 0:
            return f"{title[:remain]}...{suffix}"
        return f"{title[:15]}...{suffix[:cls.MAX_TITLE_LENGTH - 18]}..."

    def set_tasks_obj(self, tasks_obj: TasksObj):
        self.cbg.set_tasks_obj(tasks_obj)

    def _relocate_badge(self):
        self.cbg.relocate(self.cover_label)

    def _apply_cover_pixmap(self, pixmap: QPixmap) -> bool:
        if pixmap.isNull() or pixmap.height() <= 0:
            return False
        new_w = round(self.COVER_HEIGHT * pixmap.width() / pixmap.height())
        self.cover_label.setImage(pixmap)
        self.cover_label.setFixedSize(new_w, self.COVER_HEIGHT)
        self._relocate_badge()
        margins = self.layout().contentsMargins()
        self.setFixedWidth(self.cover_label.width() + margins.left() + margins.right())
        return True

    def set_cover(self, path: str):
        if not path:
            return
        if self._apply_cover_pixmap(QPixmap(path)):
            self._cover_source = "local"

    def set_preview_cover(self, pixmap: QPixmap):
        if self._cover_source == "local":
            return
        if self._apply_cover_pixmap(pixmap):
            self._cover_source = "preview"

    def set_progress(self, percent: int):
        self._last_percent = percent
        self.progress_bar.setValue(percent)

    def mark_completed(self):
        self.is_completed = True
        self.progress_bar.setCustomBarColor(light="#00ff00", dark="#00cc00")

    def dispose(self):
        self.deleteLater()


class TaskProgressEntry:
    """聚合：数据模型 + Native UI 视图"""
    __slots__ = ('progress', 'view')

    def __init__(self, progress: TaskProgress, view: t.Optional[ProgressClass] = None):
        self.progress = progress
        self.view = view


class ExpandPanelController(QObject):
    def __init__(self, gui, panel_min_height: int):
        super().__init__()
        self.gui = gui
        self.panel_min_height = panel_min_height
        self.expand_btn = None
        self.orchestrator = None
        self._transitioning = False
        self._sync_pending = False

    def bind(self, expand_btn):
        self.expand_btn = expand_btn
        self.orchestrator = ExpandCollapseOrchestrator(
            window_target=self.gui,
            content_targets=[
                ContentTarget(
                    widget=self.gui.scroll_area,
                    measure_height=lambda _widget: self._panel_target_height(),
                )
            ],
            window_target_height_getter=self._window_target_height,
            can_expand_window=self._can_expand_window,
            after_collapse=self._sync_scroll_visibility,
        )
        self._transitioning = False
        self.gui.scroll_area.viewport().installEventFilter(self)

    def cleanup(self):
        try:
            self.gui.scroll_area.viewport().removeEventFilter(self)
        except (RuntimeError, AttributeError):
            pass
        if self.orchestrator is not None:
            self.orchestrator.cleanup()
            self.orchestrator = None
        self._transitioning = False
        self._sync_pending = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._request_scroll_sync()
        return False

    def _request_scroll_sync(self):
        if self._sync_pending:
            return
        self._sync_pending = True
        safe_single_shot(0, self._do_scroll_sync)

    def _do_scroll_sync(self):
        self._sync_pending = False
        sa = self.gui.scroll_area
        if not sa.isVisible():
            return
        viewport_w = sa.viewport().width()
        if viewport_w <= 0:
            viewport_w = sa.width() - 2
        content_h = self.gui.flow_layout.heightForWidth(viewport_w)
        self.gui.scroll_content.setMinimumHeight(content_h)
        vbar = sa.scrollDelagate.vScrollBar
        vbar.scrollTo(vbar.maximum())

    def _reset_scroll_content_height(self):
        self.gui.scroll_content.setMinimumHeight(0)
        if self.orchestrator is not None:
            self.orchestrator.set_content_height(self.gui.scroll_area, 0)

    def stop_and_reset(self):
        self._transitioning = False
        if self.orchestrator is not None:
            self.orchestrator.stop()
            self.orchestrator.set_content_height(self.gui.scroll_area, 0)

    def on_expand_clicked(self):
        if self.expand_btn is None:
            return
        if self._transitioning or (self.orchestrator and self.orchestrator.is_transitioning):
            return
        self._transitioning = True
        self.expand_btn.expand()
        if self.orchestrator is None:
            self._transitioning = False
            return
        transition = self.orchestrator.expand if self.expand_btn.expanded else self.orchestrator.collapse
        if not transition(self._finish_transition):
            self._finish_transition()

    def _available_screen_height(self) -> int:
        window_handle = self.gui.windowHandle()
        screen = window_handle.screen() if window_handle is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry().height() if screen is not None else self.gui.maximumHeight()

    def _layout_overhead(self) -> int:
        gui = self.gui
        vl4_m = gui.verticalLayout_4.contentsMargins()
        sb_h = gui.statusbar.height() if gui.statusbar.isVisible() else 0
        vl2_spacing = gui.verticalLayout_2.spacing()
        fl_spacing = gui.funcLayout.spacing()
        bv_m = gui.barVLayout.contentsMargins()
        bv_spacing = gui.barVLayout.spacing()
        return (
            vl4_m.top() + vl4_m.bottom()
            + sb_h
            + vl2_spacing
            + gui.funcGroupBox.height()
            + fl_spacing
            + bv_m.top() + bv_m.bottom()
            + bv_spacing
            + gui.barHLayout.sizeHint().height()
        )

    def _panel_target_height(self) -> int:
        width = self.gui.scroll_area.viewport().width()
        if width <= 0:
            width = self.gui.width() - 20
        content_h = self.gui.flow_layout.heightForWidth(width)
        max_window = min(self.gui.maximumHeight(), self._available_screen_height())
        available = max_window - self._layout_overhead() - self.gui.showArea.minimumHeight()
        return max(self.panel_min_height, min(content_h, available))

    def _can_expand_window(self, panel_h: int) -> bool:
        return panel_h > 0 and self.gui.height() < min(
            self.gui.maximumHeight(), self._available_screen_height()
        )

    def _window_target_height(self, total_expand_delta: int) -> int:
        return min(
            self.gui.height() + total_expand_delta + 5,
            self.gui.maximumHeight(),
            self._available_screen_height(),
        )

    def _sync_scroll_visibility(self):
        self.gui.scroll_area.setVisible(self.expand_btn.expanded)

    def _finish_transition(self):
        self._transitioning = False


class TaskEntryController:
    def __init__(self, gui, entries, cover_http_cli, cover_task_mgr):
        self.gui = gui
        self.entries = entries
        self.cover_http_cli = cover_http_cli
        self.cover_task_mgr = cover_task_mgr

    @staticmethod
    def is_page_one(page) -> bool:
        if page is None:
            return False
        page_str = str(page).strip()
        if not page_str:
            return False
        stem, _ext = os.path.splitext(page_str)
        stem = stem.lower()
        if stem.isdigit():
            return int(stem.lstrip('0') or '0') == 1
        return stem in {'cover', 'front', 'first'}

    @staticmethod
    def cover_pixmap(data: bytes) -> QPixmap:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        return pixmap

    @staticmethod
    def cover_path(tasks_obj) -> t.Optional[str]:
        if not tasks_obj.local_path:
            return None
        filename = None
        for task_obj in tasks_obj.downloaded:
            page = getattr(task_obj, 'page', None)
            if not TaskEntryController.is_page_one(page):
                continue
            page_str = str(page).strip()
            _stem, ext = os.path.splitext(page_str)
            if ext:
                filename = page_str
            else:
                digits = len(str(tasks_obj.tasks_count))
                filename = f"{page_str.zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}"
            break
        if filename is None:
            digits = len(str(tasks_obj.tasks_count))
            filename = f"{'1'.zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}"
        path = os.path.join(tasks_obj.local_path, filename)
        return path if os.path.isfile(path) else None

    def clear_flow_layout(self):
        layout = getattr(self.gui, 'flow_layout', None)
        if layout is None:
            return
        while layout.count():
            layout.takeAt(0)

    def dispose_views(self, reset_view_ref: bool = False):
        self.clear_flow_layout()
        for entry in self.entries.values():
            if entry.view:
                entry.view.dispose()
                if reset_view_ref:
                    entry.view = None

    def rebuild_views(self, task_ids=None):
        self.clear_flow_layout()
        order = task_ids if task_ids is not None else list(self.entries.keys())
        for tid in order:
            entry = self.entries.get(tid)
            if entry is None:
                continue
            entry.view = self._create_view(entry.progress)
            self.gui.flow_layout.addWidget(entry.view)
            entry.view.set_progress(entry.progress.last_percent)
            if entry.progress.completed:
                entry.view.mark_completed()
            self.apply_cover(entry)

    def add_or_update(self, tasks_obj: TasksObj) -> bool:
        entry = self.entries.get(tasks_obj.taskid)
        if entry is not None:
            self.update_context(tasks_obj)
            return False
        progress = TaskProgress(tasks_obj)
        view = self._create_view(progress)
        self.gui.flow_layout.addWidget(view)
        entry = TaskProgressEntry(progress=progress, view=view)
        self.entries[tasks_obj.taskid] = entry
        if progress.last_percent > 0:
            view.set_progress(progress.last_percent)
        if progress.completed:
            view.mark_completed()
        self.apply_cover(entry)
        return True

    def update_context(self, tasks_obj: TasksObj):
        entry = self.entries.get(tasks_obj.taskid)
        if entry is None:
            return
        next_tasks_obj = deepcopy(tasks_obj)
        if next_tasks_obj.cover_bytes is None:
            next_tasks_obj.cover_bytes = entry.progress.tasks_obj.cover_bytes
        entry.progress.tasks_obj = next_tasks_obj
        if entry.view is None:
            return
        entry.view.set_tasks_obj(next_tasks_obj)
        self.apply_cover(entry)

    def update_progress(self, task_obj: TaskObj):
        entry = self.entries[task_obj.taskid]
        percent = entry.progress.apply(task_obj)
        if entry.view is not None and self.is_page_one(task_obj.page) and task_obj.success:
            cover = self.cover_path(entry.progress.tasks_obj)
            if cover:
                entry.view.set_cover(cover)
        if entry.view is not None:
            entry.view.set_progress(percent)
            if entry.progress.completed and not entry.view.is_completed:
                entry.view.mark_completed()

    def apply_cover(self, entry: TaskProgressEntry):
        tasks_obj = entry.progress.tasks_obj
        cover = self.cover_path(tasks_obj)
        if cover:
            entry.view.set_cover(cover)
        elif tasks_obj.cover_bytes:
            entry.view.set_preview_cover(self.cover_pixmap(tasks_obj.cover_bytes))
        elif tasks_obj.cover_url:
            self.schedule_cover_preload(tasks_obj)

    def on_cover_preload_success(self, taskid: str, data: bytes):
        entry = self.entries.get(taskid)
        if entry is None:
            return
        entry.progress.tasks_obj.cover_bytes = data
        if entry.view is not None:
            entry.view.set_preview_cover(self.cover_pixmap(data))

    def schedule_cover_preload(self, tasks_obj: TasksObj):
        if not tasks_obj.cover_url or tasks_obj.cover_bytes or self.cover_path(tasks_obj):
            return
        task_id = f"task_cover_{tasks_obj.taskid}"
        if self.cover_task_mgr.is_task_running(task_id):
            return
        config = TaskConfig(
            task_func=lambda _url=tasks_obj.cover_url: self.download_cover_bytes(_url),
            success_callback=lambda data, _taskid=tasks_obj.taskid: self.on_cover_preload_success(_taskid, data),
            error_callback=self.gui.log.error,
            tooltip_title="",
            show_tooltip=False,
            show_success_info=False,
            show_error_info=False,
            tooltip_parent=None,
        )
        self.cover_task_mgr.execute_task(task_id, config)

    def download_cover_bytes(self, url: str) -> bytes:
        resp = self.cover_http_cli.get(url)
        resp.raise_for_status()
        return resp.content

    def _create_view(self, progress: TaskProgress) -> ProgressClass:
        return ProgressClass(
            progress.taskid,
            progress.tasks_count,
            self.gui.scroll_content,
            progress.tasks_obj,
            progress.name,
        )


def teachtip(btn, accept_callback):
    acceptBtn = PrimaryToolButton(FIF.ACCEPT)
    tip = CustomTeachingTip.create([acceptBtn], 
        target=btn, parent=btn, 
        content="清空任务列表", tailPosition=TeachingTipTailPosition.RIGHT
    )
    acceptBtn.clicked.connect(accept_callback)
    acceptBtn.clicked.connect(tip.close)


class TaskProgressManager:
    PANEL_MIN_HEIGHT = 130

    def __init__(self, gui):
        self.gui = gui
        self._entries: t.Dict[str, TaskProgressEntry] = {}
        self.init_flag = True
        self.record_sql = SqlRecorder()
        transport = dict(proxy=f"http://{conf.proxies[0]}", retries=2) if conf.proxies else dict(retries=2)
        transport["verify"] = get_httpx_verify()
        self._cover_http_cli = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
                "Accept": "image/*",
            },
            transport=httpx.HTTPTransport(**transport),
            follow_redirects=True, timeout=15,
        )
        self._cover_task_mgr = AsyncTaskManager(gui)
        self._entry_ctrl = TaskEntryController(gui, self._entries, self._cover_http_cli, self._cover_task_mgr)
        self.expandBtn = None
        self._dl_status_badge = None
        self._panel_ctrl = ExpandPanelController(gui, self.PANEL_MIN_HEIGHT)

    def _on_clear_btn_clicked(self):
        teachtip(self.gui.clearBtn, self.zero_task_state)

    def init_native_panel(self):
        self._entry_ctrl.dispose_views()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self._panel_ctrl.cleanup()

        self._entries.clear()
        self.init_flag = True

        self.expandBtn = self.gui.expandBtn
        self.clearBtn = self.gui.clearBtn
        self.expandBtn.clicked.connect(self._panel_ctrl.on_expand_clicked)
        self.gui.clearBtn.clicked.connect(self._on_clear_btn_clicked)

        self._dl_status_badge = DlStatusBadge(parent=self.gui, target=self.expandBtn)
        self._dl_status_badge.hide()

        self._panel_ctrl.bind(self.expandBtn)

    def capture_native_snapshot(self) -> dict:
        return {'task_ids': list(self._entries.keys())}

    def rebind_native_panel(self, snapshot: dict = None):
        task_ids = snapshot.get('task_ids') if snapshot else None
        self._dispose_native_runtime_only()

        self.expandBtn = self.gui.expandBtn
        self.clearBtn = self.gui.clearBtn
        self._bind_native_signals_once()

        self._dl_status_badge = DlStatusBadge(parent=self.gui, target=self.expandBtn)
        self._dl_status_badge.hide()
        self._panel_ctrl.bind(self.expandBtn)

        self._rebuild_native_views(task_ids)
        self.gui.scroll_area.setVisible(False)
        self._panel_ctrl._reset_scroll_content_height()
        self._refresh_dl_status_badge()

    def _dispose_native_runtime_only(self):
        self._entry_ctrl.dispose_views(reset_view_ref=True)
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self._panel_ctrl.cleanup()

    def _bind_native_signals_once(self):
        self.expandBtn.clicked.connect(self._panel_ctrl.on_expand_clicked)
        self.clearBtn.clicked.connect(self._on_clear_btn_clicked)

    def _rebuild_native_views(self, task_ids=None):
        self._entry_ctrl.rebuild_views(task_ids)
        has_entries = len(self._entries) > 0
        self.expandBtn.setVisible(has_entries)
        self.clearBtn.setVisible(has_entries)

    def handle(self, task: t.Union[TasksObj, TaskObj]):
        if isinstance(task, TasksObj):
            added = self._entry_ctrl.add_or_update(task)
            if added:
                bw = getattr(self.gui, "BrowserWindow", None)
                if bw is not None and bw.isVisible():
                    bw.show_task_added_toast(task.display_title)
                if len(self._entries) == 1:
                    self.expandBtn.setVisible(True)
                    self.clearBtn.setVisible(True)
                self._refresh_dl_status_badge()
                self._panel_ctrl._request_scroll_sync()
            return

        if isinstance(task, TaskObj):
            if task.taskid not in self._entries:
                print(f"{task.taskid}: {task.page}")
            else:
                self.update_progress(task)

    def update_progress(self, task_obj: TaskObj):
        self._entry_ctrl.update_progress(task_obj)
        self._refresh_dl_status_badge()

        aggregate = self.aggregate_percent()
        self.gui.processbar_load(aggregate)

        completed = sum(1 for e in self._entries.values() if e.progress.completed)
        if completed == len(self._entries) and len(self._entries) > 0:
            self.gui.crawl_end(str(getattr(self.gui, "sv_path", "")))

    def aggregate_percent(self) -> int:
        if not self._entries:
            return 0
        total_downloaded = sum(e.progress.downloaded for e in self._entries.values())
        total_tasks = sum(e.progress.tasks_count for e in self._entries.values())
        if total_tasks == 0:
            return 0
        return int(total_downloaded * 100 / total_tasks)

    def _refresh_dl_status_badge(self):
        if self._dl_status_badge is None:
            return
        total = len(self._entries)
        if total == 0:
            self._dl_status_badge.hide()
            return
        completed = sum(1 for e in self._entries.values() if e.progress.completed)
        self._dl_status_badge.update_progress(completed, total)
        self._dl_status_badge.show()

    def zero_task_state(self):
        self._entry_ctrl.dispose_views()
        self._entries.clear()
        self.expandBtn.setVisible(False)
        self.clearBtn.setVisible(False)
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
        self._panel_ctrl.stop_and_reset()
        self._panel_ctrl._reset_scroll_content_height()
        self.gui.scroll_area.setVisible(False)
        if self.expandBtn.expanded:
            self.expandBtn.expanded = False
            self.expandBtn._anim_ctrl.rotate_to(0.0)

    @property
    def unfinished_tasks(self):
        _tasks_key = list(self._entries.keys())
        downloaded_taskids = self.record_sql.batch_check_dupe(_tasks_key)
        un_taskids = set(_tasks_key) - set(downloaded_taskids)
        return [self._entries[taskid].progress.tasks_obj for taskid in un_taskids]

    def close(self):
        self.record_sql.close()
