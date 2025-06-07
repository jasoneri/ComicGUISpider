import pathlib
import shutil
import subprocess
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication,QSpacerItem,QSizePolicy, QFileDialog, QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, TransparentToolButton, TransparentPushButton, 
    FluentIcon as FIF, PushSettingCard, InfoBar, InfoBarPosition
)
from qframelesswindow import FramelessWindow

from assets import res
from utils import curr_os, conf, yaml_update
from utils.redViewer_tools import combine_then_mv, show_max
from GUI.uic.qfluent import CustomFlyout, TableFlyoutView, CustomIcon, CustomInfoBar


class WinOS:
    file_type = ".ps1"
    script_file_type = "Script Files (*.ps1)"
    run_cmd = ["cmd.exe", "/c", "start", "/B", 'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    deploy_cmd = [curr_os.shell, "-Command", "irm https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/windows.ps1 | iex"]


class ElseOS:
    file_type = ".sh"
    script_file_type = "Script Files (*.sh)"
    run_cmd = [curr_os.shell]
    deploy_cmd = [curr_os.shell, "-c", "curl -fsSL https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/macos.sh | zsh"]


TmpCurrOs = WinOS if curr_os.shell == 'powershell' else ElseOS


class SvPathCard(PushSettingCard):
    def __init__(self, parent=None):
        super().__init__(res.GUI.Uic.rv_scriptp_desc_tip % TmpCurrOs.file_type, FIF.DOCUMENT, 
                         res.GUI.Uic.rv_scriptp_desc, "", parent)
        self.rvtool = parent
        self.clicked.connect(self._onSelectScript)

    def setContent(self, content: str):
        super().setContent(content)
        if hasattr(self.rvtool, 'runBtn'):
            self.rvtool.runBtn.setEnabled(bool(content and content != "."))

    def _onSelectScript(self):
        file, _ = QFileDialog.getOpenFileName(self, res.GUI.Uic.sv_path_desc_tip, "", TmpCurrOs.script_file_type)
        if file:
            file = pathlib.Path(file)
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read(700)
            if not ",' ,'/ /|" in content:
                self.ask_deploy()
                return
            self.setContent(str(file))
            conf.update(rv_script=str(file))
            # 将 CGS 的存储目录同步到 rV 里
            rv_conf = file.parent.joinpath(r"redViewer/backend/conf.yml")
            if not rv_conf.exists():
                shutil.move(file.parent.joinpath(r"redViewer/backend/utils/conf_sample.yml"), rv_conf)
            yaml_update(rv_conf, {"path": str(conf.sv_path)})
        if not self.contentLabel.text() or self.contentLabel.text() == ".":
            self.ask_deploy()
    
    def ask_deploy(self):
        def deploy():
            run_dir = QFileDialog.getExistingDirectory(self, res.GUI.Uic.sv_path_desc_tip)
            if run_dir:
                subprocess.Popen(TmpCurrOs.deploy_cmd, cwd=str(run_dir), start_new_session=True, shell=True, 
                                creationflags=0x00000008 | 0x00000200)
        btn = PrimaryPushButton(FIF.COMMAND_PROMPT, res.GUI.Uic.rv_deployBtn)
        btn.clicked.connect(deploy)
        CustomInfoBar.show_custom("", res.GUI.Uic.rv_deployDesc, self.rvtool, "WARNING", [btn])


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
        
        # runBtn 受 sv_path_card.setContent 影响，所有置于前面
        self.runBtn = PrimaryPushButton(FIF.PLAY, "run rV")
        self.runBtn.clicked.connect(self.run)
        self.runBtn.setDisabled(True)
        
        first_row = QHBoxLayout()
        self.sv_path_card = SvPathCard(self)
        self.sv_path_card.setContent(str(getattr(conf, "rv_script")))
        first_row.addWidget(self.sv_path_card)
        
        second_row = QHBoxLayout()
        spacer_info = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.showMaxBtn = TransparentPushButton(CustomIcon.TOOL_BOOK_MARKED, self.res.book_marked)
        self.showMaxBtn.clicked.connect(self.show_max)
        self.combineBtn = TransparentPushButton(CustomIcon.TOOL_MERGE, self.res.merge_move)
        self.combineBtn.clicked.connect(self.combine_then_mv)
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
        cmd = TmpCurrOs.run_cmd + [str(rv_script)]
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
