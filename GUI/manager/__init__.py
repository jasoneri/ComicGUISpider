import os
import subprocess
import typing as t

from PyQt5.QtCore import QTimer
from qfluentwidgets import (
    InfoBarPosition, StateToolTip
)

from assets import res
from variables import PYPI_SOURCE
from deploy.update import Proj
from utils import conf, env, uv_exc, exc_p, TaskObj, TasksObj
from utils.processed_class import PreviewHtml
from utils.sql import SqlRecorder
from GUI.uic.qfluent.components import (
    CustomInfoBar, UpdaterMessageBox
)
from GUI.manager.async_task import AsyncTaskManager, TaskConfig
from GUI.manager.clip import ClipGUIManager
from GUI.manager.ags import AggrSearchManager
from GUI.manager.rv import RVManager

__all__ = [
    'TaskProgressManager',
    'Updater',
    'AsyncTaskManager',
    'TaskConfig',
    'ClipGUIManager',
    'AggrSearchManager',
    'RVManager',
]


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


class Updater:
    res = res.Updater
    proj = None
    version = None
    stateTooltip = None
    changelog_url = 'https://doc.comicguispider.nyc.mn/changelog/history'
    
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
            CustomInfoBar.show("", self.res.to_update, 
                self.gui.textBrowser, self.proj.update_info.get("html_url"), 
                f"""<{ver}>""", _type="SUCCESS")
            _close_thread()
            QTimer.singleShot(4000, lambda: self.to_update(ver))

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
                self.gui.update_dialog.show_release_note(recv.update_info.get("body", ""))
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

    def to_update(self, ver):
        _UpdateLauncher(ver).run()
        self.gui.close()


class _UpdateLauncher:
    def __init__(self, ver: str):
        self.ver = ver
        self.install_spec = f"ComicGUISpider=={ver}"
        self.index_url = PYPI_SOURCE[conf.pypi_source]
        self.log_path = exc_p / "cgs_update.log"
        self.installer_exe = exc_p / "runtime" / "installer.exe"

    def run(self):
        if os.name == "nt" and self.installer_exe.exists():
            self._run_installer()
            return
        if os.name == "nt":
            self._run_windows_fallback()
            return
        self._run_posix_fallback()

    def _run_installer(self):
        args = [
            str(self.installer_exe),
            "--version", self.ver,
            "--uv-exc", uv_exc,
            "--index-url", self.index_url,
            "--parent-pid", str(os.getpid()),
        ]
        for key in ("UV_TOOL_DIR", "UV_TOOL_BIN_DIR"):
            value = os.environ.get(key)
            if value:
                args.extend([f"--{key.lower().replace('_', '-')}", value])
        subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE, env=env)

    def _run_windows_fallback(self):
        ps1_path = exc_p / "updater.ps1"
        script = r"""param(
    [Parameter(Mandatory = $true)][string]$UvExe,
    [Parameter(Mandatory = $true)][string]$InstallSpec,
    [Parameter(Mandatory = $true)][string]$IndexUrl,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [string]$UvToolDir = "",
    [string]$UvToolBinDir = ""
)

if ($UvToolDir) { $env:UV_TOOL_DIR = $UvToolDir }
if ($UvToolBinDir) { $env:UV_TOOL_BIN_DIR = $UvToolBinDir }

& $UvExe tool install $InstallSpec --force --index-url $IndexUrl 2>&1 |
    Tee-Object -FilePath $LogPath

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nUpdate failed (exit code: $LASTEXITCODE)" -ForegroundColor Red
}

Read-Host "Press Enter to close"
"""
        self._write(ps1_path, script)
        subprocess.Popen(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit",
                "-File", str(ps1_path),
                "-UvExe", uv_exc,
                "-InstallSpec", self.install_spec,
                "-IndexUrl", self.index_url,
                "-LogPath", str(self.log_path),
                "-UvToolDir", os.environ.get("UV_TOOL_DIR", ""),
                "-UvToolBinDir", os.environ.get("UV_TOOL_BIN_DIR", ""),
            ],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            env=env,
        )

    def _run_posix_fallback(self):
        sh_path = exc_p / "updater.sh"
        script = """#!/bin/sh
uv_exe="$1"
install_spec="$2"
index_url="$3"
log_path="$4"

"$uv_exe" tool install "$install_spec" --force --index-url "$index_url" 2>&1 | tee -a "$log_path"
echo "done"
printf "Press any key to close..."
stty -icanon -echo
dd bs=1 count=1 >/dev/null 2>&1
stty icanon echo
"""
        self._write(sh_path, script)
        os.chmod(sh_path, 0o755)
        subprocess.Popen(
            ["setsid", "sh", str(sh_path), uv_exc, self.install_spec, self.index_url, str(self.log_path)],
            start_new_session=True,
            env=env,
        )

    @staticmethod
    def _write(path, content: str):
        path.write_text(content, encoding="utf-8")
