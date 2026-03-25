import json

from utils.website.info import BookInfo
from utils import conf
from utils.processed_class import PreviewByAgsHtml
from GUI.thread import AggrSearchThread


class AggrSearchManager:
    def __init__(self, gui, *args, **kwargs):
        super(AggrSearchManager, self).__init__(*args, **kwargs)
        self.gui = gui

        self.is_triggered = False
        self.tasks = []  # 存储搜索关键词列表
        self.infos = {}  # 存储完整的book信息，由single_aggr_search_data构建
        self.page = None
        self.aggrSearchThread = None
        self.extractor = None  # 从 AggrSearchView 传递过来的 extractor

    def run(self, search_keywords):
        self.gui.searchinput.setDisabled(True)
        self.is_triggered = True

        self.gui.tf = PreviewByAgsHtml.created_temp_html()
        self.gui.set_preview()
        self.gui.BrowserWindow.resize(self.gui.BrowserWindow.width()+20, 860)
        self.gui.BrowserWindow.show()
        self.page = self.gui.BrowserWindow.view.page()

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
            if getattr(book, 'mark_tip', None):
                options['flag'] = book.mark_tip

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
                    self.gui.mark_tip(self.infos)
                    dled_bidxes = [
                        key for key, obj in self.infos.items()
                        if getattr(obj, 'mark_tip', None) == 'downloaded' and isinstance(obj, BookInfo)
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

    def create_selected_list(self, browser_output):
        selected_list = [
            self.infos[unique_id]
            for unique_id in browser_output if unique_id in self.infos
        ]
        self.extractor.remove_list(selected_list)
        return selected_list

    def reset(self):
        self.is_triggered = False
        self.tasks = []
        self.infos = {}
        self.page = None
        if self.aggrSearchThread:
            self.aggrSearchThread = None
