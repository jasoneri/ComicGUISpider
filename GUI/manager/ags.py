import contextlib
import json
from pathlib import Path

from PySide6.QtCore import QTimer

from utils import conf
from utils.processed_class import PreviewByFixHtml
from GUI.thread import AggrSearchThread
from GUI.core.font import font_color
from assets import res


class _AggrSearchRun:
    _RENDER_POLL_INTERVAL_MS = 250

    def __init__(self, manager, search_keywords):
        self.manager = manager
        self.gui = manager.gui
        self.search_keywords = list(search_keywords)
        self.gui.tf = PreviewByFixHtml.created_temp_html()
        self.preview_path = Path(self.gui.tf).resolve()
        self.gui.set_preview()
        self.browser = self.gui.BrowserWindow
        self.browser.resize(self.browser.width() + 20, 860)
        self.thread = AggrSearchThread(
            self.gui, self.search_keywords,
            thread_site_runtime=self.gui.gui_site_runtime.create_thread_site_runtime(),
        )
        self.manager.aggrSearchThread = self.thread

    def start(self):
        self.browser.set_close_handler(self._on_browser_closed)
        self.browser.view.urlChanged.connect(self._on_url_changed)
        self.thread.group_signal.connect(self._on_group_data)
        self.thread.total_signal.connect(self._on_total_data)
        self.thread.empty_signal.connect(self._on_empty_search)
        self.thread.error_signal.connect(self._on_search_error)
        self.thread.finished.connect(lambda thread=self.thread: self._on_thread_finished(thread))
        self.thread.finished.connect(self.thread.deleteLater)
        self.browser.view.loadFinished.connect(self._start_thread_once)
        self.browser.show()

    def stop(self):
        self._disconnect_browser_signals()
        self.browser.set_close_handler(None)
        thread = self.thread
        self.thread = None
        if thread is None:
            return
        thread.stop()
        if self.manager.aggrSearchThread is thread:
            self.manager.aggrSearchThread = None
        if not thread.isRunning():
            thread.deleteLater()

    def is_current(self):
        return self.manager._run is self

    def _disconnect_browser_signals(self):
        with contextlib.suppress(TypeError, RuntimeError):
            self.browser.view.loadFinished.disconnect(self._start_thread_once)
        with contextlib.suppress(TypeError, RuntimeError):
            self.browser.view.urlChanged.disconnect(self._on_url_changed)

    def _start_thread_once(self, ok):
        with contextlib.suppress(TypeError, RuntimeError):
            self.browser.view.loadFinished.disconnect(self._start_thread_once)
        if not ok or not self.is_current():
            return
        self.thread.start()

    def _on_group_data(self, group_idx, books_list):
        if not self.is_current():
            return
        keyword = books_list[0].search_keyword
        js_parts = [f'addFixGroup({json.dumps(group_idx)},{json.dumps(keyword, ensure_ascii=False)})']

        for book in books_list:
            self.manager.infos[str(book.idx)] = book
            options = {'with_follow': False}
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
                ep_options = {'with_follow': False}
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

        self.browser.page_runtime.run_js(';'.join(js_parts))

    def _on_total_data(self, total_data):
        if not self.is_current():
            return
        if not total_data:
            self.browser.hide()
            self.gui.say(font_color(res.GUI.Clip.all_fail, cls='theme-err'), ignore_http=True)
            self.gui.say(font_color(rf"<br>{res.GUI.Clip.view_log} [{conf.log_path}\GUI.log]", cls='theme-err', size=3))
            return

        iterations = 0
        max_iterations = 7 * len(self.search_keywords)

        def check_render_completion():
            nonlocal iterations
            if not self.is_current():
                return
            if iterations >= max_iterations:
                print("[aggr search tasks loop]❌over max_iterations, fail.")
                self._snapshot_total_data(total_data)
                return
            iterations += 1
            self.browser.page_runtime.run_js("checkDoneTasks();", handle_render_check_result)

        def handle_render_check_result(num):
            if not self.is_current():
                return
            if num >= len(total_data):
                print("[aggr search tasks loop]✅finsh.")
                self._snapshot_total_data(total_data)
                return
            QTimer.singleShot(self._RENDER_POLL_INTERVAL_MS, check_render_completion)

        delay_ms = 1200 if len(total_data) == 1 else 350
        QTimer.singleShot(delay_ms, check_render_completion)

    def _snapshot_total_data(self, total_data):
        if not self.is_current():
            return

        def refresh_tf(html):
            if not self.is_current():
                return
            with open(self.gui.tf, 'w', encoding='utf-8') as f:
                f.write(html)
            if conf.isDeduplicate:
                downloaded_md5s = self.gui.download_state.downloaded_md5s(self.manager.infos.values())
                dled_bidxes = [
                    key for key, obj in self.manager.infos.items()
                    if obj.id_and_md5()[1] in downloaded_md5s and not obj.episodes
                ]
                if dled_bidxes:
                    self.browser.page_runtime.run_js(f'previewRuntime.markDownloaded({json.dumps(dled_bidxes)},[])')
            if self.browser.topHintBox.isChecked():
                self.browser.topHintBox.click()
            if len(total_data) < len(self.search_keywords):
                self.gui.activateWindow()
                self.gui.say(f"➖ {self.gui.res.Clip.partial_fail}")

        self.browser.page_runtime.page_to_html(refresh_tf, description="ags HTML snapshot")

    def _on_empty_search(self, search_keyword):
        if self.is_current():
            self.gui.say(f"🅾️{res.GUI.Ags.empty_search}: {search_keyword}")

    def _on_search_error(self, err_msg, trace_text):
        if not self.is_current():
            return
        self.gui.log.error(trace_text)
        self.gui.say(font_color(err_msg + '<br>', cls='theme-err'), ignore_http=True)

    def _on_thread_finished(self, thread):
        if self.thread is thread:
            self.thread = None
        if self.manager.aggrSearchThread is thread:
            self.manager.aggrSearchThread = None

    def _on_browser_closed(self, _browser, event):
        self.manager.cancel_active_run()
        event.accept()

    def _on_url_changed(self, url):
        if not self.is_current():
            return
        url_text = url.toString()
        if not url_text or url_text == "about:blank":
            return
        if url.isLocalFile() and Path(url.toLocalFile()).resolve() == self.preview_path:
            return
        self.manager.cancel_active_run()


class AggrSearchManager:
    def __init__(self, gui, *args, **kwargs):
        super(AggrSearchManager, self).__init__(*args, **kwargs)
        self.gui = gui

        self.is_triggered = False
        self.tasks = []  # 存储搜索关键词列表
        self.infos = {}  # 存储完整的book信息，由single_aggr_search_data构建
        self.aggrSearchThread = None
        self.extractor = None  # 从 AggrSearchView 传递过来的 extractor
        self._run = None

    def run(self, search_keywords):
        self._stop_current_run()
        self.tasks = list(search_keywords)
        self.infos = {}
        run = _AggrSearchRun(self, self.tasks)
        self.gui.update_search_ui(controls_blocked=True)
        self.is_triggered = True
        self._run = run
        run.start()

    def submit_browser_selection(self):
        run = self._run
        selected_list = [
            self.infos[str(unique_id)]
            for unique_id in run.browser.output
        ]
        self.extractor.remove_list(selected_list)
        self.gui.sel_mgr.submit_decision("BOOK", selected_list, flow_stage=self.gui.flow_stage)
        self.cancel_active_run()

    def reset(self):
        self.cancel_active_run()
        self.tasks = []
        self.infos = {}

    def cancel_active_run(self):
        self._stop_current_run()
        self.is_triggered = False
        self.gui.update_search_ui(controls_blocked=False)

    def _stop_current_run(self):
        run = self._run
        self._run = None
        if run is not None:
            run.stop()

    def server_mode_switch_blockers(self) -> list[str]:
        thread = self.aggrSearchThread
        if thread is not None and thread.isRunning():
            return ["aggregate search"]
        return []
