import json
import pathlib

from assets import res
from variables import CGS_DOC
from utils import conf
from utils.processed_class import ClipSqlHandler
from GUI.thread import ClipTasksThread
from GUI.uic.qfluent import CustomInfoBar

"""处理所有剪贴板任务数据"""


class _ClipPreviewScriptBatch:
    def __init__(self):
        self._calls = []

    @staticmethod
    def _serialize(value):
        return json.dumps(value, ensure_ascii=False)

    def call(self, name, *args):
        rendered_args = ','.join(self._serialize(arg) for arg in args)
        self._calls.append(f"{name}({rendered_args})")
        return self

    def add_book_card(self, book, options):
        return self.call("addBookCard", book.idx, book.img_preview, book.name, book.url, options)

    def add_book_with_episodes(self, book, options):
        return self.call("addBookWithEpsCard", book.idx, book.img_preview, book.name, book.url, options)

    def update_episodes(self, book_idx, episodes_data):
        return self.call("updateEpisodes", str(book_idx), episodes_data)

    def select_all_episodes(self, book_idx):
        return self.call("selectAllEpisodes", str(book_idx))

    def mark_downloaded(self, book_ids):
        return self.call("previewRuntime.markDownloaded", book_ids, [])

    def render(self):
        return ';'.join(self._calls)

    def run(self, page_runtime):
        page_runtime.run_js(self.render())


class ClipGUIManager:
    res = res.GUI.ClipGUIManager

    def __init__(self, gui, *args, **kwargs):
        super(ClipGUIManager, self).__init__(*args, **kwargs)
        self.gui = gui

        # 剪贴板相关数据管理
        self.is_triggered = False
        self.tasks = []
        self.infos = {}  # 存储完整的任务信息，由single_clip_tasks_data构建
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
            gui_site_runtime = self.gui.gui_site_runtime
            if gui_site_runtime is None:
                raise RuntimeError("gui_site_runtime unavailable for clip flow")
            clip = ClipSqlHandler(conf.clip_db, f"{conf.clip_sql} limit {conf.clip_read_num}",
                               gui_site_runtime.book_url_regex)
            tf, match_items = clip.create_tf()
            if not match_items:
                self.gui.say(res.GUI.Clip.match_none % gui_site_runtime.book_url_regex,
                             ignore_http=True)
            else:
                self.init_clip_handle(tf, match_items)

    def init_clip_handle(self, tf, match_urls):
        """初始化剪贴板处理"""

        self.gui.update_search_ui(controls_blocked=True)
        self.is_triggered = True
        # 统一使用GUI的tf
        self.gui.tf = tf
        self.tasks = match_urls
        self.gui.set_preview()
        self.gui.BrowserWindow.resize(self.gui.BrowserWindow.width(), 860)
        self.gui.BrowserWindow.show()
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
            downloaded_md5s = {
                episode.id_and_md5()[1]
                for episode in self.gui.download_state.downloaded_items(book.episodes)
            }
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

            episodes_data = [
                {
                    "name": ep.name,
                    "idx": ep.idx,
                    "downloaded": ep.id_and_md5()[1] in downloaded_md5s,
                }
                for ep in book.episodes
            ]
            js_batch = _ClipPreviewScriptBatch()
            js_batch.add_book_with_episodes(book, options)
            js_batch.update_episodes(book.idx, episodes_data)
            js_batch.select_all_episodes(book.idx)
            js_batch.run(self.gui.BrowserWindow.page_runtime)
        else:
            self.infos[str(book.idx)] = book

            options = {}
            if book.pages:
                options['pages'] = book.pages

            _ClipPreviewScriptBatch().add_book_card(book, options).run(
                self.gui.BrowserWindow.page_runtime
            )

    def all_clip_tasks_data(self, total_data):
        """处理所有剪贴板任务完成后的操作"""
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)
                if conf.isDeduplicate:
                    dled_bidxes = []
                    downloaded_md5s = self.gui.download_state.downloaded_md5s(self.infos.values())
                    for key, obj in self.infos.items():
                        if not hasattr(obj, "id_and_md5") or obj.id_and_md5()[1] not in downloaded_md5s:
                            continue
                        if getattr(obj, "from_book", None) is None:
                            dled_bidxes.append(key)
                    if dled_bidxes:
                        _ClipPreviewScriptBatch().mark_downloaded(dled_bidxes).run(
                            self.gui.BrowserWindow.page_runtime
                        )
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

    def submit_browser_selection(self):
        browser = getattr(self.gui, "BrowserWindow", None)
        if browser is None:
            return
        selected_list = [
            self.infos[unique_id]
            for unique_id in list(browser.output or [])
            if unique_id in self.infos
        ]
        self.gui.sel_mgr.submit_decision(
            "BOOK",
            selected_list,
            flow_stage=self.gui.flow_stage,
        )

    def reset(self):
        """重置剪贴板状态"""
        self.is_triggered = False
        self.tasks = []
        self.infos = {}
        if self.clipTasksThread:
            self.clipTasksThread = None
