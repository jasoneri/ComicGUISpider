import json
from PyQt5.QtCore import QTimer

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
        self.gui.previewInit = False
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
        self.aggrSearchThread.start()

    def handle_group_data(self, group_idx, books_list):
        # preview_args格式: (idx, img_preview, name, preview_url)
        books_data = []
        for book in books_list:
            self.infos[str(book.idx)] = book
            idx, img_src, title, url = book.preview_args
            book_dict = {
                'idx': idx, 'img_src': img_src, 'title': title,
                'url': url, 'search_keyword': getattr(book, 'search_keyword', ''),
            }
            for _ in ('pages', 'likes', 'lang', 'btype'):
                if hasattr(book, _) and getattr(book, _):
                    book_dict[_] = getattr(book, _)
            if hasattr(book, 'mark_tip') and book.mark_tip:
                book_dict['flag'] = book.mark_tip
            books_data.append(book_dict)

        books_json = json.dumps(books_data, ensure_ascii=False)
        js_code = f'addAgsGroup({group_idx}, {books_json});'
        self.gui.BrowserWindow.js_execute_by_page(self.page, js_code, lambda _: None)

    def all_aggr_search_data(self, total_data):
        def refresh_tf(html):
            if html:
                with open(self.gui.tf, 'w', encoding='utf-8') as f:
                    f.write(html)
                if conf.isDeduplicate:
                    def delayed_mark():
                        books_and_eps = self.gui.mark_tip(self.infos)
                        dled_bidxes = []
                        for key, obj in self.infos.items():
                            if getattr(obj, 'mark_tip', None) == 'downloaded':
                                if isinstance(obj, BookInfo):
                                    dled_bidxes.append(key)
                        js_code = f'''tryMarkDownload({dled_bidxes},[]);'''
                        self.gui.BrowserWindow.js_execute_by_page(self.page, js_code, lambda _: None)
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
