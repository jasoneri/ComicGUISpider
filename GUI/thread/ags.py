import asyncio
import traceback
from PySide6.QtCore import QThread, Signal
from utils import PresetHtmlEl
from utils.ags import SearchKey
from assets import res


class AggrSearchThread(QThread):
    total_signal = Signal(object)
    group_signal = Signal(int, list)  # 用于通知完成一组搜索: (group_idx, books_list)
    empty_signal = Signal(object)
    error_signal = Signal(str, str)

    def __init__(self, gui, tasks, *, thread_site_runtime):
        super(AggrSearchThread, self).__init__(gui)
        self.tasks = list(tasks)
        self.thread_site_runtime = thread_site_runtime
        self.book_idx_counter = 0  # 全局book索引计数器
        self._active = True
        self._loop = None
        self._pending_tasks = []

    def stop(self):
        self._active = False
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._cancel_async_tasks)

    def _cancel_async_tasks(self):
        for task in list(self._pending_tasks):
            task.cancel()

    def run(self):
        self.msleep(500)
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            total = loop.run_until_complete(self._async_run())
            if self._active:
                self.total_signal.emit(total)
        finally:
            try:
                loop.run_until_complete(self.thread_site_runtime.aclose())
            finally:
                loop.close()
                self._loop = None

    async def _async_run(self):
        total = {}

        async def fetch_single(group_idx, search_keyword: SearchKey):
            if not self._active:
                return {}
            try:
                books = await self.thread_site_runtime.preview_search(search_keyword)
                await asyncio.sleep(0.05)

                group_books = {}
                books_list = []
                if not books:
                    if self._active:
                        self.empty_signal.emit(search_keyword)
                    return {}

                for book in books:
                    self.book_idx_counter += 1
                    book.name = PresetHtmlEl.sub(book.name)
                    book.idx = self.book_idx_counter
                    book.search_keyword = search_keyword
                    book.group_idx = group_idx + 1  # 记录属于哪个搜索组
                    group_books[book.idx] = book
                    books_list.append(book)
                if self._active:
                    self.group_signal.emit(group_idx + 1, books_list)
                return group_books
            except asyncio.CancelledError:
                return {}
            except Exception as e:
                err_msg = rf"{res.GUI.Clip.get_info_error}({search_keyword}): [{type(e).__name__}] {str(e)}"
                if self._active:
                    self.error_signal.emit(err_msg, traceback.format_exc())
                return {}

        tasks = [
            asyncio.create_task(fetch_single(idx, keyword))
            for idx, keyword in enumerate(self.tasks)
        ]
        self._pending_tasks = tasks
        try:
            results = await asyncio.gather(*tasks)
        finally:
            self._pending_tasks = []

        for result in results:
            if result:
                total.update(result)  # 合并所有book到total字典中
        return total
