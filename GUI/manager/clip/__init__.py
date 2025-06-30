import re
import pathlib
from PyQt5.QtCore import Qt
from qfluentwidgets import (
    InfoBar, InfoBarIcon, InfoBarPosition
)

from assets import res
from variables import SPIDERS
from utils import conf
from utils.processed_class import PreviewHtml, ClipManager, Selected
from GUI.thread import ClipTasksThread
from GUI.uic.qfluent import (
    CustomInfoBar
)
"""处理所有剪贴板任务数据"""


class ClipGUIManager:
    res = res.GUI.ClipGUIManager

    def __init__(self, gui, *args, **kwargs):
        super(ClipGUIManager, self).__init__(*args, **kwargs)
        self.gui = gui

        # 剪贴板相关数据管理
        self.is_triggered = False
        self.tasks = []
        self.infos = {}  # 存储完整的任务信息，由single_clip_tasks_data构建
        self.page = None
        self.clipTasksThread = None

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
        else:
            clip = ClipManager(conf.clip_db, f"{conf.clip_sql} limit {conf.clip_read_num}",
                               getattr(self.gui.spiderUtils, "book_url_regex"))
            tf, match_items = clip.main()
            if not match_items:
                self.gui.say(res.GUI.Clip.match_none % self.gui.spiderUtils.book_url_regex,
                             ignore_http=True)
            else:
                self.init_clip_handle(tf, match_items)

    def init_clip_handle(self, tf, match_urls):
        """初始化剪贴板处理"""

        self.gui.searchinput.setDisabled(True)
        self.gui.previewInit = False
        self.is_triggered = True
        # 统一使用GUI的tf
        self.gui.tf = tf
        self.tasks = match_urls
        self.gui.set_preview()
        self.gui.BrowserWindow.resize(self.gui.BrowserWindow.width(), 860)
        self.gui.BrowserWindow.show()
        self.page = self.gui.BrowserWindow.view.page()
        self.clipTasksThread = ClipTasksThread(self.gui, match_urls)
        self.clipTasksThread.info_signal.connect(self.single_clip_tasks_data)
        self.clipTasksThread.total_signal.connect(self.all_clip_tasks_data)

        def start_clip_thread_once(ok):
            if ok:
                self.clipTasksThread.start()
                self.gui.BrowserWindow.view.loadFinished.disconnect(start_clip_thread_once)
        self.gui.BrowserWindow.view.loadFinished.connect(start_clip_thread_once)

    def single_clip_tasks_data(self, info):
        """处理单个剪贴板任务数据并构建infos为Selected对象"""
        # info格式: (idx, url, img_src, title, author, pages, tags, episodes)
        idx, url, img_src, title, author, pages, tags, episodes = info

        if episodes:
            # 有episodes时，每个episode用f"{idx}-{ep_idx}"作为键存储单个Selected
            for ep in episodes:
                episode_name = ep.get('ep', f'Episode-{ep.get("bid", "")}')
                selected = Selected(title=title, bid=ep['bid'], episode_name=episode_name)
                # 使用f"{任务idx}-{章节idx}"作为键
                unique_key = f"{idx}-{ep['idx']}"
                self.infos[unique_key] = selected
        else:
            # 无episodes时，使用任务idx作为键存储单个Selected
            selected = Selected(title=title, bid=url, episode_name=None)
            self.infos[str(idx)] = selected

        def js_param(val):
            if isinstance(val, str):
                return '"' + val.replace('"', '\\"') + '"'
            else:
                return str(val)
        params = ','.join(map(js_param, info))
        js_code = f'addEL({params})'
        self.gui.BrowserWindow.js_execute_by_page(self.page, js_code, lambda _: None)

    def all_clip_tasks_data(self, total_data):
        """处理所有剪贴板任务完成后的操作"""
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    # 实在搞不懂怎么跨端正常关掉已经打开的模态框，只能硬改标签属性了
                    html = re.sub(r"<body.*?>", "<body>", html)
                    html = re.sub(r"""aria-labelledby="exampleModalLabel".*?>""",
                                  """aria-labelledby="exampleModalLabel">""", html)
                    html = html.replace(r"""<div class="modal-backdrop fade show"></div>""", "")
                    f.write(html)
                if conf.isDeduplicate:
                    # 延迟一点确保页面刷新完成
                    from PyQt5.QtCore import QTimer
                    def delayed_mark():
                        page = self.page if self.page else None
                        PreviewHtml.tip_duplication(SPIDERS[self.gui.chooseBox.currentIndex()], self.gui.tf, page)
                    QTimer.singleShot(300, delayed_mark)
                    self.gui.BrowserWindow.refreshBtn.click()
                if self.gui.BrowserWindow.topHintBox.isChecked():
                    self.gui.BrowserWindow.topHintBox.click()
                if len(total_data) < len(self.tasks):
                    self.gui.activateWindow()
                    self.gui.say(f"➖ {self.gui.res.Clip.partial_fail}")
            else:
                print("没有内容？？？")
        if not total_data:
            self.gui.BrowserWindow.hide()
        else:
            self.gui.BrowserWindow.js_execute("finishTasks();", refresh_tf)

    def create_selected_list(self, browser_output):
        """根据用户选择创建Selected列表"""
        selected_list = [
            self.infos[unique_id]
            for unique_id in browser_output if unique_id in self.infos
        ]
        return selected_list

    def reset(self):
        """重置剪贴板状态"""
        self.is_triggered = False
        self.tasks = []
        self.infos = {}
        self.page = None
        if self.clipTasksThread:
            self.clipTasksThread = None
