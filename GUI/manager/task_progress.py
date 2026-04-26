import os
import gc
import typing as t
from copy import deepcopy

from PySide6.QtCore import Qt, QEvent, QObject, QRect, QSize, QUrl
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
from utils import conf, TaskObj, TasksObj, curr_os
from utils.sql import SqlRecorder
from utils.website.registry import create_gui_site_runtime, resolve_provider_descriptor_by_site


class TaskProgress:
    """任务进度状态（不依赖 Qt）"""
    __slots__ = ("tasks_obj", "_downloaded_count", "last_percent", "completed")

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
    def downloaded(self) -> int:
        return self._downloaded_count

    def apply(self, event: TaskObj) -> int:
        """接收一个下载事件，更新进度，返回百分比"""
        self._downloaded_count += 1
        self.last_percent = int(self._downloaded_count / self.tasks_obj.tasks_count * 100)
        if self.last_percent >= 100:
            self.completed = True
        return self.last_percent

    def record_job_result(self, *, success: bool, error: str | None = None) -> bool:
        was_completed = self.completed
        if not success:
            self.completed = False
        return was_completed != self.completed


class ProgressClass(QFrame):
    MAX_TITLE_LENGTH = 70
    COVER_HEIGHT = 110
    DEFAULT_COVER_WIDTH = 130
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

    def __init__(self, parent: QWidget, progress: TaskProgress):
        super().__init__(parent)
        self.taskid = progress.taskid
        self._cover_source = None
        self.tasks_obj = progress.tasks_obj

        layout = VBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.cover_label = ImageLabel(self)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setStyleSheet("background: rgba(0, 0, 0, 0.08); border-radius: 4px;")
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setFixedSize(self.DEFAULT_COVER_WIDTH, self.COVER_HEIGHT)

        for attr, icon, callback in (
            ("folder_btn", FIF.FOLDER, self._open_task_folder),
            ("link_btn", FIF.LINK, self._open_task_link),
        ):
            btn = TransparentToolButton(icon, self.cover_label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
            btn.setIconSize(QSize(12, 12))
            btn.setStyleSheet("background: rgba(20, 20, 20, 0.4);")
            btn.clicked.connect(callback)
            setattr(self, attr, btn)
        self.page_badge = QLabel(self.cover_label)
        self.page_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.page_badge.setStyleSheet(self.PAGE_BADGE_STYLE)
        self.title_label = QLabel(self)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setWordWrap(False)
        self.progress_bar = ProgressBar(self)

        layout.addWidget(self.cover_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress_bar)

        self.setFixedWidth(self.DEFAULT_COVER_WIDTH + 8)
        self.set_tasks_obj(progress.tasks_obj)

    @classmethod
    def _clip_task_name(cls, task_name: str) -> str:
        if len(task_name) <= cls.MAX_TITLE_LENGTH:
            return task_name
        split_mark = " - "
        if split_mark not in task_name:
            return f"{task_name[:cls.MAX_TITLE_LENGTH - 3]}..."
        title, episode_name = task_name.rsplit(split_mark, 1)
        suffix = f"{split_mark}{episode_name}"
        remain = cls.MAX_TITLE_LENGTH - len(suffix) - 3
        if remain > 0:
            return f"{title[:remain]}...{suffix}"
        return f"{title[:15]}...{suffix[:cls.MAX_TITLE_LENGTH - 18]}..."

    def set_tasks_obj(self, tasks_obj: TasksObj):
        self.tasks_obj = tasks_obj
        task_name = tasks_obj.display_title or self.taskid
        self.title_label.setText(self._clip_task_name(task_name))
        self.title_label.setToolTip(task_name)
        self.folder_btn.setEnabled(bool(tasks_obj.local_path))
        self.link_btn.setEnabled(bool(tasks_obj.title_url))
        self.page_badge.setText(f"{tasks_obj.tasks_count}P")
        self.page_badge.adjustSize()
        self._relocate_badge()

    def _relocate_badge(self):
        self.page_badge.adjustSize()
        badge_y = self.cover_label.height() - self.page_badge.height() - self.BADGE_MARGIN
        curr_x = self.BADGE_MARGIN
        for widget in (self.folder_btn, self.link_btn, self.page_badge):
            widget.move(curr_x, badge_y)
            curr_x += widget.width() + self.BADGE_SPACING

    def _open_task_folder(self):
        curr_os.open_folder(self.tasks_obj.local_path)

    def _open_task_link(self):
        QDesktopServices.openUrl(QUrl(self.tasks_obj.title_url))

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
        if path and self._apply_cover_pixmap(QPixmap(path)):
            self._cover_source = "local"

    def set_preview_cover(self, pixmap: QPixmap):
        if self._cover_source != "local" and self._apply_cover_pixmap(pixmap):
            self._cover_source = "preview"

    def set_progress(self, percent: int):
        self.progress_bar.setValue(percent)

    def dispose(self):
        self.deleteLater()


class TaskProgressEntry:
    """单条任务 owner：进度、视图、封面预载、上下文替换都归这里。"""

    __slots__ = ("owner", "progress", "view")

    def __init__(self, owner: "TaskProgressManager", tasks_obj: TasksObj):
        self.owner = owner
        self.progress = TaskProgress(tasks_obj)
        self.view: t.Optional[ProgressClass] = None

    @property
    def taskid(self) -> str:
        return self.progress.taskid

    @property
    def tasks_obj(self) -> TasksObj:
        return self.progress.tasks_obj

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
            return int(stem.lstrip("0") or "0") == 1
        return stem in {"cover", "front", "first"}

    @staticmethod
    def cover_pixmap(data: bytes) -> QPixmap:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        return pixmap

    def mount(self):
        if self.view is not None:
            return
        gui = self.owner.gui
        self.view = ProgressClass(gui.scroll_content, self.progress)
        gui.flow_layout.addWidget(self.view)
        self.refresh_view()

    def dispose_view(self, reset_view_ref: bool = False):
        if self.view is None:
            return
        self.view.dispose()
        if reset_view_ref:
            self.view = None

    def replace_tasks_obj(self, tasks_obj: TasksObj):
        next_tasks_obj = deepcopy(tasks_obj)
        if next_tasks_obj.cover_bytes is None:
            next_tasks_obj.cover_bytes = self.tasks_obj.cover_bytes
        self.progress.tasks_obj = next_tasks_obj
        self.refresh_view()

    def apply_task(self, task_obj: TaskObj) -> bool:
        layout_changed = False
        percent = self.progress.apply(task_obj)
        if self.view is not None and self.is_page_one(task_obj.page) and task_obj.success:
            cover = self.cover_path()
            if cover:
                self.view.set_cover(cover)
                layout_changed = True
        if self.view is not None:
            self.view.set_progress(percent)
        return layout_changed

    def record_job_result(self, *, success: bool, error: str | None = None) -> bool:
        return self.progress.record_job_result(success=success, error=error)

    def refresh_view(self):
        if self.view is None:
            return
        self.view.set_tasks_obj(self.tasks_obj)
        self.view.set_progress(self.progress.last_percent)
        cover = self.cover_path()
        if cover:
            self.view.set_cover(cover)
            return
        if self.tasks_obj.cover_bytes:
            self.view.set_preview_cover(self.cover_pixmap(self.tasks_obj.cover_bytes))
            return
        self.schedule_cover_preload()

    def cover_path(self) -> t.Optional[str]:
        if not self.tasks_obj.local_path:
            return None
        filename = None
        for task_obj in self.tasks_obj.downloaded:
            page = getattr(task_obj, "page", None)
            if not self.is_page_one(page):
                continue
            page_str = str(page).strip()
            _stem, ext = os.path.splitext(page_str)
            if ext:
                filename = page_str
            else:
                digits = len(str(self.tasks_obj.tasks_count))
                filename = f"{page_str.zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}"
            break
        if filename is None:
            digits = len(str(self.tasks_obj.tasks_count))
            filename = f"{'1'.zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}"
        path = os.path.join(self.tasks_obj.local_path, filename)
        return path if os.path.isfile(path) else None

    def schedule_cover_preload(self):
        if (
            not self.tasks_obj.cover_url
            or self.tasks_obj.cover_bytes
            or self.cover_path()
        ):
            return
        provider_descriptor = resolve_provider_descriptor_by_site(self.tasks_obj.source)
        cover_preload_via_http = bool(getattr(provider_descriptor.provider_cls, "cover_preload_via_http", True))
        if not cover_preload_via_http:
            return
        task_id = f"task_cover_{self.taskid}"
        cover_task_mgr = self.owner.cover_task_mgr
        if cover_task_mgr.is_task_running(task_id):
            return
        cover_task_mgr.execute_task(
            task_id,
            TaskConfig(
                task_func=self.download_cover_bytes,
                success_callback=self.on_cover_preload_success,
                error_callback=self.owner.gui.log.error,
                tooltip_title="",
                show_tooltip=False,
                show_success_info=False,
                show_error_info=False,
                tooltip_parent=None,
            ),
        )

    def on_cover_preload_success(self, data: bytes):
        self.tasks_obj.cover_bytes = data
        if self.view is not None:
            self.view.set_preview_cover(self.cover_pixmap(data))

    def download_cover_bytes(self) -> bytes:
        thread_site_runtime = create_gui_site_runtime(
            self.tasks_obj.source,
            conf_state=conf,
        ).create_thread_site_runtime()
        try:
            return thread_site_runtime.download_cover_bytes(self.tasks_obj)
        finally:
            thread_site_runtime.close()


class TaskPanelDisplayController(QObject):
    def __init__(self, owner: "TaskProgressManager", layout: "TaskPanelLayoutController"):
        super().__init__()
        self.owner = owner
        self.layout = layout
        self._sync_pending = False
        self._stick_to_bottom = False
        self._viewport = None

    def bind(self):
        self._viewport = self.owner.gui.scroll_area.viewport()
        self._viewport.installEventFilter(self)
        self._sync_pending = False
        self._stick_to_bottom = False

    def cleanup(self):
        if self._viewport is not None:
            self._viewport.removeEventFilter(self)
            self._viewport = None
        self._sync_pending = False
        self._stick_to_bottom = False

    def eventFilter(self, obj, event):
        if obj is self._viewport and event.type() == QEvent.Resize:
            self.request_refresh()
        return False

    def request_refresh(self, *, stick_to_bottom: bool = False):
        self._stick_to_bottom = self._stick_to_bottom or stick_to_bottom
        if not self.owner.gui.scroll_area.isVisible():
            return
        if self._sync_pending:
            return
        self._sync_pending = True
        safe_single_shot(0, self.refresh)

    def hide_panel(self):
        self.owner.gui.scroll_area.setVisible(False)

    def reset(self):
        gui = self.owner.gui
        self._sync_pending = False
        self._stick_to_bottom = False
        gui.scroll_content.setMinimumHeight(0)
        gui.scroll_content.resize(gui.scroll_content.width(), 0)

    def refresh(self):
        self._sync_pending = False
        gui = self.owner.gui
        scroll_area = gui.scroll_area
        if not scroll_area.isVisible():
            return
        native_bar = scroll_area.verticalScrollBar()
        should_stick = self._stick_to_bottom or self._is_at_bottom(native_bar)
        self._stick_to_bottom = False

        viewport = scroll_area.viewport()
        viewport_w = max(1, viewport.width())
        viewport_h = max(0, viewport.height())
        content_w, content_h = self.layout.layout_metrics(viewport_h)
        target_h = max(scroll_area.viewport().height(), content_h)
        gui.scroll_content.setMinimumHeight(target_h)
        gui.scroll_content.resize(viewport_w, target_h)
        gui.flow_layout.setGeometry(QRect(0, 0, content_w, content_h))
        gui.scroll_content.updateGeometry()
        scroll_area.widget().updateGeometry()
        viewport.update()
        if should_stick:
            native_bar.setValue(native_bar.maximum())

    @staticmethod
    def _is_at_bottom(scroll_bar) -> bool:
        if scroll_bar.maximum() <= 0:
            return True
        return scroll_bar.maximum() - scroll_bar.value() <= 2


class TaskPanelLayoutController(QObject):
    def __init__(self, owner: "TaskProgressManager"):
        super().__init__()
        self.owner = owner

    def panel_target_height(self, available_height: int) -> int:
        _layout_w, content_h = self.layout_metrics(max(0, available_height))
        if content_h <= 0:
            return self.owner.PANEL_MIN_HEIGHT
        return max(self.owner.PANEL_MIN_HEIGHT, min(content_h, available_height))

    def layout_metrics(self, viewport_height: int | None = None) -> tuple[int, int]:
        layout_w = self.content_width()
        content_h = self.content_height_for_width(layout_w)
        if viewport_height is None:
            viewport_height = max(0, self.owner.gui.scroll_area.viewport().height())
        if content_h <= viewport_height:
            return layout_w, content_h
        gutter = self.vertical_overlay_width()
        if gutter <= 0 or layout_w <= gutter:
            return layout_w, content_h
        layout_w = max(1, layout_w - gutter)
        return layout_w, self.content_height_for_width(layout_w)

    def content_height_for_width(self, width: int | None = None) -> int:
        gui = self.owner.gui
        flow_layout = gui.flow_layout
        if flow_layout.count() == 0:
            return 0
        content_w = self.content_width(width)
        flow_layout.invalidate()
        return max(1, flow_layout.heightForWidth(content_w))

    def content_width(self, width: int | None = None) -> int:
        if width is not None and width > 0:
            return width
        gui = self.owner.gui
        viewport_w = gui.scroll_area.viewport().width()
        if viewport_w > 0:
            return viewport_w
        fallback = gui.scroll_area.width() - 2
        if fallback > 0:
            return fallback
        return max(1, gui.width() - 20)

    def vertical_overlay_width(self) -> int:
        delegate = getattr(self.owner.gui.scroll_area, "scrollDelagate", None)
        if delegate is None:
            return 0
        scroll_bar = getattr(delegate, "vScrollBar", None)
        if scroll_bar is None:
            return 0
        return max(0, scroll_bar.width() + 1)


class ExpandPanelController(QObject):
    def __init__(
        self,
        owner: "TaskProgressManager",
        layout: TaskPanelLayoutController,
        display: TaskPanelDisplayController,
    ):
        super().__init__()
        self.owner = owner
        self.layout = layout
        self.display = display
        self.expand_btn = None
        self.orchestrator = None
        self._transitioning = False

    def bind(self, expand_btn):
        gui = self.owner.gui
        self.expand_btn = expand_btn
        self.orchestrator = ExpandCollapseOrchestrator(
            window_target=gui,
            content_targets=[
                ContentTarget(
                    widget=gui.scroll_area,
                    measure_height=lambda _widget: self._panel_target_height(),
                )
            ],
            window_target_height_getter=self._window_target_height,
            can_expand_window=self._can_expand_window,
            before_expand=self._before_expand,
            after_expand=self._after_expand,
            after_collapse=self._after_collapse,
        )
        self._transitioning = False

    def cleanup(self):
        if self.orchestrator is not None:
            self.orchestrator.cleanup()
            self.orchestrator = None
        self._transitioning = False

    def stop_and_reset(self):
        gui = self.owner.gui
        self._transitioning = False
        if self.orchestrator is not None:
            self.orchestrator.stop()
            self.orchestrator.set_content_height(gui.scroll_area, 0)

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
        def finish_transition():
            self._transitioning = False
        if not transition(finish_transition):
            finish_transition()

    def _available_screen_height(self) -> int:
        gui = self.owner.gui
        window_handle = gui.windowHandle()
        screen = window_handle.screen() if window_handle is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry().height() if screen is not None else gui.maximumHeight()

    def _layout_overhead(self) -> int:
        gui = self.owner.gui
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
        gui = self.owner.gui
        max_window = min(gui.maximumHeight(), self._available_screen_height())
        show_area_min = max(gui.showArea.minimumHeight(), gui.showArea.minimumSizeHint().height())
        available = max(0, max_window - self._layout_overhead() - show_area_min)
        return self.layout.panel_target_height(available)

    def _can_expand_window(self, panel_h: int) -> bool:
        gui = self.owner.gui
        return panel_h > 0 and gui.height() < min(
            gui.maximumHeight(), self._available_screen_height()
        )

    def _window_target_height(self, total_expand_delta: int) -> int:
        gui = self.owner.gui
        return min(
            gui.height() + total_expand_delta + 5,
            gui.maximumHeight(),
            self._available_screen_height(),
        )

    def _before_expand(self):
        self.owner.gui.scroll_area.setVisible(True)

    def _after_expand(self):
        self.display.request_refresh(stick_to_bottom=True)

    def _after_collapse(self):
        self.display.hide_panel()


class TaskRepairActionController(QObject):
    def __init__(self, owner: "TaskProgressManager"):
        super().__init__()
        self.owner = owner
        self.button = None
        self._visible = None

    def bind(self, button):
        self.button = button
        self._visible = None
        self.button.clicked.connect(self.submit_repairable_tasks)

    def repairable_task_ids(self) -> list[str]:
        dl_mgr = getattr(self.owner.gui, "dl_mgr", None)
        running_ids = dl_mgr.get_running_task_ids() if dl_mgr is not None else set()
        return [
            task_id for task_id, entry in self.owner._entries.items()
            if task_id not in running_ids and not entry.progress.completed
        ]

    def sync(self):
        if self.button is None:
            return
        visible = bool(self.repairable_task_ids())
        if visible == self._visible:
            return
        self._visible = visible
        self.button.setVisible(visible)
        self.button.setEnabled(visible)

    def submit_repairable_tasks(self):
        task_ids = self.repairable_task_ids()
        if not task_ids:
            return
        self.owner.drop_entries(task_ids)
        self.owner.sync_progress_badge()
        self.owner.sync_toolbar_state()
        self.owner.display_ctrl.request_refresh()
        for task_id in task_ids:
            self.owner.gui.dl_mgr.resubmit_download(task_id)


class TaskProgressManager:
    PANEL_MIN_HEIGHT = 130

    def __init__(self, gui):
        self.gui = gui
        self._entries: t.Dict[str, TaskProgressEntry] = {}
        self.record_sql = SqlRecorder()
        self.cover_task_mgr = AsyncTaskManager(gui)
        self.expandBtn = None
        self.clearBtn = None
        self._dl_status_badge = None
        self.layout_ctrl = TaskPanelLayoutController(self)
        self.display_ctrl = TaskPanelDisplayController(self, self.layout_ctrl)
        self.animation_ctrl = ExpandPanelController(self, self.layout_ctrl, self.display_ctrl)
        self.repair_action = TaskRepairActionController(self)
        self._total_tasks = 0
        self._total_downloaded = 0
        self._completed_entries = 0
        self._toolbar_visible = None
        self._badge_state = None
        self._aggregate_percent = None

    def _reset_cached_state(self):
        self._total_tasks = 0
        self._total_downloaded = 0
        self._completed_entries = 0
        self._toolbar_visible = None
        self._badge_state = None
        self._aggregate_percent = None

    def sync_toolbar_state(self):
        visible = bool(self._entries)
        if visible != self._toolbar_visible:
            self._toolbar_visible = visible
            if self.expandBtn is not None:
                self.expandBtn.setVisible(visible)
            if self.clearBtn is not None:
                self.clearBtn.setVisible(visible)
        self.repair_action.sync()

    def _dispose_views(self, reset_view_ref: bool = False):
        layout = getattr(self.gui, "flow_layout", None)
        if layout is not None:
            while layout.count():
                layout.takeAt(0)
        for entry in self._entries.values():
            entry.dispose_view(reset_view_ref=reset_view_ref)

    def _on_clear_btn_clicked(self):
        accept_btn = PrimaryToolButton(FIF.ACCEPT)
        tip = CustomTeachingTip.create(
            [accept_btn],
            target=self.gui.clearBtn,
            parent=self.gui.clearBtn,
            content="清空任务列表",
            tailPosition=TeachingTipTailPosition.RIGHT,
        )
        accept_btn.clicked.connect(self.zero_task_state)
        accept_btn.clicked.connect(tip.close)

    def drop_entry(self, task_id: str):
        def _unregister_entry(entry: TaskProgressEntry):
            self._total_tasks -= entry.progress.tasks_count
            self._total_downloaded -= entry.progress.downloaded
            if entry.progress.completed:
                self._completed_entries -= 1

        entry = self._entries.pop(task_id, None)
        if entry is None:
            return
        _unregister_entry(entry)
        if entry.view is not None:
            self.gui.flow_layout.removeWidget(entry.view)
        entry.dispose_view(reset_view_ref=True)

    def drop_entries(self, task_ids: list[str]):
        for task_id in task_ids:
            self.drop_entry(task_id)

    def sync_progress_badge(self):
        if self._dl_status_badge is None:
            return
        total = len(self._entries)
        if total == 0:
            self._badge_state = None
            self._dl_status_badge.hide()
            return
        badge_state = (self._completed_entries, total)
        if badge_state == self._badge_state:
            return
        self._badge_state = badge_state
        self._dl_status_badge.update_progress(*badge_state)
        self._dl_status_badge.show()

    def init_native_panel(self):
        self._dispose_views()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self.animation_ctrl.cleanup()
        self.display_ctrl.cleanup()

        self._entries.clear()
        self._reset_cached_state()

        self.expandBtn = self.gui.expandBtn
        self.clearBtn = self.gui.clearBtn
        self.expandBtn.clicked.connect(self.animation_ctrl.on_expand_clicked)
        self.clearBtn.clicked.connect(self._on_clear_btn_clicked)

        self._dl_status_badge = DlStatusBadge(self.gui, target=self.expandBtn)
        self._dl_status_badge.hide()
        self.display_ctrl.bind()
        self.animation_ctrl.bind(self.expandBtn)
        self.repair_action.bind(self.gui.repairBtn)
        self.sync_toolbar_state()

    def handle(self, task: t.Union[TasksObj, TaskObj]):
        def _register_entry(entry: TaskProgressEntry):
            self._total_tasks += entry.progress.tasks_count
            self._total_downloaded += entry.progress.downloaded
            if entry.progress.completed:
                self._completed_entries += 1

        if isinstance(task, TasksObj):
            entry = self._entries.get(task.taskid)
            if entry is None:
                entry = TaskProgressEntry(self, task)
                self._entries[task.taskid] = entry
                _register_entry(entry)
                entry.mount()
                browser = getattr(self.gui, "BrowserWindow", None)
                if browser is not None and browser.isVisible():
                    browser.show_task_added_toast(task.display_title)
                self.sync_toolbar_state()
                self.sync_progress_badge()
                self.display_ctrl.request_refresh(stick_to_bottom=True)
                return
            entry.replace_tasks_obj(task)
            self.display_ctrl.request_refresh()
            return

        if isinstance(task, TaskObj):
            entry = self._entries.get(task.taskid)
            if entry is None:
                print(f"{task.taskid}: {task.page}")
                return
            was_completed = entry.progress.completed
            layout_changed = entry.apply_task(task)
            self._total_downloaded += 1
            if not was_completed and entry.progress.completed:
                self._completed_entries += 1
                self.sync_progress_badge()
            if layout_changed:
                self.display_ctrl.request_refresh()
            aggregate = int(self._total_downloaded * 100 / self._total_tasks) if self._total_tasks else 0
            if aggregate != self._aggregate_percent:
                self._aggregate_percent = aggregate
                self.gui.processbar_load(aggregate)

    def handle_job_finished(self, task_id: str, *, success: bool, error: str | None = None):
        entry = self._entries.get(task_id)
        if entry is None:
            return
        was_completed = entry.progress.completed
        changed = entry.record_job_result(success=success, error=error)
        if was_completed and not entry.progress.completed:
            self._completed_entries -= 1
            self.sync_progress_badge()
        elif not was_completed and entry.progress.completed:
            self._completed_entries += 1
            self.sync_progress_badge()
        if changed:
            self.display_ctrl.request_refresh()

    def zero_task_state(self):
        completed_task_ids = [task_id for task_id, entry in self._entries.items() if entry.progress.completed]
        self.drop_entries(completed_task_ids)
        self._dispose_views()
        self._entries.clear()
        self._reset_cached_state()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
        self.sync_toolbar_state()
        self.animation_ctrl.stop_and_reset()
        self.display_ctrl.reset()
        self.display_ctrl.hide_panel()
        if self.expandBtn.expanded:
            self.expandBtn.expanded = False
            self.expandBtn._anim_ctrl.rotate_to(0.0)
        gc.collect()
        self.gui.progressBar.setValue(0)

    @property
    def unfinished_tasks(self):
        task_ids = list(self._entries.keys())
        downloaded_taskids = self.record_sql.batch_check_dupe(task_ids)
        un_taskids = set(task_ids) - set(downloaded_taskids)
        return [self._entries[taskid].tasks_obj for taskid in un_taskids]

    def close(self):
        self.cover_task_mgr.cleanup()
        self.animation_ctrl.cleanup()
        self.display_ctrl.cleanup()
        self._dispose_views(reset_view_ref=True)
        self._entries.clear()
        self._reset_cached_state()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self.record_sql.close()
