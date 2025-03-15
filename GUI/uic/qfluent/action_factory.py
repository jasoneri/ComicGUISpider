import sys
import re
import subprocess
from PyQt5 import QtCore, QtWidgets 
from PyQt5.QtCore import QThread, pyqtSignal

from qfluentwidgets import (
    InfoBar, InfoBarPosition, MessageBoxBase, TextBrowser,
    Flyout, FlyoutViewBase, FlyoutAnimationType, 
    IndeterminateProgressBar, SubtitleLabel
)

from assets import res
from utils import ori_path
from deploy.update import create_desc, regular_update, Proj, MarkdownConverter
from GUI.uic.qfluent.components import CustomInfoBar


class DescCreator:
    @staticmethod
    def run():
        desc_html = create_desc()
        subprocess.run(["start", "", f"{desc_html}"], shell=True, check=True)


class IndeterminateBarFView(FlyoutViewBase):
    def __init__(self, parent=None):
        super(IndeterminateBarFView, self).__init__(parent)
        self.barLayout = QtWidgets.QHBoxLayout(self)
        self.barLayout.setContentsMargins(8, 0, 8, 0)
        indeterminateBar = IndeterminateProgressBar(self, start=True)
        self.barLayout.addWidget(indeterminateBar)
        self.setFixedSize(int(parent.width()*0.9), 10)


class CustomMessageBox(MessageBoxBase):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.gui = parent
        self.yesButton.setText(Updater.res.update_ensure)
        self.textBrowser = TextBrowser(self)
        # self.textBrowser.setWordWrapMode(QtGui.QTextOption.NoWrap)  # 禁用自动换行
        self.textBrowser.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)  # 需要时显示水平滚动条
        if title:
            self.titleLabel = SubtitleLabel(title)
            self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.textBrowser)
        self.widget.setMinimumWidth(int(parent.width() * 0.8))

    def validate(self):
        isValid = True
        print(f"{isValid=}")
        self.gui.conf_dia.puThread.update_signal.emit()
        return isValid

    def show_release_note(self, note):
        def _format_note(note):
            note = note.split("\n---")[0]
            return re.sub(r'\s*\(\s*[0-9a-f]{40}.*\)', '', note)
        html_text = MarkdownConverter.convert_html(_format_note(note))
        self.textBrowser.setHtml(html_text)
        self.gui.conf_dia.hide()
        self.show()


class ProjUpdateThread(QThread):
    checked_signal = pyqtSignal(object)
    update_signal = pyqtSignal()
    updated_signal = pyqtSignal(object)
    proj = None

    def __init__(self, conf_dia):
        super(ProjUpdateThread, self).__init__()
        self.conf_dia = conf_dia

    def run(self):
        self.proj = Proj()
        self.proj.check()
        # self.msleep(2000)
        # import json
        # class Project:
        #     pass
        # self.proj = Project()
        # self.proj.update_flag = "dev"
        # with open(ori_path.joinpath('test/analyze/github/releases.json'), 'r', encoding='utf-8') as f:
        #     self.proj.update_info = json.load(f)[0]  # FIXME: 临时，commit前删除
        self.checked_signal.emit(self.proj)
        self.exec_()

    def run_update(self):
        if self.proj:
            print("开始更新操作...")
            # self.msleep(1500)
            # self.proj.update()
            self.updated_signal.emit(self.proj)
            print("更新完成")


class Updater:
    res = res.Updater
    proj = None
    version = None
    
    def __init__(self, gui):
        self.gui = gui
        self.conf_dia = self.gui.conf_dia

    def run(self):
        def updated(proj):
            CustomInfoBar.show("", "🚧更新动作部分尚未竣工，需前往release页面下载", 
                self.gui.textBrowser,
                proj.update_info.get("html_url"), proj.update_info.get("tag_name"), 
                _type="WARNING")
            if self.conf_dia.puThread:
                self.conf_dia.puThread.quit()
                self.conf_dia.puThread.wait()

        def checked(proj):
            fly.close()
            print(f"checked: {proj.update_flag}")
            if proj.update_flag == "local":
                InfoBar.success(
                    title='', content=self.res.ver_local_latest,
                    orient=QtCore.Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
                    duration=7000, parent=self.conf_dia
                )
            else:
                match proj.update_flag:
                    case "stable":
                        title = f"📫{res.GUI.Uic.confDia_updateDialog_stable} ⭐️{proj.update_info.get('tag_name')}"
                    case "dev":
                        title = f"📫{res.GUI.Uic.confDia_updateDialog_dev} 🧪{proj.update_info.get('tag_name')}"
                    case _:
                        title = ""
                self.gui.update_dialog = CustomMessageBox(title, self.gui)
                self.gui.update_dialog.show_release_note(proj.update_info.get("body"))
        fly = Flyout.make(
            view=IndeterminateBarFView(self.conf_dia), 
            target=self.conf_dia.descBtn.mapToGlobal(self.conf_dia.descBtn.rect().bottomLeft()), 
            parent=self.conf_dia, aniType=FlyoutAnimationType.PULL_UP,
        )
        self.conf_dia.puThread.checked_signal.connect(checked)
        self.conf_dia.puThread.update_signal.connect(self.conf_dia.puThread.run_update)
        self.conf_dia.puThread.updated_signal.connect(updated)
        self.conf_dia.puThread.start()

    def _update(self):
        # ⚠️ danger！⚠️ -------------->
        regular_update(self.version)
        # <-------------- ⚠️ danger！⚠️

    def after_update(self):
        subprocess.Popen([sys.executable, ori_path.joinpath("CGS.py")])
        QtCore.QTimer.singleShot(1000, self.gui.close)
