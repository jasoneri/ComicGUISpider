import sys
import subprocess
import pathlib

from PyQt5.QtCore import Qt, QTimer
from qfluentwidgets import (
    InfoBar, InfoBarPosition
)

from utils.processed_class import (
    PreviewHtml, TaskObj, TasksObj, ClipManager
)
from utils.sql import SqlUtils
from utils import conf, ori_path
from assets import res
from deploy.update import Proj
from GUI.uic.qfluent.components import (
    CustomInfoBar, CustomFlyout, IndeterminateBarFView, CustomMessageBox
)


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
    
    def __init__(self, gui):
        self.gui = gui
        self.conf_dia = self.gui.conf_dia

    def run(self):
        def _close_thread():
            if self.conf_dia.puThread:
                self.conf_dia.puThread.quit()
                self.conf_dia.puThread.wait()

        def updated(recv):
            try:
                self.gui.updating_fly.close()
            except RuntimeError:
                pass
            if isinstance(recv, str):
                self.gui.textBrowser.append(recv)
                msg = self.res.updated_fail % str(ori_path.joinpath("logs/GUI.log"))
                _type = "ERROR"
                reload_time = 10000
            else:
                msg = self.res.updated_success
                _type = "SUCCESS"
                reload_time = 5000
            CustomInfoBar.show("", msg, 
                self.gui.textBrowser, self.proj.update_info.get("html_url"), 
                f"""<{self.proj.update_info.get("tag_name")}>""", _type=_type)
            _close_thread()
            QTimer.singleShot(reload_time, self.after_update)

        def checked(recv):
            try:
                self.check_fly.close()
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
                self.gui.update_dialog = CustomMessageBox(title, self.gui)
                self.gui.update_dialog.show_release_note(recv.update_info.get("body"))
        self.check_fly = CustomFlyout.make(
            view=IndeterminateBarFView(self.conf_dia), 
            target=self.conf_dia, parent=self.conf_dia, calc_bottom=True
        )
        self.conf_dia.puThread.checked_signal.connect(checked)
        self.conf_dia.puThread.update_signal.connect(self.conf_dia.puThread.request_update)
        self.conf_dia.puThread.updated_signal.connect(updated)
        self.conf_dia.puThread.start()

    def after_update(self):
        subprocess.Popen([sys.executable, ori_path.joinpath("CGS.py")])
        QTimer.singleShot(1000, self.gui.close)


class ClipGUIManager:
    res = res.GUI.ClipGUIManager

    def __init__(self, gui, *args, **kwargs):
        super(ClipGUIManager, self).__init__(*args, **kwargs)
        self.gui = gui

    def read_clip(self):
        if self.gui.next_btn.text() != res.GUI.Uic.next_btnDefaultText:
            InfoBar.warning(
                title='Clip start error', content=res.GUI.Clip.process_warning,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=3500, parent=self.gui.textBrowser
            )
        elif not pathlib.Path(conf.clip_db).exists():
            CustomInfoBar.show(
                title='Clip-db not found', content=res.GUI.Clip.db_not_found_guide,
                parent=self.gui.textBrowser,
                url="https://jasoneri.github.io/ComicGUISpider/config/#剪贴板db-clip-db", url_name="Guide"
            )
            # https://jasoneri.github.io/ComicGUISpider/feature/#_4-1-%E8%AF%BB%E5%89%AA%E8%B4%B4%E6%9D%BF
        else:
            clip = ClipManager(conf.clip_db, f"{conf.clip_sql} limit {conf.clip_read_num}",
                               getattr(self.gui.spiderUtils, "book_url_regex"))
            tf, match_items = clip.main()
            if not match_items:
                self.gui.say(res.GUI.Clip.match_none % self.gui.spiderUtils.book_url_regex,
                             ignore_http=True)
            else:
                self.gui.init_clip_handle(tf, match_items)
