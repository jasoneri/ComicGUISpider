import json

from utils import conf
from utils.processed_class import PreviewByFixHtml
from GUI.thread import AggrSearchThread


class AggrSearchManager:
    def __init__(self, gui, *args, **kwargs):
        super(AggrSearchManager, self).__init__(*args, **kwargs)
        self.gui = gui

        self.is_triggered = False
        self.tasks = []  # 存储搜索关键词列表
        self.infos = {}  # 存储完整的book信息，由single_aggr_search_data构建
        self.aggrSearchThread = None
        self.extractor = None  # 从 AggrSearchView 传递过来的 extractor

    def run(self, search_keywords):
        self.gui.searchinput.setDisabled(True)
        self.is_triggered = True

        self.gui.tf = PreviewByFixHtml.created_temp_html()
        self.gui.set_preview()
        self.gui.BrowserWindow.resize(self.gui.BrowserWindow.width()+20, 860)
        self.gui.BrowserWindow.show()

        self.tasks = search_keywords
        self.aggrSearchThread = AggrSearchThread(self.gui, search_keywords)
        self.aggrSearchThread.group_signal.connect(self.handle_group_data)
        self.aggrSearchThread.total_signal.connect(self.all_aggr_search_data)

        def start_aggr_thread_once(ok):
            if ok:
                self.aggrSearchThread.start()
                self.gui.BrowserWindow.view.loadFinished.disconnect(start_aggr_thread_once)

        self.gui.BrowserWindow.view.loadFinished.connect(start_aggr_thread_once)

    def handle_group_data(self, group_idx, books_list):
        if not books_list:
            return
        keyword = getattr(books_list[0], 'search_keyword', f'Group {group_idx}')
        js_parts = [f'addFixGroup({json.dumps(group_idx)},{json.dumps(keyword, ensure_ascii=False)})']

        for book in books_list:
            self.infos[str(book.idx)] = book
            options = {}
            for attr in ('pages', 'likes', 'lang', 'btype'):
                val = getattr(book, attr, None)
                if val:
                    options[attr] = val

            if book.episodes:
                meta = []
                if book.artist:
                    meta.append(book.artist)
                if book.pages:
                    meta.append(f'{book.pages}pages')
                ep_options = {}
                if meta:
                    ep_options['meta'] = meta
                if book.tags:
                    ep_options['meta_badges'] = book.tags[:20]
                js_parts.append(
                    f'addBookWithEpsCard({json.dumps(book.idx)},'
                    f'{json.dumps(book.img_preview, ensure_ascii=False)},'
                    f'{json.dumps(book.name, ensure_ascii=False)},'
                    f'{json.dumps(book.url, ensure_ascii=False)},'
                    f'{json.dumps(ep_options, ensure_ascii=False)})'
                )
            else:
                js_parts.append(
                    f'addBookCard({json.dumps(book.idx)},'
                    f'{json.dumps(book.img_preview, ensure_ascii=False)},'
                    f'{json.dumps(book.name, ensure_ascii=False)},'
                    f'{json.dumps(book.url, ensure_ascii=False)},'
                    f'{json.dumps(options, ensure_ascii=False)})'
                )

        self.gui.BrowserWindow.page_runtime.run_js(';'.join(js_parts))

    def all_aggr_search_data(self, total_data):
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)
                if conf.isDeduplicate:
                    downloaded_md5s = self.gui.download_state.downloaded_md5s(self.infos.values())
                    dled_bidxes = [
                        key for key, obj in self.infos.items()
                        if hasattr(obj, "id_and_md5") and obj.id_and_md5()[1] in downloaded_md5s
                        and not getattr(obj, "episodes", None)
                    ]
                    if dled_bidxes:
                        self.gui.BrowserWindow.page_runtime.run_js(
                            f'previewRuntime.markDownloaded({json.dumps(dled_bidxes)},[])'
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
                description="ags HTML snapshot",
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
        self.extractor.remove_list(selected_list)
        self.gui.sel_mgr.submit_decision(
            "BOOK",
            selected_list,
            flow_stage=self.gui.flow_stage,
        )

    def reset(self):
        self.is_triggered = False
        self.tasks = []
        self.infos = {}
        if self.aggrSearchThread:
            self.aggrSearchThread = None
