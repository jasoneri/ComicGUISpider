
import typing as t
from utils import conf, TaskObj, TasksObj
from utils.processed_class import PreviewHtml
from utils.sql import SqlRecorder


class TaskProgressManager:
    def __init__(self, gui):
        self.gui = gui
        self._tasks = {}
        self.init_flag = True
        self.record_sql = SqlRecorder()
        self._init_lock = False
        self._pending_tasks = []

    def init(self):
        # 就是为了设定任务细化面板 包的饺子
        self.init_flag = False
        if not self.gui.BrowserWindow and self.gui.previewInit:  # 这是拷贝等无预览有章节时设的preview处理
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
            return
        if isinstance(task, TasksObj):
            self.add_task(task)
        elif isinstance(task, TaskObj):
            if task.taskid not in self._tasks:
                print(f"{task.taskid}: {task.page}")
            else:
                self.update_progress(task)  

    def _process_pending_tasks(self):
        for task in self._pending_tasks:
            self.add_task(task)
        self._pending_tasks.clear()

    def add_task(self, tasks_obj):
        self._tasks[tasks_obj.taskid] = tasks_obj
        self.gui.BrowserWindow.add_task(tasks_obj)

    def update_progress(self, task_obj: TaskObj):
        taskid = task_obj.taskid
        progress_completed = False
        _tasks = self._tasks[taskid]
        _tasks.downloaded.append(task_obj)
        curr_progress = int(len(_tasks.downloaded) / _tasks.tasks_count * 100)
        if conf.isDeduplicate and curr_progress >= 100:
            progress_completed = True
        self.gui.BrowserWindow.update_progress(taskid, curr_progress,
            lambda: self.gui.BrowserWindow.tmp_sv_local() if progress_completed else lambda: None
        )

    @property
    def unfinished_tasks(self):
        _tasks_key = list(self._tasks.keys())
        downloaded_taskids = self.record_sql.batch_check_dupe(_tasks_key)
        un_taskids = set(_tasks_key) - set(downloaded_taskids)
        return [self._tasks[taskid] for taskid in un_taskids]
        
    def close(self):
        self.record_sql.close()
