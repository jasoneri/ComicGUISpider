"""
异步任务管理器 - 流程化耗时操作处理
提供类似微服务的便捷接入方式，支持 QThread 处理、回调和可视化状态提示
"""
import asyncio
from dataclasses import dataclass, field
import inspect
import math
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QWidget
from GUI.core.timer import safe_single_shot
from qfluentwidgets import InfoBar, InfoBarPosition, StateToolTip


def summarize_error_message(message: object, *, max_length: int = 180) -> str:
    if isinstance(message, BaseException):
        detail = str(message).strip()
        text = f"{type(message).__name__}: {detail}" if detail else type(message).__name__
    else:
        text = str(message or "").strip()

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first_line = " ".join(first_line.split())
    if not first_line:
        first_line = "Unknown error"

    clipped = len(first_line) > max_length
    if clipped:
        first_line = first_line[: max_length - 3].rstrip() + "..."

    has_hidden_detail = clipped or len(text.splitlines()) > 1
    return f"{first_line}。详情见日志" if has_hidden_detail else first_line


class AsyncTaskProgressReporter:
    def __init__(self, emit: Callable[[str], None], *, throttle_seconds: float = 0.2, min_percent_step: int = 1):
        self._emit = emit
        self._throttle_seconds = throttle_seconds
        self._min_percent_step = min_percent_step
        self._label = ""
        self._bytes_downloaded = 0
        self._total_bytes: Optional[int] = None
        self._last_emit_at = 0.0
        self._last_percent = -1

    def __call__(self, message: str):
        self._emit(message)

    def download_reset(self, *, label: Optional[str] = None):
        self._label = label or self._label
        self._bytes_downloaded = 0
        self._total_bytes = None
        self._last_emit_at = 0.0
        self._last_percent = -1

    def download_start(self, *, label: str, total_bytes: Optional[int] = None):
        self.download_reset(label=label)
        self._total_bytes = total_bytes if total_bytes is not None and total_bytes > 0 else None
        if self._total_bytes is None:
            self._emit(f"{self._label} 0B")
            return
        self._emit(f"{self._label} 0% {self._format_ratio(0, self._total_bytes)}")

    def download_advance(self, chunk_size: int, *, label: Optional[str] = None, total_bytes: Optional[int] = None):
        if chunk_size < 0:
            raise ValueError("chunk_size must be >= 0")
        if label:
            self._label = label
        if total_bytes is not None:
            self._total_bytes = total_bytes if total_bytes > 0 else None
        self._bytes_downloaded += chunk_size
        now = time.monotonic()
        if self._total_bytes is None:
            if now - self._last_emit_at < self._throttle_seconds:
                return
            self._last_emit_at = now
            self._emit(f"{self._label} {self._format_bytes(self._bytes_downloaded)}")
            return

        percent = min(100, math.floor((self._bytes_downloaded * 100) / self._total_bytes))
        should_emit = percent >= self._last_percent + self._min_percent_step or now - self._last_emit_at >= self._throttle_seconds
        if not should_emit:
            return
        self._last_emit_at = now
        self._last_percent = percent
        self._emit(f"{self._label} {percent}% {self._format_ratio(self._bytes_downloaded, self._total_bytes)}")

    def download_finish(self, *, label: Optional[str] = None):
        if label:
            self._label = label
        if self._total_bytes is None:
            self._emit(f"{self._label} done {self._format_bytes(self._bytes_downloaded)}")
            return
        done_bytes = max(self._bytes_downloaded, self._total_bytes)
        self._emit(f"{self._label} done {self._format_bytes(done_bytes)}")

    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes}B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}K"
        return f"{size_bytes / 1024 / 1024:.1f}M"

    @classmethod
    def _format_ratio(cls, downloaded_bytes: int, total_bytes: int) -> str:
        if total_bytes < 1024:
            return f"{downloaded_bytes}/{total_bytes}B"
        if total_bytes < 1024 * 1024:
            return f"{downloaded_bytes / 1024:.1f}/{total_bytes / 1024:.1f}K"
        return f"{downloaded_bytes / 1024 / 1024:.1f}/{total_bytes / 1024 / 1024:.1f}M"


class AsyncTaskThread(QThread):
    success_signal = Signal(object)
    error_signal = Signal(str)
    progress_signal = Signal(str)

    def __init__(self, task_func: Callable, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = tuple(args)
        self.kwargs = dict(kwargs)
        self.is_cancelled = False

    def run(self):
        try:
            if self.is_cancelled:
                return
            code_obj = getattr(self.task_func, "__code__", None)
            if code_obj is not None and "progress_callback" in code_obj.co_varnames:
                self.kwargs["progress_callback"] = AsyncTaskProgressReporter(self.emit_progress)
            result = self.task_func(*self.args, **self.kwargs)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            if not self.is_cancelled:
                self.success_signal.emit(result)
        except Exception as exc:
            if not self.is_cancelled:
                self.error_signal.emit(f"任务执行 > {exc}\n{traceback.format_exc()}")

    def emit_progress(self, message: str):
        if not self.is_cancelled:
            self.progress_signal.emit(message)

    def cancel(self):
        self.is_cancelled = True
        self.quit()
        self.wait()


@dataclass(slots=True)
class TaskConfig:
    task_func: Callable[..., Any]
    success_callback: Optional[Callable[[Any], None]] = None
    error_callback: Optional[Callable[[str], None]] = None
    progress_callback: Optional[Callable[[str], None]] = None
    tooltip_title: str = "处理中..."
    tooltip_content: str = "请稍候"
    show_success_info: bool = True
    show_error_info: bool = True
    success_message: str = "操作完成"
    auto_hide_tooltip: bool = True
    show_tooltip: bool = True
    tooltip_position: Optional[Tuple[int, int]] = None
    tooltip_parent: Optional[QObject] = None
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)


class _TooltipEntry:
    __slots__ = ("tooltip", "parent", "custom_position")

    def __init__(self, tooltip: StateToolTip, parent: QObject, custom_position: bool):
        self.tooltip = tooltip
        self.parent = parent
        self.custom_position = custom_position


class TaskTooltipStack:
    TOOLTIP_VERTICAL_SPACING = 64
    TOOLTIP_TOP_MARGIN = 20
    TOOLTIP_RIGHT_MARGIN = 30
    CLOSE_DELAY_MS = 1000

    def __init__(self, default_parent: QWidget):
        self._default_parent = default_parent
        self.tooltips: Dict[str, StateToolTip] = {}
        self._entries: Dict[str, _TooltipEntry] = {}

    def show(self, task_id: str, title: str, content: str, position: Optional[Tuple[int, int]] = None, parent: Optional[QObject] = None):
        tooltip_parent = parent if parent is not None else self._default_parent

        tooltip = StateToolTip(title, content, tooltip_parent)
        self.tooltips[task_id] = tooltip
        self._entries[task_id] = _TooltipEntry(tooltip=tooltip, parent=tooltip_parent, custom_position=position is not None)

        if position is None:
            self._rearrange_parent(tooltip_parent)
        else:
            tooltip.move(position[0], position[1])

        tooltip.setState(False)
        tooltip.show()

    def update(self, task_id: str, content: str):
        tooltip = self.tooltips.get(task_id)
        if tooltip is not None:
            tooltip.setContent(content)

    def complete(self, task_id: str, auto_hide: bool):
        tooltip = self.tooltips.get(task_id)
        if tooltip is None:
            return
        if auto_hide:
            tooltip.setState(True)
            safe_single_shot(self.CLOSE_DELAY_MS, lambda tid=task_id: self.close(tid))
            return
        tooltip.setContent("任务已完成")

    def close(self, task_id: str):
        entry = self._entries.pop(task_id, None)
        tooltip = self.tooltips.pop(task_id, None)
        if tooltip is None:
            return

        tooltip.close()
        if entry is not None:
            self._rearrange_parent(entry.parent)

    def cleanup(self):
        for tooltip in list(self.tooltips.values()):
            tooltip.close()
        self.tooltips.clear()
        self._entries.clear()

    def _rearrange_parent(self, parent: QObject):
        auto_entries = [
            entry
            for entry in self._entries.values()
            if entry.parent is parent and not entry.custom_position
        ]
        for index, entry in enumerate(auto_entries):
            x = parent.width() - entry.tooltip.width() - self.TOOLTIP_RIGHT_MARGIN
            y = self.TOOLTIP_TOP_MARGIN + index * self.TOOLTIP_VERTICAL_SPACING
            entry.tooltip.move(x, y)


class TaskInfoBarCenter:
    def __init__(self, gui, parent: QWidget):
        self._gui = gui
        self._parent = parent
        self.infobars: List[InfoBar] = []

    def success(self, message: str):
        # 兼容旧行为：该开关存在，但当前 GUI 没有成功弹层设计。
        return None

    def warning(self, message: str):
        self._show(factory=InfoBar.warning, title="警告", content=message, duration=6000)

    def info(self, message: str):
        self._show(factory=InfoBar.info, title="", content=message, duration=2000)

    def error(self, message: str, show_popup: bool = True):
        self._gui.log.error(message)
        if not show_popup:
            return
        self._show(factory=InfoBar.error, title="", content=summarize_error_message(message), duration=-1)

    def cleanup(self):
        for infobar in list(self.infobars):
            infobar.close()
        self.infobars.clear()

    def _show(self, factory: Callable[..., Optional[InfoBar]], title: str, content: str, duration: int):
        infobar = factory(
            title=title, content=content, orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
            duration=duration, parent=self._parent,
        )
        if infobar is None:
            return None
        self.infobars.append(infobar)
        infobar.closedSignal.connect(lambda bar=infobar: self._cleanup_closed(bar))
        return infobar

    def _cleanup_closed(self, infobar: InfoBar):
        if infobar in self.infobars:
            self.infobars.remove(infobar)


class AsyncTaskManager(QObject):
    """异步任务管理器 - 只负责任务入口、线程生命周期与结果分发"""

    def __init__(self, gui, parent: QWidget):
        super().__init__(parent)
        self.current_tasks: Dict[str, AsyncTaskThread] = {}
        self._tooltip_stack = TaskTooltipStack(parent)
        self._infobar_center = TaskInfoBarCenter(gui, parent)
        self.current_tooltips = self._tooltip_stack.tooltips
        self.current_infobars = self._infobar_center.infobars
        self._active = True

    def execute_task(self, task_id: str, config: TaskConfig) -> bool:
        if self.is_task_running(task_id):
            self._infobar_center.warning(f"任务 '{task_id}' 正在运行中")
            return False

        try:
            thread = AsyncTaskThread(config.task_func, *config.args, **config.kwargs)
            self.current_tasks[task_id] = thread
            thread.success_signal.connect(lambda result, tid=task_id, task_config=config: self._handle_success(tid, result, task_config))
            thread.error_signal.connect(lambda error, tid=task_id, task_config=config: self._handle_error(tid, error, task_config))
            thread.progress_signal.connect(
                lambda progress, tid=task_id, task_config=config: self._handle_progress(tid, progress, task_config)
            )
            if config.show_tooltip:
                self._tooltip_stack.show(
                    task_id, config.tooltip_title, config.tooltip_content, config.tooltip_position, config.tooltip_parent
                )
            thread.start()
            return True
        except Exception as exc:
            self._infobar_center.error(f"启动任务失败: {exc}\n{traceback.format_exc()}")
            self.current_tasks.pop(task_id, None)
            return False

    def execute_simple_task(
        self,
        task_func: Callable[..., Any],
        success_callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        tooltip_title: str = "处理中...",
        tooltip_content: str = "请稍候",
        show_success_info: bool = True,
        show_error_info: bool = True,
        success_message: str = "操作完成",
        auto_hide_tooltip: bool = True,
        tooltip_position: Optional[Tuple[int, int]] = None,
        show_tooltip: bool = True,
        tooltip_parent: Optional[QObject] = None,
        task_id: Optional[str] = None,
        *args,
        **kwargs,
    ) -> bool:
        if task_id is None:
            task_id = f"task_{task_func.__name__}_{int(time.time() * 1000000)}"

        return self.execute_task(
            task_id,
            TaskConfig(
                task_func=task_func, success_callback=success_callback, error_callback=error_callback,
                progress_callback=progress_callback, tooltip_title=tooltip_title, tooltip_content=tooltip_content,
                show_success_info=show_success_info, show_error_info=show_error_info, success_message=success_message,
                auto_hide_tooltip=auto_hide_tooltip, show_tooltip=show_tooltip, tooltip_position=tooltip_position,
                tooltip_parent=tooltip_parent, args=args, kwargs=kwargs,
            ),
        )

    def cancel_task(self, task_id: str) -> bool:
        thread = self.current_tasks.get(task_id)
        if thread is None or not thread.isRunning():
            return False

        thread.cancel()
        self._tooltip_stack.complete(task_id, auto_hide=True)
        self._infobar_center.info("任务已取消")
        self._cleanup_task(task_id)
        return True

    def cancel_all_tasks(self):
        for task_id in list(self.current_tasks.keys()):
            self.cancel_task(task_id)

    def is_task_running(self, task_id: str) -> bool:
        thread = self.current_tasks.get(task_id)
        return bool(thread and thread.isRunning())

    def get_running_tasks(self) -> list:
        return [task_id for task_id, thread in self.current_tasks.items() if thread.isRunning()]

    def cleanup(self):
        self._active = False
        self.cancel_all_tasks()
        self._tooltip_stack.cleanup()
        self._infobar_center.cleanup()
        self.current_tasks.clear()

    def reset(self):
        self.cleanup()
        self._active = True

    def _handle_success(self, task_id: str, result: Any, config: TaskConfig):
        if not self._active:
            self._cleanup_task(task_id)
            return

        self._tooltip_stack.complete(task_id, config.auto_hide_tooltip)
        if config.show_success_info:
            self._infobar_center.success(config.success_message)
        try:
            if config.success_callback is not None:
                config.success_callback(result)
        finally:
            self._cleanup_task(task_id)

    def _handle_error(self, task_id: str, error: str, config: TaskConfig):
        if not self._active:
            self._cleanup_task(task_id)
            return

        self._tooltip_stack.complete(task_id, auto_hide=True)
        self._infobar_center.error(error, show_popup=config.show_error_info)
        try:
            if config.error_callback is not None:
                config.error_callback(error)
        finally:
            self._cleanup_task(task_id)

    def _handle_progress(self, task_id: str, progress: str, config: TaskConfig):
        if not self._active:
            return

        self._tooltip_stack.update(task_id, progress)
        if config.progress_callback is not None:
            config.progress_callback(progress)

    def _cleanup_task(self, task_id: str):
        thread = self.current_tasks.get(task_id)
        if thread is not None and not thread.isRunning():
            del self.current_tasks[task_id]
