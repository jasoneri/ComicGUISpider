
import typing as t

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtGui import QGuiApplication
from qfluentwidgets import (
    ProgressBar, VBoxLayout, PrimaryToolButton,
    FluentIcon as FIF, TeachingTipTailPosition
)

from GUI.core.anim import ExpandCollapseOrchestrator, ContentTarget
from GUI.uic.qfluent.components import DlStatusBadge, CustomTeachingTip
from utils import conf, TaskObj, TasksObj
from utils.processed_class import PreviewHtml
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
    

    def apply(self, event: TaskObj) -> int:
        """接收一个下载事件，更新进度，返回百分比"""
        self.tasks_obj.downloaded.append(event)
        self._downloaded_count += 1
        self.last_percent = int(self._downloaded_count / self.tasks_obj.tasks_count * 100)
        if self.last_percent >= 100:
            self.completed = True
        return self.last_percent


class ProgressClass:
    def __init__(self, taskid:str, tasks_count: int, parent: QWidget, task_name: str=None):
        self.taskid = taskid
        self.tasks_count = tasks_count
        self.is_completed = False
        self._last_percent = 0
        self._make_task_widget(task_name or taskid, parent)

    def _make_task_widget(self, task_name: str, parent: QWidget):
        w = QWidget(parent)
        w.setMinimumHeight(35)
        w.setMaximumHeight(40)
        layout = VBoxLayout(w)
        layout.setContentsMargins(8, 4, 8, 4)
        row = QHBoxLayout()
        self.title_label = QLabel(task_name, w)
        self.progress_bar = ProgressBar(w)
        row.addWidget(self.title_label)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.progress_bar)
        self.widget = w

    def set_progress(self, percent: int):
        self._last_percent = percent
        self.progress_bar.setValue(percent)

    def mark_completed(self):
        self.is_completed = True
        self.progress_bar.setCustomBarColor(light="#00ff00", dark="#00cc00")

    def dispose(self):
        self.widget.deleteLater()


class TaskProgressEntry:
    """聚合：数据模型 + Native UI 视图"""
    __slots__ = ('progress', 'view')

    def __init__(self, progress: TaskProgress, view: t.Optional[ProgressClass] = None):
        self.progress = progress
        self.view = view


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
    PANEL_MAX_HEIGHT = 450

    def __init__(self, gui):
        self.gui = gui
        self._entries: t.Dict[str, TaskProgressEntry] = {}
        self.init_flag = True
        self.record_sql = SqlRecorder()
        self._init_lock = False
        self._pending_tasks = []
        self.expandBtn = None
        self._dl_status_badge = None
        self._expand_orchestrator = None
        self._transitioning = False

    def _on_clear_btn_clicked(self):
        teachtip(self.gui.clearBtn, self.zero_task_state)

    def init_native_panel(self):
        for entry in self._entries.values():
            if entry.view:
                entry.view.dispose()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        if self._expand_orchestrator is not None:
            self._expand_orchestrator.cleanup()
            self._expand_orchestrator = None

        self._entries.clear()
        self._pending_tasks.clear()
        self._init_lock = False
        self.init_flag = True

        self.expandBtn = self.gui.expandBtn
        self.clearBtn = self.gui.clearBtn
        self.expandBtn.clicked.connect(self._on_expand_clicked)
        self.gui.clearBtn.clicked.connect(self._on_clear_btn_clicked)

        self._dl_status_badge = DlStatusBadge(parent=self.gui, target=self.expandBtn)
        self._dl_status_badge.hide()

        self._expand_orchestrator = self._create_expand_orchestrator()
        self._transitioning = False

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
        self._expand_orchestrator = self._create_expand_orchestrator()
        self._transitioning = False

        self._rebuild_native_views(task_ids)
        self.gui.scroll_area.setVisible(False)
        self._expand_orchestrator.set_content_height(self.gui.scroll_area, 0)
        self._refresh_dl_status_badge()

    def _dispose_native_runtime_only(self):
        for entry in self._entries.values():
            if entry.view:
                entry.view.dispose()
                entry.view = None
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        if self._expand_orchestrator is not None:
            self._expand_orchestrator.cleanup()
            self._expand_orchestrator = None

    def _bind_native_signals_once(self):
        self.expandBtn.clicked.connect(self._on_expand_clicked)
        self.clearBtn.clicked.connect(self._on_clear_btn_clicked)

    def _create_expand_orchestrator(self):
        return ExpandCollapseOrchestrator(
            window_target=self.gui,
            content_targets=[
                ContentTarget(widget=self.gui.scroll_area,
                    measure_height=lambda _widget: self._panel_target_height(),
                )
            ],
            window_target_height_getter=self._window_target_height,
            can_expand_window=self._can_expand_window,
            after_collapse=self._sync_scroll_visibility,
        )

    def _rebuild_native_views(self, task_ids=None):
        order = task_ids if task_ids is not None else list(self._entries.keys())
        for tid in order:
            entry = self._entries.get(tid)
            if entry is None:
                continue
            pc = ProgressClass(entry.progress.taskid, entry.progress.tasks_count, self.gui.scroll_content, entry.progress.name)
            self.gui.task_list_layout.addWidget(pc.widget)
            pc.set_progress(entry.progress.last_percent)
            if entry.progress.completed:
                pc.mark_completed()
            entry.view = pc
        has_entries = len(self._entries) > 0
        self.expandBtn.setVisible(has_entries)
        self.clearBtn.setVisible(has_entries)

    def _available_screen_height(self) -> int:
        window_handle = self.gui.windowHandle()
        screen = window_handle.screen() if window_handle is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry().height() if screen is not None else self.gui.maximumHeight()

    def _panel_target_height(self) -> int:
        scroll_h = self.gui.scroll_area.sizeHint().height()
        return max(self.PANEL_MIN_HEIGHT, min(scroll_h, self.PANEL_MAX_HEIGHT))

    def _can_expand_window(self, panel_h: int) -> bool:
        if panel_h <= 0:
            return False
        max_by_window = self.gui.maximumHeight()
        max_by_screen = self._available_screen_height()
        return self.gui.height() < min(max_by_window, max_by_screen)

    def _window_target_height(self, total_expand_delta: int) -> int:
        return min(
            self.gui.height() + total_expand_delta + 5,
            self.gui.maximumHeight(),
            self._available_screen_height(),
        )

    def _sync_scroll_visibility(self):
        self.gui.scroll_area.setVisible(self.expandBtn.expanded)

    def _finish_transition(self):
        self._transitioning = False

    def _start_expand(self):
        if self._expand_orchestrator:
            if not self._expand_orchestrator.expand(self._finish_transition):
                self._finish_transition()
        else:
            self._finish_transition()

    def _start_collapse(self):
        if self._expand_orchestrator:
            if not self._expand_orchestrator.collapse(self._finish_transition):
                self._finish_transition()
        else:
            self._finish_transition()

    def _on_expand_clicked(self):
        if self._transitioning or (self._expand_orchestrator and self._expand_orchestrator.is_transitioning):
            return
        self._transitioning = True
        self.expandBtn.expand()
        if self.expandBtn.expanded:
            self._start_expand()
        else:
            self._start_collapse()

    def init(self):
        self.init_flag = False
        if not self.gui.BrowserWindow and self.gui.previewInit:
            self.gui.tf = self.gui.tf or PreviewHtml().created_temp_html
            self.gui.previewInit = False
            self.gui.set_preview()

    def handle(self, task: t.Union[TasksObj, TaskObj]):
        if not getattr(self.gui, "BrowserWindow"):
            self.init()
        if self.gui.tf and not getattr(self.gui.tf, "tasks_progress_panel_flag"):
            if not self._init_lock:
                self._init_lock = True
                self.gui.BrowserWindow.init_tasks_progress_panel(
                    callback=self._process_pending_tasks
                )
            if isinstance(task, TasksObj):
                self._pending_tasks.append(task)
                self._add_task_native(task)
            return
        if isinstance(task, TasksObj):
            self.add_task(task)
        elif isinstance(task, TaskObj):
            if task.taskid not in self._entries:
                print(f"{task.taskid}: {task.page}")
            else:
                self.update_progress(task)

    def _process_pending_tasks(self):
        for task in self._pending_tasks:
            self.gui.BrowserWindow.add_task(task)
        self._pending_tasks.clear()

    def add_task(self, tasks_obj):
        self.gui.BrowserWindow.add_task(tasks_obj)
        self._add_task_native(tasks_obj)

    def _add_task_native(self, tasks_obj):
        if tasks_obj.taskid in self._entries:
            print(f"[TaskProgressManager] duplicate taskid: {tasks_obj.taskid}")
            return
        progress = TaskProgress(tasks_obj)
        pc = ProgressClass(progress.taskid, progress.tasks_count, self.gui.scroll_content, progress.name)
        self.gui.task_list_layout.addWidget(pc.widget)
        self._entries[tasks_obj.taskid] = TaskProgressEntry(progress=progress, view=pc)
        if len(self._entries) == 1:
            self.expandBtn.setVisible(True)
            self.clearBtn.setVisible(True)
        self._refresh_dl_status_badge()

    def update_progress(self, task_obj: TaskObj):
        taskid = task_obj.taskid
        entry = self._entries[taskid]
        was_completed = entry.progress.completed
        curr_progress = entry.progress.apply(task_obj)
        progress_completed = conf.isDeduplicate and (not was_completed and entry.progress.completed)
        self._update_progress_native(taskid, curr_progress)
        self.gui.BrowserWindow.update_progress(taskid, curr_progress,
            lambda: self.gui.BrowserWindow.tmp_sv_local() if progress_completed else lambda: None
        )

    def _update_progress_native(self, taskid: str, percent: int):
        entry = self._entries.get(taskid)
        if entry is None or entry.view is None:
            return
        pc = entry.view
        pc.set_progress(percent)
        if entry.progress.completed and not pc.is_completed:
            pc.mark_completed()
        self._refresh_dl_status_badge()
        completed = sum(1 for e in self._entries.values() if e.progress.completed)
        if completed == len(self._entries):
            ...

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
        for entry in self._entries.values():
            if entry.view:
                entry.view.dispose()
        self._entries.clear()
        self.expandBtn.setVisible(False)
        self.clearBtn.setVisible(False)
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
        self._transitioning = False
        if self._expand_orchestrator is not None:
            self._expand_orchestrator.stop()
            self._expand_orchestrator.set_content_height(self.gui.scroll_area, 0)
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
