import os
import shlex
import subprocess

from PyQt5.QtCore import QTimer
from qfluentwidgets import (
    InfoBarPosition, StateToolTip
)

from variables import PYPI_SOURCE
from utils.processed_class import (
    PreviewHtml, TaskObj, TasksObj
)
from utils.sql import SqlUtils
from utils import conf, ori_path, env, uv_exc, exc_p
from assets import res
from deploy.update import Proj
from GUI.uic.qfluent.components import (
    CustomInfoBar, UpdaterMessageBox
)
from GUI.manager.async_task import AsyncTaskManager, TaskConfig
from GUI.manager.clip import ClipGUIManager


class TaskProgressManager:
    def __init__(self, gui):
        self.gui = gui
        self._tasks = {}
        self.init_flag = True
        self.sql_handler = SqlUtils()

    def init(self, add_task):
        self.init_flag = False
        if not self.gui.BrowserWindow and self.gui.previewInit:
            self.gui.tf = self.gui.tf or PreviewHtml().created_temp_html
            self.gui.previewInit = False
            self.gui.set_preview()
        self.gui.BrowserWindow.init_task_panel(add_task)

    def handle(self, task):
        if isinstance(task, tuple):
            self.add_task(task)
        else:
            self.update_progress(task)
            
    def add_task(self, task_info: tuple):
        if self.init_flag:
            self.init(lambda: self._real_add_task(task_info))
        else:
            self._real_add_task(task_info)

    def _real_add_task(self, task_info: tuple):
        obj = TasksObj(*task_info)
        self._tasks[task_info[0]] = obj
        self.gui.BrowserWindow.add_task(obj)

    def update_progress(self, task_obj: TaskObj):
        taskid = task_obj.taskid
        progress_completed = False
        if taskid in self._tasks:
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
        downloaded_taskids = self.sql_handler.batch_check_dupe(_tasks_key)
        un_taskids = set(_tasks_key) - set(downloaded_taskids)
        return [self._tasks[taskid] for taskid in un_taskids]
        
    def close(self):
        self.sql_handler.close()


class Updater:
    res = res.Updater
    proj = None
    version = None
    stateTooltip = None
    
    def __init__(self, gui):
        self.gui = gui
        self.conf_dia = self.gui.conf_dia

    def run(self):
        def _close_thread():
            if self.conf_dia.puThread:
                self.conf_dia.puThread.quit()
                self.conf_dia.puThread.wait()

        def to_update(recv):
            try:
                self.gui.updaterStateTooltip.setContent("Finish..")
                self.gui.updaterStateTooltip.setState(True)
                self.gui.updaterStateTooltip = None
            except Exception:
                pass
            ver = recv.update_info.get("tag_name")
            log = str(conf.log_path.joinpath("update.log"))
            CustomInfoBar.show("", self.res.to_update % log, 
                self.gui.textBrowser, self.proj.update_info.get("html_url"), 
                f"""<{ver}>""", _type="SUCCESS")
            _close_thread()
            QTimer.singleShot(6000, lambda: self.to_update(ver, log))

        def checked(recv):
            try:
                self.stateTooltip.setState(True)
                self.stateTooltip = None
            except RuntimeError:
                pass
            if isinstance(recv, str):
                self.gui.textBrowser.append(recv)
                CustomInfoBar.show("", self.res.ver_check_fail, self.gui.textBrowser, 
                                   f"{Proj.url}/releases", "access releases", _type="ERROR")
                _close_thread()
                return
            self.proj = recv
            print(f"checked: {recv.update_flag}")
            if recv.update_flag == "local":
                CustomInfoBar.show("", self.res.ver_local_latest, 
                self.conf_dia, f"https://github.com/jasoneri/ComicGUISpider/releases/tag/{recv.local_ver}", 
                f"""updateInfo-<{recv.local_ver}> """, _type="SUCCESS",
                duration=7000, position=InfoBarPosition.BOTTOM_LEFT)
            else:
                match recv.update_flag:
                    case "stable":
                        title = f"📫{res.GUI.Uic.confDia_updateDialog_stable} ⭐️{recv.update_info.get('tag_name')}"
                    case "dev":
                        title = f"📫{res.GUI.Uic.confDia_updateDialog_dev} 🧪{recv.update_info.get('tag_name')}"
                    case _:
                        title = ""
                self.gui.update_dialog = UpdaterMessageBox(title, self.gui)
                self.gui.update_dialog.show_release_note(recv.update_info.get("body"))
        self.stateTooltip = StateToolTip("Checking..", "", self.conf_dia.cookiesEdit)
        self.stateTooltip.show()
        self.conf_dia.puThread.checked_signal.connect(checked)
        self.conf_dia.puThread.update_signal.connect(self.conf_dia.puThread.request_update)
        self.conf_dia.puThread.toupdate_signal.connect(to_update)
        self.conf_dia.puThread.start()

    def rerun(self):
        cmd = ["cgs"]
        subprocess.Popen(cmd, cwd=exc_p, env=env)
        QTimer.singleShot(1000, self.gui.close)

    def to_update(self, ver, log):
        cmd = f"{uv_exc} tool install ComicGUISpider=={ver} --force --index-url {PYPI_SOURCE[conf.pypi_source]}"
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "", "powershell", "-NoProfile", "-Command",
                            f"{cmd} 2>&1 | Tee-Object -FilePath {shlex.quote(log)} ; Read-Host 'Press Enter to close'"])
        else:
            full = f"""{cmd} 2>&1 | tee -a {shlex.quote(log)} ; echo 'done'; read -n1 -s -r -p 'Press any key to close...'"""
            subprocess.Popen(["setsid", "sh", "-c", full], start_new_session=True)
        self.gui.close()
