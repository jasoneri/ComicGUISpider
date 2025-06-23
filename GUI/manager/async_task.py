"""
异步任务管理器 - 流程化耗时操作处理
提供类似微服务的便捷接入方式，支持QThread处理、回调和可视化状态提示
"""
import traceback
import time
from typing import Callable, Optional, Any, Dict
from PyQt5.QtCore import QThread, pyqtSignal, QObject
from qfluentwidgets import StateToolTip, InfoBar, InfoBarPosition
from PyQt5.QtCore import Qt


class AsyncTaskThread(QThread):
    success_signal = pyqtSignal(object)  # 成功信号，传递结果
    error_signal = pyqtSignal(str)       # 错误信号，传递错误信息
    progress_signal = pyqtSignal(str)    # 进度信号，传递进度信息
    
    def __init__(self, task_func: Callable, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self.is_cancelled = False
    
    def run(self):
        try:
            if self.is_cancelled:
                return
            # 如果任务函数接受progress_callback参数，传递进度回调
            if 'progress_callback' in self.task_func.__code__.co_varnames:
                self.kwargs['progress_callback'] = self.emit_progress
            result = self.task_func(*self.args, **self.kwargs)
            if not self.is_cancelled:
                self.success_signal.emit(result)
        except Exception as e:
            if not self.is_cancelled:
                error_msg = f"任务执行失败: {str(e)}\n{traceback.format_exc()}"
                self.error_signal.emit(error_msg)
    
    def emit_progress(self, message: str):
        """发射进度信号"""
        if not self.is_cancelled:
            self.progress_signal.emit(message)
    
    def cancel(self):
        self.is_cancelled = True
        self.quit()
        self.wait()


class TaskConfig:
    def __init__(self,
                 task_func: Callable,
                 success_callback: Optional[Callable] = None,
                 error_callback: Optional[Callable] = None,
                 progress_callback: Optional[Callable] = None,
                 tooltip_title: str = "处理中...",
                 tooltip_content: str = "请稍候",
                 show_success_info: bool = True,
                 show_error_info: bool = True,
                 success_message: str = "操作完成",
                 auto_hide_tooltip: bool = True,
                 tooltip_position: Optional[tuple] = None,  # (x, y) 或 None 使用默认位置
                 tooltip_parent: Optional[QObject] = None,  # 自定义 tooltip 父组件
                 *args, **kwargs):
        self.task_func = task_func
        self.success_callback = success_callback
        self.error_callback = error_callback
        self.progress_callback = progress_callback
        self.tooltip_title = tooltip_title
        self.tooltip_content = tooltip_content
        self.show_success_info = show_success_info
        self.show_error_info = show_error_info
        self.success_message = success_message
        self.auto_hide_tooltip = auto_hide_tooltip
        self.tooltip_position = tooltip_position
        self.tooltip_parent = tooltip_parent
        self.args = args
        self.kwargs = kwargs


class AsyncTaskManager(QObject):
    """异步任务管理器 - 流程化耗时操作处理"""

    def __init__(self, parent_widget=None):
        super().__init__()
        self.parent_widget = parent_widget
        self.current_tasks: Dict[str, AsyncTaskThread] = {}
        self.current_tooltips: Dict[str, StateToolTip] = {}
        self._tooltip_offset_counter = 0  # 用于计算tooltip位置偏移
    
    def execute_task(self, 
                    task_id: str,
                    config: TaskConfig) -> bool:
        """
        执行异步任务
        
        Args:
            task_id: 任务唯一标识
            config: 任务配置
            
        Returns:
            bool: 是否成功启动任务
        """
        # 检查是否已有同名任务在运行
        if task_id in self.current_tasks and self.current_tasks[task_id].isRunning():
            self._show_warning(f"任务 '{task_id}' 正在运行中")
            return False
        
        try:
            # 创建并启动任务线程
            thread = AsyncTaskThread(config.task_func, *config.args, **config.kwargs)
            self.current_tasks[task_id] = thread
            # 连接信号
            thread.success_signal.connect(
                lambda result: self._handle_success(task_id, result, config)
            )
            thread.error_signal.connect(
                lambda error: self._handle_error(task_id, error, config)
            )
            thread.progress_signal.connect(
                lambda progress: self._handle_progress(task_id, progress, config)
            )
            # 显示状态提示
            self._show_tooltip(task_id, config.tooltip_title, config.tooltip_content,
                             config.tooltip_position, config.tooltip_parent)
            # 启动线程
            thread.start()
            return True
        except Exception as e:
            self._show_error(f"启动任务失败: {str(e)}")
            return False
    
    def execute_simple_task(self,
                           task_func: Callable,
                           success_callback: Optional[Callable] = None,
                           error_callback: Optional[Callable] = None,
                           tooltip_title: str = "处理中...",
                           tooltip_position: Optional[tuple] = None,
                           tooltip_parent: Optional[QObject] = None,
                           task_id: Optional[str] = None,
                           *args, **kwargs) -> bool:
        """
        简化的任务执行接口

        Args:
            task_func: 要执行的函数
            success_callback: 成功回调
            error_callback: 错误回调
            tooltip_title: 提示标题
            tooltip_position: StateToolTip位置 (x, y)，None使用默认位置
            tooltip_parent: StateToolTip父组件，None使用默认父组件
            task_id: 任务ID，如果不提供则自动生成
            *args, **kwargs: 传递给task_func的参数

        Returns:
            bool: 是否成功启动任务
        """
        if task_id is None:
            # 使用时间戳和函数名生成唯一ID，避免重复
            task_id = f"task_{task_func.__name__}_{int(time.time() * 1000000)}"

        config = TaskConfig(
            task_func=task_func,
            success_callback=success_callback,
            error_callback=error_callback,
            tooltip_title=tooltip_title,
            tooltip_position=tooltip_position,
            tooltip_parent=tooltip_parent,
            *args, **kwargs
        )

        return self.execute_task(task_id, config)
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消指定任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消
        """
        if task_id in self.current_tasks:
            thread = self.current_tasks[task_id]
            if thread.isRunning():
                thread.cancel()
                self._hide_tooltip(task_id)
                self._show_info("任务已取消")
                return True
        return False
    
    def cancel_all_tasks(self):
        for task_id in list(self.current_tasks.keys()):
            self.cancel_task(task_id)
    
    def is_task_running(self, task_id: str) -> bool:
        return (task_id in self.current_tasks and 
                self.current_tasks[task_id].isRunning())
    
    def get_running_tasks(self) -> list:
        return [task_id for task_id, thread in self.current_tasks.items() 
                if thread.isRunning()]
    
    def _handle_success(self, task_id: str, result: Any, config: TaskConfig):
        # 隐藏状态提示
        if config.auto_hide_tooltip:
            self._hide_tooltip(task_id)
        else:
            self._update_tooltip(task_id, "完成", "任务已完成")
        # 显示成功信息
        if config.show_success_info:
            self._show_success(config.success_message)
        # 执行成功回调
        if config.success_callback:
            try:
                config.success_callback(result)
            except Exception as e:
                ...
        # 清理任务
        self._cleanup_task(task_id)
    
    def _handle_error(self, task_id: str, error: str, config: TaskConfig):
        # 隐藏状态提示
        self._hide_tooltip(task_id)
        # 显示错误信息
        if config.show_error_info:
            self._show_error(f"任务失败: {error}")
        # 执行错误回调
        if config.error_callback:
            try:
                config.error_callback(error)
            except Exception as e:
                self._show_error(f"错误回调执行失败: {str(e)}")
        # 清理任务
        self._cleanup_task(task_id)
    
    def _handle_progress(self, task_id: str, progress: str, config: TaskConfig):
        # 更新状态提示
        self._update_tooltip(task_id, config.tooltip_title, progress)
        # 执行进度回调
        if config.progress_callback:
            try:
                config.progress_callback(progress)
            except Exception as e:
                print(f"进度回调执行失败: {str(e)}")
    
    def _show_tooltip(self, task_id: str, title: str, content: str,
                     position: Optional[tuple] = None, parent: Optional[QObject] = None):
        """显示状态提示"""
        # 确定父组件
        tooltip_parent = parent or self.parent_widget
        if not tooltip_parent:
            return
        tooltip = StateToolTip(title, content, tooltip_parent)
        # 设置位置
        if position:
            # 使用自定义位置
            tooltip.move(position[0], position[1])
        else:
            # 计算智能位置，避免重叠
            x = tooltip_parent.width() - tooltip.width() - 30
            y = 20 + (self._tooltip_offset_counter * 80)  # 每个tooltip垂直间隔80像素
            tooltip.move(x, y)
            self._tooltip_offset_counter += 1
        tooltip.setState(False)  # 设置为加载状态
        tooltip.show()
        self.current_tooltips[task_id] = tooltip
    
    def _update_tooltip(self, task_id: str, title: str, content: str):
        if task_id in self.current_tooltips:
            tooltip = self.current_tooltips[task_id]
            tooltip.setContent(content)
    
    def _hide_tooltip(self, task_id: str):
        if task_id in self.current_tooltips:
            tooltip = self.current_tooltips[task_id]
            tooltip.setState(True)  # 设置为完成状态
            # 延迟删除tooltip
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(1000, lambda: self._cleanup_tooltip(task_id))
    
    def _cleanup_tooltip(self, task_id: str):
        if task_id in self.current_tooltips:
            tooltip = self.current_tooltips[task_id]
            tooltip.close()
            del self.current_tooltips[task_id]
            # 重新排列剩余的tooltip位置
            self._rearrange_tooltips()

    def _rearrange_tooltips(self):
        """重新排列剩余tooltip的位置，避免空隙"""
        if not self.current_tooltips or not self.parent_widget:
            self._tooltip_offset_counter = 0
            return

        # 按创建顺序重新排列tooltip位置
        for i, tooltip in enumerate(self.current_tooltips.values()):
            x = self.parent_widget.width() - tooltip.width() - 30
            y = 20 + (i * 80)  # 每个tooltip垂直间隔80像素
            tooltip.move(x, y)

        # 更新偏移计数器
        self._tooltip_offset_counter = len(self.current_tooltips)

    def _cleanup_task(self, task_id: str):
        if task_id in self.current_tasks:
            thread = self.current_tasks[task_id]
            if not thread.isRunning():
                del self.current_tasks[task_id]
    
    def _show_success(self, message: str):
        ...
    
    def _show_error(self, message: str):
        if self.parent_widget:
            InfoBar.error(
                title='错误', content=message,
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP,
                duration=-1, parent=self.parent_widget
            )
    
    def _show_warning(self, message: str):
        if self.parent_widget:
            InfoBar.warning(
                title='警告', content=message,
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP,
                duration=6000, parent=self.parent_widget
            )
    
    def _show_info(self, message: str):
        if self.parent_widget:
            InfoBar.info(
                title='', content=message,
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000, parent=self.parent_widget
            )
    
    def cleanup(self):
        self.cancel_all_tasks()
        for tooltip in self.current_tooltips.values():
            tooltip.close()
        self.current_tooltips.clear()
        self.current_tasks.clear()
        self._tooltip_offset_counter = 0  # 重置偏移计数器
