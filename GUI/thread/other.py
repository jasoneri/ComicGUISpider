import pathlib
from copy import deepcopy

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import (
    Action, InfoBar, InfoBarPosition, DWMMenu
)

from assets import res
from utils import conf, curr_os, ori_path
from utils.comic_viewer_tools import combine_then_mv, show_max
from utils.processed_class import ClipManager
from GUI.uic.qfluent import CustomFlyout, TableFlyoutView, CustomInfoBar
from GUI.hitomi_tools import HitomiTools


class ToolMenu(DWMMenu):
    res = res.GUI.ToolMenu

    def __init__(self, gui, *args, **kwargs):
        super(ToolMenu, self).__init__(*args, **kwargs)
        self.gui = gui
        self.init_actions()
        self.gui.toolButton.setMenu(self)

    def init_actions(self):
        self.action_show_max = Action(self.tr(self.res.action1), triggered=self.show_max)
        self.action_combine_then_mv = Action(self.tr(self.res.action2), triggered=self.combine_then_mv)
        self.addAction(self.action_show_max)
        self.addAction(self.action_combine_then_mv)

    def show_max(self):
        record_txt = conf.sv_path.joinpath("web_handle/record.txt")
        if record_txt.exists():
            CustomFlyout.make(
                TableFlyoutView(show_max(record_txt), self.gui.textBrowser), 
                self.gui.searchinput, self.gui.textBrowser)
        else:
            InfoBar.warning(
                title='show_max', content=self.res.action2_warning % record_txt,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=5000, parent=self.gui.textBrowser
            )

    def combine_then_mv(self):
        done = combine_then_mv(conf.sv_path, conf.sv_path.joinpath("web"))
        InfoBar.success(
            title='combine_then_mv', content=self.res.combined_tip % (done, conf.sv_path.joinpath("web")),
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=3000, parent=self.gui.textBrowser
        )

    def switch_ero(self, index):
        self.removeAction(self.action_show_max)
        self.removeAction(self.action_combine_then_mv)
        
        self.action_read_clip = Action(self.tr(self.res.action_ero1), triggered=self.read_clip)
        self.addAction(self.action_read_clip)
        if index == 6:
            self.add_hitomi_tools()

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

    def add_hitomi_tools(self):
        if hasattr(self, "action_read_clip"):
            self.removeAction(self.action_read_clip)
        
        self.action_hitomi_tools = Action(self.tr('hitomi-tools'), triggered=self.hitomi_tools_run)
        self.addAction(self.action_hitomi_tools)

    def hitomi_tools_run(self):
        hitomi_db_path = ori_path.joinpath("assets/hitomi.db")
        if not hitomi_db_path.exists():
            CustomInfoBar.show(
                title='', content=res.GUI.hitomiDb_guide % hitomi_db_path,
                parent=self.gui.textBrowser, _type="WARNING",
                url="https://github.com/jasoneri/ComicGUISpider/releases/download/v2.2.0-beta/hitomi.db", url_name="Download"
            )
            # TODO[1] : 调用 utils/website/hitomi/scape_dataset.py 下载 hitomi.db
        else:
            if not hasattr(self.gui, "hitomi_tools"):
                self.gui.hitomi_tools = HitomiTools(self.gui)
            self.gui.hitomi_tools.show()

class CopyUnfinished:
    copy_delay = 150 if curr_os != "macOS" else 300
    copied = 0
    
    def __init__(self, tasks):
        self.tasks = deepcopy(tasks)
        self.length = len(self.tasks)

    def to_clip(self):
        def copy_to_clipboard(text):
            QApplication.clipboard().setText(text)
        for i, task in enumerate(self.tasks):
            QTimer.singleShot(self.copy_delay * (i + 1), 
                lambda t=task.title_url: copy_to_clipboard(t))
