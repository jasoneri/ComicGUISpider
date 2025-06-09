import pathlib
from PyQt5.QtCore import Qt
from qfluentwidgets import (
    Action, InfoBar, InfoBarPosition, DWMMenu
)

from assets import res
from utils import conf, ori_path
from utils.processed_class import ClipManager
from GUI.uic.qfluent import CustomInfoBar
from GUI.tools import HitomiTools

class ToolMenu(DWMMenu):
    res = res.GUI.ToolMenu

    def __init__(self, gui, *args, **kwargs):
        super(ToolMenu, self).__init__(*args, **kwargs)
        self.gui = gui
        self.init_actions()

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
