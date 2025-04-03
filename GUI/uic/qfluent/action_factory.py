#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import subprocess
import traceback
from PyQt5 import QtCore
from PyQt5.QtCore import QThread, pyqtSignal

from qfluentwidgets import InfoBar, InfoBarPosition

from assets import res
from utils import ori_path, conf
from deploy import curr_os
from deploy.update import create_desc, Proj
from GUI.uic.qfluent.components import (
    CustomInfoBar, CustomFlyout, IndeterminateBarFView, CustomMessageBox
)


class DescCreator:
    @staticmethod
    def run():
        desc_html = create_desc()
        curr_os.open_file(desc_html)


class ProjUpdateThread(QThread):
    checked_signal = pyqtSignal(object)
    update_signal = pyqtSignal()
    updated_signal = pyqtSignal(object)
    proj = None

    def __init__(self, conf_dia):
        super(ProjUpdateThread, self).__init__()
        self.conf_dia = conf_dia
        self.is_update_requested = False
        self.log = conf.cLog(name="GUI")

    def run(self):
        try:
            self.proj = Proj()
            self.proj.check()
            self.checked_signal.emit(self.proj)
            while not self.is_update_requested and not self.isInterruptionRequested():
                self.msleep(100)  # 休眠100毫秒，减少CPU使用
            if self.is_update_requested and not self.isInterruptionRequested():
                self.run_update()
        except Exception as e:
            self.log.exception(f"ProjCheckError: {e}")
            self.checked_signal.emit(traceback.format_exc())
        

    def request_update(self):
        self.is_update_requested = True

    def run_update(self):
        try:
            # ⚠️ danger！⚠️ -------------->
            self.proj.local_update()
            # <-------------- ⚠️ danger！⚠️
            self.updated_signal.emit(self.proj)
        except Exception as e:
            self.log.exception(f"ProjUpdateError: {e}")
            self.updated_signal.emit(traceback.format_exc())


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
                msg = self.res.updated_fail
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
            QtCore.QTimer.singleShot(reload_time, self.after_update)

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
                InfoBar.success(
                    title='', content=self.res.ver_local_latest,
                    orient=QtCore.Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
                    duration=7000, parent=self.conf_dia
                )
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
        QtCore.QTimer.singleShot(1000, self.gui.close)
