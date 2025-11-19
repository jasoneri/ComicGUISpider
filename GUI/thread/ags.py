import asyncio
from PyQt5.QtCore import QThread, pyqtSignal
from utils import conf, get_loop, PresetHtmlEl
from utils.ags import SearchKey
from assets import res
from GUI.core.font import font_color


class AggrSearchThread(QThread):
    total_signal = pyqtSignal(dict)
    group_signal = pyqtSignal(int, list)  # 用于通知完成一组搜索: (group_idx, books_list)

    def __init__(self, gui, tasks):
        super(AggrSearchThread, self).__init__(gui)
        self.gui = gui
        self.tasks = tasks
        self.book_idx_counter = 0  # 全局book索引计数器

    def run(self):
        self.msleep(500)
        loop = get_loop()
        total = loop.run_until_complete(self._async_run())
        self.handle_total(total)

    async def _async_run(self):
        async with self.gui.sut.get_cli(conf, is_async=True) as cli:
            total = {}
            async def fetch_single(group_idx, search_keyword: SearchKey):
                try:
                    search_url = self.gui.sut.build_search_url(search_keyword)
                    resp = await cli.get(search_url, follow_redirects=True, timeout=6)
                    books = self.gui.sut.parse_search(resp.text)
                    self.msleep(50)

                    group_books = {}
                    books_list = []
                    if not books:
                        self.gui.say(f"🅾️{res.GUI.Ags.empty_search}: {search_keyword}")
                        return {}
                    for book in books:
                        self.book_idx_counter += 1
                        book.name = PresetHtmlEl.sub(book.name)
                        book.idx = self.book_idx_counter
                        book.search_keyword = search_keyword
                        book.group_idx = group_idx + 1  # 记录属于哪个搜索组
                        group_books[book.idx] = book
                        books_list.append(book)
                    self.group_signal.emit(group_idx + 1, books_list)
                    return group_books
                except Exception as e:
                    err_msg = rf"{res.GUI.Clip.get_info_error}({search_keyword}): [{type(e).__name__}] {str(e)}"
                    self.gui.log.exception(e)
                    self.gui.say(font_color(err_msg + '<br>', cls='theme-err'), ignore_http=True)
                    return {}

            tasks = [fetch_single(idx, keyword) for idx, keyword in enumerate(self.tasks)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    continue
                if result:
                    total.update(result)  # 合并所有book到total字典中
            return total

    def check_condition_and_run_js(self):
        if self.iterations >= self.max_iterations:
            print("[aggr search tasks loop]❌over max_iterations, fail.")
            self.total_signal.emit(self.total)
            return
        self.iterations += 1
        self.gui.BrowserWindow.js_execute("checkDoneTasks();", self.handle_js_result)

    def handle_js_result(self, num):
        if num and num >= len(self.total):
            print("[aggr search tasks loop]✅finsh.")
            self.total_signal.emit(self.total)
            return
        self.msleep(250)
        self.check_condition_and_run_js()

    def handle_total(self, total):
        self.max_iterations = 7 * len(self.tasks)
        self.iterations = 0
        self.total = total
        if not total:
            self.total_signal.emit({})
            self.gui.say(font_color(res.GUI.Clip.all_fail, cls='theme-err'), ignore_http=True)
            self.gui.say(font_color(rf"<br>{res.GUI.Clip.view_log} [{conf.log_path}\GUI.log]", cls='theme-err', size=5))
        else:
            self.msleep(1200 if len(self.total) == 1 else 350)
            self.check_condition_and_run_js()
