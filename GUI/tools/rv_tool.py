import pathlib
import platform
import shutil
import subprocess
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QSpacerItem, QSizePolicy, QFileDialog, QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, PrimaryToolButton,
    TransparentToolButton, PushButton, HyperlinkButton, 
    FluentIcon as FIF, PushSettingCard, InfoBar, InfoBarPosition,
    BodyLabel
)
from qframelesswindow import FramelessWindow

from assets import res as ori_res
from utils import curr_os, conf, yaml_update
from utils.redViewer_tools import combine_then_mv, show_max
from GUI.uic.qfluent import CustomFlyout, TableFlyoutView, CustomIcon

tools_res = ori_res.GUI.Tools


class WinOS:
    file_type = ".ps1"
    script_file_type = "Script Files (*.ps1)"
    run_cmd = ["cmd.exe", "/c", "start", "/B", 'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    run_cmd_kw = dict(start_new_session=True, shell=True, creationflags=0x00000008 | 0x00000200)
    deploy_cmd = [curr_os.shell, "-Command", "irm https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/windows.ps1 | iex"]
    deploy_cmd_kw = dict(start_new_session=True, shell=True, creationflags=0x00000008 | 0x00000200)
    deploy_desc = tools_res.rv_deployDesc + tools_res.rv_deployWinRequire


class ElseOS:
    file_type = ".sh"
    script_file_type = "Script Files (*.sh)"
    run_cmd = [curr_os.shell]
    deploy_cmd = [curr_os.shell, "-c", "curl -fsSL https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/linux.sh | zsh"]
    deploy_cmd_kw = run_cmd_kw = dict(start_new_session=True, shell=True)
    deploy_desc = tools_res.rv_deployDesc

TmpCurrOs = WinOS if curr_os.shell == 'powershell' else ElseOS


class AskDeployView(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        w = int(parent.width()*0.7)
        h = int(parent.height()*1.1)
        self.resize(w, h)
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        self.move(int((screen_geo.width() - w) / 2.3),int((screen_geo.height() - h) / 2))
        self.init_ui()

    def init_ui(self):
        first_row = QHBoxLayout()
        first_row.addStretch()
        body = BodyLabel(TmpCurrOs.deploy_desc)
        first_row.addWidget(body)
        first_row.addStretch()
        
        second_row = QHBoxLayout()
        first_row.addStretch()
        def deploy():
            run_dir = QFileDialog.getExistingDirectory(self, ori_res.GUI.Uic.sv_path_desc_tip)
            if run_dir:
                if platform.system() == "Darwin":
                    TmpCurrOs.deploy_cmd_kw = dict(start_new_session=True)
                    TmpCurrOs.deploy_cmd = [
                        "osascript",
                        "-e",
                        f'''tell application "Terminal" to do script "cd {str(run_dir)};zsh -c \\"curl -fsSL https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/macos.sh | zsh\\""'''
                    ]
                subprocess.Popen(TmpCurrOs.deploy_cmd, cwd=str(run_dir), **TmpCurrOs.deploy_cmd_kw)
        deployBtn = PrimaryPushButton(FIF.COMMAND_PROMPT, tools_res.rv_deployBtn)
        deployBtn.clicked.connect(deploy)
        hyberBtn = HyperlinkButton(FIF.GITHUB, 
            r"https://github.com/jasoneri/redViewer#%EF%B8%8F%E9%83%A8%WE7%BD%B2%E6%9B%B4%E6%96%B0%E8%BF%90%E8%A1%8C%E5%A4%9A%E5%90%88%E4%B8%80%E8%84%9A%E6%9C%AC", 
            "rV 部署命令说明"
        )
        cancelBtn = TransparentToolButton(FIF.CLOSE, self)
        cancelBtn.clicked.connect(self.close)
        second_row.addWidget(hyberBtn)
        second_row.addWidget(deployBtn)
        second_row.addWidget(cancelBtn)
        first_row.addStretch()

        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)


class SvPathCard(PushSettingCard):
    def __init__(self, parent=None):
        super().__init__(tools_res.rv_scriptp_desc_tip % TmpCurrOs.file_type, FIF.DOCUMENT, 
                         tools_res.rv_scriptp_desc, "", parent)
        self.rvtool = parent
        self.clicked.connect(self._onSelectScript)

    def setContent(self, content: str):
        super().setContent(content)
        self.rvtool.runBtn.setEnabled(bool(content and content != "."))
        self.rvtool.broomBtn.setEnabled(bool(content and content != "."))

    def _onSelectScript(self):
        file, _ = QFileDialog.getOpenFileName(self, ori_res.GUI.Uic.sv_path_desc_tip, "", TmpCurrOs.script_file_type)
        if file:
            file = pathlib.Path(file)
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read(700)
            if not ",' ,'/ /|" in content:
                InfoBar.error(
                    title='', content=tools_res.rv_deploy_desc_content,
                    orient=Qt.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP_LEFT,
                    duration=5000, parent=self.rvtool
                )
            self.setContent(str(file))
            conf.update(rv_script=str(file))
            # 将 CGS 的存储目录同步到 rV 里
            rv_conf = file.parent.joinpath(r"redViewer/backend/conf.yml")
            if not rv_conf.exists():
                shutil.move(file.parent.joinpath(r"redViewer/backend/utils/conf_sample.yml"), rv_conf)
            yaml_update(rv_conf, {"path": str(conf.sv_path)})
        if not self.contentLabel.text() or self.contentLabel.text() == ".":
            self.ask_deploy()


class rvTool(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.toolWin = parent
        self.init_ui()
    
    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        # 受 sv_path_card.setContent 影响的 btn 都置于 sv_path_card 前面
        self.runBtn = PrimaryPushButton(FIF.PLAY, "run rV")
        self.runBtn.clicked.connect(self.run)
        self.runBtn.setDisabled(True)
        self.broomBtn = PrimaryToolButton(FIF.BROOM, self)
        self.broomBtn.clicked.connect(self.broom)
        self.broomBtn.setDisabled(True)
        
        first_row = QHBoxLayout()
        self.sv_path_card = SvPathCard(self)
        self.sv_path_card.setContent(str(getattr(conf, "rv_script")))
        first_row.addWidget(self.sv_path_card)
        
        second_row = QHBoxLayout()
        spacer_info = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.deployBtn = PrimaryPushButton(FIF.DICTIONARY, tools_res.rv_deploy_desc)
        self.showMaxBtn = PushButton(CustomIcon.TOOL_BOOK_MARKED, tools_res.rv_book_marked)
        self.deployBtn.clicked.connect(self.deploy)
        self.showMaxBtn.clicked.connect(self.show_max)
        self.combineBtn = PushButton(CustomIcon.TOOL_MERGE, tools_res.rv_merge_move)
        self.combineBtn.clicked.connect(self.combine_then_mv)
        second_row.addSpacerItem(spacer_info)
        second_row.addWidget(self.deployBtn)
        second_row.addWidget(self.showMaxBtn)
        second_row.addWidget(self.combineBtn)
        second_row.addWidget(self.broomBtn)
        second_row.addWidget(self.runBtn)

        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)

    def broom(self):
        conf.update(rv_script="")
        self.sv_path_card.setContent("")

    def deploy(self):
        _ = AskDeployView(self)
        _.show()
    
    def show_max(self):
        CustomFlyout.make(TableFlyoutView(show_max(), self), self.sv_path_card, self)

    def combine_then_mv(self):
        done = combine_then_mv(conf.sv_path, conf.sv_path.joinpath("web"))
        InfoBar.success(
            title='combine_then_mv', content=ori_res.GUI.Tools.rv_combined_tip % (done, str(conf.sv_path.joinpath("web"))),
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=3000, parent=self
        )

    def run(self):
        rv_script = pathlib.Path(getattr(conf, "rv_script"))
        run_dir = rv_script.parent
        cmd = TmpCurrOs.run_cmd + [str(rv_script)]
        if platform.system() == "Darwin":
            TmpCurrOs.run_cmd_kw = dict(start_new_session=True)
            cmd = [
                "osascript", 
                "-e", 
                f'''tell application "Terminal" to do script "zsh {str(rv_script)}"'''
            ]
        subprocess.Popen(cmd, cwd=str(run_dir), **TmpCurrOs.run_cmd_kw)
        self.toolWin.close()
