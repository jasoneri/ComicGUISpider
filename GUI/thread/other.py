from copy import deepcopy

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import (
    Action, InfoBar, InfoBarPosition, DWMMenu
)

from assets import res
from utils import conf, curr_os
from utils.comic_viewer_tools import combine_then_mv, show_max
from utils.processed_class import ClipManager
from GUI.uic.qfluent import CustomFlyout, TableFlyoutView


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
            title='combine_then_mv', content=f"已将{done}整合章节并转换至[{conf.sv_path.joinpath("web")}]",
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=3000, parent=self.gui.textBrowser
        )

    def switch_ero(self):
        self.removeAction(self.action_show_max)
        self.removeAction(self.action_combine_then_mv)
        
        self.action_read_clip = Action(self.tr(self.res.action_ero1), triggered=self.read_clip)
        self.addAction(self.action_read_clip)

    def read_clip(self):
        if self.gui.next_btn.text() != '搜索':
            InfoBar.warning(
                title='Clip start error', content=self.res.clip_process_warning,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=3500, parent=self.gui.textBrowser
            )
        else:
            clip = ClipManager(conf.clip_db, f"{conf.clip_sql} limit {conf.clip_read_num}",
                               getattr(self.gui.spiderUtils, "book_url_regex"))
            tf, match_items = clip.main()
            if not match_items:
                self.gui.say(f"无匹配任务，先进行复制再运行此功能，当前匹配规则：{self.gui.spiderUtils.book_url_regex}",
                             ignore_http=True)
            else:
                self.gui.init_clip_handle(tf, match_items)


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
