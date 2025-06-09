#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import subprocess
from PyQt5.QtCore import QTimer

from qfluentwidgets import InfoBarPosition

from assets import res
from utils import ori_path, conf
from deploy.update import Proj
from GUI.uic.qfluent.components import (
    CustomInfoBar, CustomFlyout, IndeterminateBarFView, CustomMessageBox
)


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
