import subprocess
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QIcon, QDesktopServices, QPixmap
from PyQt5.QtWidgets import QSpacerItem, QSizePolicy, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget, QGraphicsOpacityEffect
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton,
    TransparentToolButton, PushButton, PrimaryToolButton, 
    FluentIcon as FIF, InfoBar, InfoBarPosition,
    BodyLabel, ImageLabel
)
from assets import res as ori_res
from utils import curr_os, conf, yaml_update
from utils.config.rule import CgsRuleMgr
from GUI.uic.qfluent import CustomFlyout, TableFlyoutView, CustomIcon, CustomInfoBar, MonkeyPatch as FluentMonkeyPatch

tools_res = ori_res.GUI.Tools


def _bind_ratio(widget, ratio):
    _orig = widget.resizeEvent
    def _resize(event):
        _orig(event)
        w = int(event.size().height() * ratio)
        if widget.minimumWidth() != w:
            widget.setFixedWidth(w)
    widget.resizeEvent = _resize


class WinOS:
    file_type = ".exe"
    script_type = "Script Exe (*.exe)"
    run_cmd = ["start", "/B"]
    run_cmd_kw = dict(start_new_session=True, shell=True, creationflags=0x00000008 | 0x00000200)
    deploy_cmd = [curr_os.shell, "-Command", "irm https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/windows.ps1 | iex"]
    deploy_cmd_kw = dict(start_new_session=True, shell=True, creationflags=0x00000008 | 0x00000200)
    deploy_desc = tools_res.rv_deployDesc + tools_res.rv_deployWinRequire


class ElseOS:
    file_type = ".sh"
    script_type = "Script Files (*.sh)"
    run_cmd = [curr_os.shell]
    deploy_cmd = [curr_os.shell, "-c", "curl -fsSL https://gitee.com/json_eri/redViewer/raw/master/deploy/online_scripts/linux.sh | zsh"]
    deploy_cmd_kw = run_cmd_kw = dict(start_new_session=True, shell=True)
    deploy_desc = tools_res.rv_deployDesc

TmpCurrOs = WinOS if curr_os.shell == 'powershell' else ElseOS


class rvTool(QWidget):
    infobar_pos = InfoBarPosition.BOTTOM_LEFT

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toolWin = parent
        self.gui = parent.gui
        self.init_ui()

    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        row = QHBoxLayout()
        row.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # col1: showMaxBtn + scanBtn
        col1 = QVBoxLayout()
        self.showMaxBtn = PrimaryPushButton(CustomIcon.TOOL_BOOK_MARKED, tools_res.rv_book_marked)
        self.scanBtn = PushButton(FIF.SYNC, tools_res.rv_scan_local)
        col1.addWidget(self.showMaxBtn)
        col1.addWidget(self.scanBtn)

        # sauceWidget: sauceBtn + sauceLabel (hidden by default)
        self.sauceWidget = QWidget()
        sauce_layout = QVBoxLayout(self.sauceWidget)
        sauce_layout.setSpacing(0)
        sauce_layout.setContentsMargins(0, 0, 0, 5)
        self.sauceBtn = TransparentToolButton(QIcon(':/tools/saucenao.png'))
        self.sauceLabel = BodyLabel(f"{tools_res.search_by_pic}👆")
        self.sauceLabel.setAlignment(Qt.AlignCenter)
        sauce_layout.addWidget(self.sauceBtn)
        sauce_layout.addWidget(self.sauceLabel)
        self.sauceWidget.setVisible(False)

        # col3: container (background layer + button layer)
        self.col3Widget = QWidget()
        self.col3Widget.setContentsMargins(0, 0, 0, 0)
        self.col3BgLabel = ImageLabel(self.col3Widget)
        self.col3BgLabel.setScaledContents(True)
        self.col3BgLabel.setImage(QPixmap(":/tools/rv.png"))
        bg_opacity = QGraphicsOpacityEffect(self.col3BgLabel)
        bg_opacity.setOpacity(0.3)
        self.col3BgLabel.setGraphicsEffect(bg_opacity)
        self.col3BgLabel.lower()

        col3 = QVBoxLayout(self.col3Widget)
        col3.setContentsMargins(0, 0, 0, 0)
        col3.setSpacing(5)
        self.deployBtn = PrimaryPushButton(FIF.DOWNLOAD, tools_res.rv_deploy_desc)
        deploy_opacity = QGraphicsOpacityEffect(self.deployBtn)
        deploy_opacity.setOpacity(0.8)
        self.deployBtn.setGraphicsEffect(deploy_opacity)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        self.broomBtn = TransparentToolButton(FIF.BROOM, self)
        self.broomBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._sync_broom_state()
        self.runBtn = PrimaryToolButton(FIF.PLAY)
        self.runBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        run_opacity = QGraphicsOpacityEffect(self.runBtn)
        run_opacity.setOpacity(0.8)
        self.runBtn.setGraphicsEffect(run_opacity)
        btn_row.addWidget(self.broomBtn)
        btn_row.addWidget(self.runBtn)
        col3.addWidget(self.deployBtn)
        col3.addLayout(btn_row)
        
        self.showMaxBtn.clicked.connect(self.show_max)
        self.scanBtn.clicked.connect(self.rv_scan)
        self.sauceBtn.clicked.connect(self.do_sauce)
        self.deployBtn.clicked.connect(self.deploy)
        self.broomBtn.clicked.connect(self.broom)
        self.runBtn.clicked.connect(self.run)
        
        row.addLayout(col1)
        row.addWidget(self.sauceWidget)
        row.addWidget(self.col3Widget)
        row.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.main_layout.addLayout(row)

        _bind_ratio(self.showMaxBtn, 3)
        _bind_ratio(self.scanBtn, 3)
        _bind_ratio(self.sauceBtn, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = int(event.size().height() * 0.3)
        sq = 2 * h + 5
        self.col3Widget.setFixedSize(sq, sq)
        self.col3BgLabel.setGeometry(0, 0, sq, sq)
        if self.showMaxBtn.maximumHeight() != h:
            for btn in (self.showMaxBtn, self.scanBtn, self.deployBtn, self.broomBtn, self.runBtn):
                btn.setFixedHeight(h)
            icon_size = int(h*1.5)
            self.sauceBtn.setFixedHeight(icon_size)
            self.sauceBtn.setIconSize(QSize(icon_size, icon_size))

    def set_sauce_visible(self, visible: bool):
        self.sauceWidget.setVisible(bool(visible))

    def do_sauce(self):
        def callback():
            bro = self.gui.BrowserWindow
            FluentMonkeyPatch.rbutton_menu_sauce(bro)
            target = bro.view.mapToGlobal(bro.view.rect().bottomLeft())
            target.setX(target.x() + 18)
            target.setY(target.y() - 18)
            guide = BodyLabel(tools_res.search_by_pic_guide)
            img = ImageLabel()
            img.setImage(QPixmap(":/tools/ascii2d.png"))
            CustomInfoBar.show_custom(title='', content='', parent=bro.view, _type="INFORMATION", duration=7000,
                ib_pos=InfoBarPosition.TOP_LEFT, widgets=[guide,img])
        self.gui.open_url_by_browser("https://saucenao.com/", callback)

    def show_max(self):
        self.gui.bsm = self.gui.bsm or self.gui.rv_tools.show_max()
        if not self.gui.bsm:
            InfoBar.warning(title='', content='show empty, had you downloaded on this sv_path? or scan',
                position=self.infobar_pos, duration=3000, parent=self)
            return
        self.table_fv = CustomFlyout.make(TableFlyoutView(self.gui.bsm, self), self.showMaxBtn, self)

    def rv_scan(self):
        if not CgsRuleMgr.exists(conf.sv_path):
            InfoBar.warning(title='', content=tools_res.rv_notCgsRule,
                position=InfoBarPosition.TOP_RIGHT, duration=4000, parent=self)
        self.gui.rv_mgr.start_scan(show_progress=True, parent_widget=self, pos=self.infobar_pos)

    def _sync_broom_state(self):
        rv = conf.rv_script
        self.broomBtn.setEnabled(bool(rv and str(rv) != "."))

    def deploy(self):
        QDesktopServices.openUrl(QUrl("https://github.com/jasoneri/redViewer/releases"))

    def broom(self):
        conf.update(rv_script="")
        self._sync_broom_state()

    def run(self):
        if TmpCurrOs is not WinOS:
            CustomInfoBar.show(
                title='', content=tools_res.rv_nonwin_guide,
                parent=self,
                url="https://rv.101114105.xyz/deploy/#%E2%8C%98-2-%E5%91%BD%E4%BB%A4%E8%A1%8C-%E9%83%A8%E7%BD%B2-%E8%BF%90%E8%A1%8C%E2%80%94%E5%A4%9A%E5%90%88%E4%B8%80%E8%84%9A%E6%9C%AC",
                url_name=tools_res.rv_deploy_desc,
                _type="INFORMATION"
            )
            return

        rv_script = conf.rv_script
        if not (rv_script and str(rv_script) != "." and rv_script.is_file() and rv_script.suffix == TmpCurrOs.file_type):
            file, _ = QFileDialog.getOpenFileName(self, ori_res.GUI.Uic.sv_path_desc_tip, "", TmpCurrOs.script_type)
            if not file:
                return
            conf.update(rv_script=file)
            rv_script = conf.rv_script
            self._sync_broom_state()

        run_dir = rv_script.parent
        cmd = TmpCurrOs.run_cmd + [str(rv_script)]
        subprocess.Popen(cmd, cwd=str(run_dir), **TmpCurrOs.run_cmd_kw)
        self.toolWin.close()
