"""
异步任务管理器 - 流程化耗时操作处理
提供类似微服务的便捷接入方式，支持 QThread 处理、回调和可视化状态提示
"""
from dataclasses import dataclass, field
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QThread, Signal
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
            if "progress_callback" in self.task_func.__code__.co_varnames:
                self.kwargs["progress_callback"] = self.emit_progress
            result = self.task_func(*self.args, **self.kwargs)
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

    def __init__(self, default_parent: Optional[QObject] = None):
        self._default_parent = default_parent
        self.tooltips: Dict[str, StateToolTip] = {}
        self._entries: Dict[str, _TooltipEntry] = {}

    def show(
        self,
        task_id: str,
        title: str,
        content: str,
        position: Optional[Tuple[int, int]] = None,
        parent: Optional[QObject] = None,
    ):
        tooltip_parent = parent or self._default_parent
        if tooltip_parent is None:
            return

        tooltip = StateToolTip(title, content, tooltip_parent)
        self.tooltips[task_id] = tooltip
        self._entries[task_id] = _TooltipEntry(
            tooltip=tooltip,
            parent=tooltip_parent,
            custom_position=position is not None,
        )

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
    def __init__(self, gui: Optional[QObject] = None):
        self._gui = gui
        self.infobars: List[InfoBar] = []

    def success(self, message: str):
        # 兼容旧行为：该开关存在，但当前 GUI 没有成功弹层设计。
        return None

    def warning(self, message: str):
        self._show(
            factory=InfoBar.warning,
            title="警告",
            content=message,
            duration=6000,
        )

    def info(self, message: str):
        self._show(
            factory=InfoBar.info,
            title="",
            content=message,
            duration=2000,
        )

    def error(self, message: str, show_popup: bool = True):
        self._log_error(message)
        if not show_popup:
            return
        self._show(
            factory=InfoBar.error,
            title="",
            content=self._clip_error(message),
            duration=-1,
        )

    def cleanup(self):
        for infobar in list(self.infobars):
            infobar.close()
        self.infobars.clear()

    def _show(self, factory: Callable[..., Optional[InfoBar]], title: str, content: str, duration: int):
        if self._gui is None:
            return None
        infobar = factory(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=self._gui,
        )
        if infobar is None:
            return None
        self.infobars.append(infobar)
        infobar.closedSignal.connect(lambda bar=infobar: self._cleanup_closed(bar))
        return infobar

    def _cleanup_closed(self, infobar: InfoBar):
        if infobar in self.infobars:
            self.infobars.remove(infobar)

    def _log_error(self, message: str):
        logger = getattr(self._gui, "log", None)
        if logger is not None:
            logger.error(message)

    @staticmethod
    def _clip_error(message: str) -> str:
        return summarize_error_message(message)


class AsyncTaskManager(QObject):
    """异步任务管理器 - 只负责任务入口、线程生命周期与结果分发"""

    def __init__(self, gui=None):
        super().__init__()
        self.gui = gui
        self.current_tasks: Dict[str, AsyncTaskThread] = {}
        self._tooltip_stack = TaskTooltipStack(gui)
        self._infobar_center = TaskInfoBarCenter(gui)
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
            thread.success_signal.connect(
                lambda result, tid=task_id, task_config=config: self._handle_success(tid, result, task_config)
            )
            thread.error_signal.connect(
                lambda error, tid=task_id, task_config=config: self._handle_error(tid, error, task_config)
            )
            thread.progress_signal.connect(
                lambda progress, tid=task_id, task_config=config: self._handle_progress(tid, progress, task_config)
            )
            if config.show_tooltip:
                self._tooltip_stack.show(
                    task_id,
                    config.tooltip_title,
                    config.tooltip_content,
                    config.tooltip_position,
                    config.tooltip_parent,
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
                task_func=task_func,
                success_callback=success_callback,
                error_callback=error_callback,
                progress_callback=progress_callback,
                tooltip_title=tooltip_title,
                tooltip_content=tooltip_content,
                show_success_info=show_success_info,
                show_error_info=show_error_info,
                success_message=success_message,
                auto_hide_tooltip=auto_hide_tooltip,
                show_tooltip=show_tooltip,
                tooltip_position=tooltip_position,
                tooltip_parent=tooltip_parent,
                args=args,
                kwargs=kwargs,
            ),
        )

    def cancel_task(self, task_id: str) -> bool:
        thread = self.current_tasks.get(task_id)
        if thread is None or not thread.isRunning():
            return False

        thread.cancel()
        self._tooltip_stack.complete(task_id, auto_hide=True)
        self._infobar_center.info("任务已取消")
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
        self.cancel_all_tasks()
        self._tooltip_stack.cleanup()
        self._infobar_center.cleanup()
        self.current_tasks.clear()
        self._active = True

    def _handle_success(self, task_id: str, result: Any, config: TaskConfig):
        if not self._active:
            self._cleanup_task(task_id)
            return

        self._tooltip_stack.complete(task_id, config.auto_hide_tooltip)
        if config.show_success_info:
            self._infobar_center.success(config.success_message)

        callback_error = self._invoke_callback(config.success_callback, result, "成功")
        if callback_error is not None:
            self._infobar_center.error(callback_error)

        self._cleanup_task(task_id)

    def _handle_error(self, task_id: str, error: str, config: TaskConfig):
        if not self._active:
            self._cleanup_task(task_id)
            return

        self._tooltip_stack.complete(task_id, auto_hide=True)
        self._infobar_center.error(error, show_popup=config.show_error_info)

        callback_error = self._invoke_callback(config.error_callback, error, "错误")
        if callback_error is not None:
            self._infobar_center.error(callback_error)

        self._cleanup_task(task_id)

    def _handle_progress(self, task_id: str, progress: str, config: TaskConfig):
        if not self._active:
            return

        self._tooltip_stack.update(task_id, progress)
        callback_error = self._invoke_callback(config.progress_callback, progress, "进度")
        if callback_error is not None:
            self._infobar_center.error(callback_error)

    @staticmethod
    def _invoke_callback(callback: Optional[Callable], payload: Any, stage: str) -> Optional[str]:
        if callback is None:
            return None
        try:
            callback(payload)
        except Exception as exc:
            return f"{stage}回调执行失败: {exc}\n{traceback.format_exc()}"
        return None

    def _cleanup_task(self, task_id: str):
        thread = self.current_tasks.get(task_id)
        if thread is not None and not thread.isRunning():
            del self.current_tasks[task_id]
