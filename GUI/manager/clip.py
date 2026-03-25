import json
import pathlib
from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from assets import res
from utils.website.info import BookInfo, Episode
from variables import CGS_DOC
from utils import conf
from utils.processed_class import ClipSqlHandler
from GUI.thread import ClipTasksThread
from GUI.uic.qfluent import CustomInfoBar

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
        # TODO[2](2026-03-02): 与搜索流程区分处理
        #     InfoBar.warning(
        #         title='Clip start error', content=res.GUI.Clip.process_warning,
        #         orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
        #         duration=3500, parent=self.gui.textBrowser
        #     )
        if not pathlib.Path(conf.clip_db).exists():
            CustomInfoBar.show(
                title='Clip-db not found', content=res.GUI.Clip.db_not_found_guide,
                parent=self.gui.showArea,
                url=f"{CGS_DOC}/config/#剪贴板db-clip-db", url_name="Guide"
            )
        else:
            clip = ClipSqlHandler(conf.clip_db, f"{conf.clip_sql} limit {conf.clip_read_num}",
                               getattr(self.gui.spiderUtils, "book_url_regex"))
            tf, match_items = clip.create_tf()
            if not match_items:
                self.gui.say(res.GUI.Clip.match_none % self.gui.spiderUtils.book_url_regex,
                             ignore_http=True)
            else:
                self.init_clip_handle(tf, match_items)

    def init_clip_handle(self, tf, match_urls):
        """初始化剪贴板处理"""

        self.gui.searchinput.setDisabled(True)
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

    def single_clip_tasks_data(self, book):
        if book.episodes:
            for ep in book.episodes:
                ep.name = ep.name or f'Episode-{ep.id}'
                self.infos[f"ep{book.idx}-{ep.idx}"] = ep
            self.infos[str(book.idx)] = book

            options = {}
            meta = []
            if book.artist:
                meta.append(book.artist)
            if book.pages:
                meta.append(f'{book.pages}pages')
            if meta:
                options['meta'] = meta
            if book.tags:
                options['meta_badges'] = book.tags[:20]

            book_key = json.dumps(str(book.idx))
            episodes_data = [{"name": ep.name, "idx": ep.idx} for ep in book.episodes]
            js_code = (
                f'addBookWithEpsCard({json.dumps(book.idx)},'
                f'{json.dumps(book.img_preview, ensure_ascii=False)},'
                f'{json.dumps(book.name, ensure_ascii=False)},'
                f'{json.dumps(book.url, ensure_ascii=False)},'
                f'{json.dumps(options, ensure_ascii=False)});'
                f'updateEpisodes({book_key},{json.dumps(episodes_data, ensure_ascii=False)});'
                f'selectAllEpisodes({book_key})'
            )
            self.gui.BrowserWindow.page_runtime.run_js(js_code)
        else:
            self.infos[str(book.idx)] = book

            options = {}
            if book.pages:
                options['pages'] = book.pages

            js_code = (
                f'addBookCard({json.dumps(book.idx)},'
                f'{json.dumps(book.img_preview, ensure_ascii=False)},'
                f'{json.dumps(book.name, ensure_ascii=False)},'
                f'{json.dumps(book.url, ensure_ascii=False)},'
                f'{json.dumps(options, ensure_ascii=False)})'
            )
            self.gui.BrowserWindow.page_runtime.run_js(js_code)

    def all_clip_tasks_data(self, total_data):
        """处理所有剪贴板任务完成后的操作"""
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)
                if conf.isDeduplicate:
                    self.gui.mark_tip(self.infos)
                    dled_bidxes = []
                    dled_eidxes = []
                    for key, obj in self.infos.items():
                        if getattr(obj, 'mark_tip', None) == 'downloaded':
                            if isinstance(obj, BookInfo):
                                dled_bidxes.append(key)
                            elif isinstance(obj, Episode):
                                dled_eidxes.append(key)
                    if dled_bidxes or dled_eidxes:
                        js_parts = []
                        if dled_bidxes:
                            js_parts.append(f'previewRuntime.markDownloaded({json.dumps(dled_bidxes)},[])')
                        if dled_eidxes:
                            js_parts.append(f'markDownloadedEpisodes({json.dumps(dled_eidxes)})')
                        self.gui.BrowserWindow.page_runtime.run_js(';'.join(js_parts))
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
            self.gui.BrowserWindow.page_runtime.page_to_html(
                refresh_tf,
                description="clip HTML snapshot",
                error_callback=lambda _exc: refresh_tf(""),
            )

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
