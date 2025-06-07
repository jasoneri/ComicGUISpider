import pathlib
import subprocess
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication,QSpacerItem,QSizePolicy, QFileDialog, QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, TransparentToolButton, 
    FluentIcon as FIF, PushSettingCard, InfoBar, InfoBarPosition
)
from qframelesswindow import FramelessWindow

from assets import res
from utils import curr_os, conf
from utils.redViewer_tools import combine_then_mv, show_max
from GUI.uic.qfluent import CustomFlyout, TableFlyoutView, CustomIcon, CustomInfoBar


class SvPathCard(PushSettingCard):
    def __init__(self, parent=None):
        super().__init__(res.GUI.Uic.rv_scriptp_desc_tip, FIF.DOCUMENT, 
                         res.GUI.Uic.rv_scriptp_desc, "", parent)
        self.rvtool = parent
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
                CustomInfoBar.show("", res.GUI.rvTool.set_script_err, self.rvtool, 
                "https://github.com/jasoneri/redViewer#%EF%B8%8F%E9%83%A8%E7%BD%B2%E6%9B%B4%E6%96%B0%E8%BF%90%E8%A1%8C%E5%A4%9A%E5%90%88%E4%B8%80%E8%84%9A%E6%9C%AC", 
                "rV script", _type="WARNING", position=InfoBarPosition.TOP)


class rvTool(FramelessWindow):
    res = res.GUI.rvTool
  
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        if parent:
            window_width = int(parent.width() * 0.8)
        else:
            window_width = int(screen_geo.width() * 0.4)
        window_height = int(screen_geo.height() * 0.12)
        self.setMinimumSize(window_width, window_height)
        self.resize(window_width, window_height)
        self.move(
            int((screen_geo.width() - window_width) / 2),
            int((screen_geo.height() - window_height) / 2)
        )
        
        self.init_ui()
    
    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        
        first_row = QHBoxLayout()
        self.sv_path_card = SvPathCard(self)
        self.sv_path_card.setContent(str(getattr(conf, "rv_script")))
        first_row.addWidget(self.sv_path_card)
        
        
        second_row = QHBoxLayout()
        spacer_info = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.showMaxBtn = PrimaryPushButton(CustomIcon.TOOL_BOOK_MARKED, self.res.book_marked)
        self.showMaxBtn.clicked.connect(self.show_max)
        self.combineBtn = PrimaryPushButton(CustomIcon.TOOL_MERGE, self.res.merge_move)
        self.combineBtn.clicked.connect(self.combine_then_mv)
        self.runBtn = PrimaryPushButton(FIF.PLAY, "run rV")
        self.runBtn.clicked.connect(self.run)
        self.cancelBtn = TransparentToolButton(FIF.CLOSE, self)
        self.cancelBtn.clicked.connect(self.close)
        second_row.addSpacerItem(spacer_info)
        second_row.addWidget(self.showMaxBtn)
        second_row.addWidget(self.combineBtn)
        second_row.addWidget(self.runBtn)
        second_row.addWidget(self.cancelBtn)

        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)
        
    def show_max(self):
        record_txt = conf.sv_path.joinpath("web_handle/record.txt")
        if record_txt.exists():
            CustomFlyout.make(
                TableFlyoutView(show_max(record_txt), self), 
                self.sv_path_card, self)
        else:
            InfoBar.warning(
                title='show_max', content=res.GUI.rvTool.book_marked_warning % record_txt,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
                duration=5000, parent=self
            )

    def combine_then_mv(self):
        done = combine_then_mv(conf.sv_path, conf.sv_path.joinpath("web"))
        InfoBar.success(
            title='combine_then_mv', content=res.GUI.rvTool.combined_tip % (done, conf.sv_path.joinpath("web")),
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=3000, parent=self
        )

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


if __name__ == '__main__':
    import GUI.src.material_ct
    main()
