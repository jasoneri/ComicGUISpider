import pathlib
import subprocess
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication, QFileDialog, QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, PrimaryToolButton, TransparentToolButton, 
    FluentIcon as FIF, PushSettingCard
)
from qframelesswindow import FramelessWindow

from assets import res
from utils import curr_os, conf


class SvPathCard(PushSettingCard):
    def __init__(self, parent=None):
        super().__init__(res.GUI.Uic.rv_scriptp_desc_tip, FIF.DOCUMENT, 
                         res.GUI.Uic.rv_scriptp_desc, "", parent)
        self.clicked.connect(self._onSelectFolder)

    def _onSelectFolder(self):
        file, _ = QFileDialog.getOpenFileName(self, res.GUI.Uic.sv_path_desc_tip, "",
            "Script Files (*.ps1 *.sh)")
        if file:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read(700)
                if ",' ,'/ /|" in content:
                    self.setContent(file)
                    conf.update(rv_script=file)
                else:
                    ...


class rvTool(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        window_width = int(screen_geo.width() * 0.4)
        window_height = int(screen_geo.height() * 0.1)
        self.setMinimumSize(window_width, window_height)
        self.resize(window_width, window_height)
        self.move(
            int((screen_geo.width() - window_width) / 2),
            int((screen_geo.height() - window_height) / 2)
        )
        
        self.init_ui()
    
    def init_ui(self):
        main_layout = VBoxLayout(self)
        
        first_row = QHBoxLayout()
        self.sv_path_card = SvPathCard(self)
        self.sv_path_card.setContent(str(getattr(conf, "rv_script")))
        first_row.addWidget(self.sv_path_card)
        
        self.runBtn = PrimaryToolButton(FIF.PLAY, self)
        self.runBtn.clicked.connect(self.run)
        self.cancelBtn = TransparentToolButton(FIF.CLOSE, self)
        self.cancelBtn.clicked.connect(self.close)
        first_row.addWidget(self.runBtn)
        first_row.addWidget(self.cancelBtn)
        
        main_layout.addLayout(first_row)
        
    def run(self):
        rv_script = pathlib.Path(getattr(conf, "rv_script"))
        run_dir = rv_script.parent
        if curr_os.shell == 'powershell':
            cmd = ["cmd.exe", "/c",
            "start", "/B", 'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', f'{str(rv_script)}']
        else:
            cmd = [curr_os.shell, str(rv_script)]
        subprocess.Popen(cmd, cwd=str(run_dir), start_new_session=True, shell=True, 
                         creationflags=0x00000008 | 0x00000200)
        self.close()


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication([])
    window = rvTool()
    window.show()
    app.exec_()
