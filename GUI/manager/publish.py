import asyncio
from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread
from PySide6.QtWebChannel import QWebChannel
from qfluentwidgets import InfoBar, InfoBarPosition

from assets import res as ori_res
from utils.website import extract_domains
from GUI.tools.domain import DomainToolView


class DomainTestThread(QThread):
    results_ready = Signal(set, set)
    error_occurred = Signal(str)

    def __init__(self, domains, site_gateway):
        super().__init__()
        self._domains = domains
        self._site_gateway = site_gateway

    def cancel(self):
        self.requestInterruption()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(
                asyncio.gather(
                    *[self._site_gateway.test_aviable_domain(d) for d in self._domains],
                    return_exceptions=True
                )
            )
            if self.isInterruptionRequested():
                return
            hosts = set(r for r in results if r and not isinstance(r, Exception))
            available = hosts & self._domains
            unavailable = self._domains - available
            self.results_ready.emit(available, unavailable)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            loop.close()


class PublishBridge(QObject):
    def __init__(self, manager):
        super().__init__()
        self._mgr = manager

    @Slot(str)
    def tpd(self, texts):
        self._mgr.start_domain_test(texts)


class PublishDomainManager(QObject):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self._bridge = PublishBridge(self)
        self._channel = None
        self._channel_page = None
        self._current_thread = None
        self._current_view = None
        self._task_id = 0

    def setup_channel(self, page):
        if self._channel and self._channel_page is page:
            return
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)
        self._channel_page = page

    def start_domain_test(self, texts):
        self._task_id += 1
        current_id = self._task_id
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.cancel()
        domains = extract_domains(texts)
        if not domains:
            return
        gateway = self.gui.site_gateway
        if gateway is None:
            raise RuntimeError("site gateway unavailable for publish domain test")
        self._current_view = DomainToolView(self.gui)
        self.gui.BrowserWindow.domain_v = self._current_view
        self._current_thread = DomainTestThread(domains, gateway)
        self._current_view.show_loading()
        self._current_thread.results_ready.connect(
            lambda av, un: self._on_results_ready(current_id, av, un)
        )
        self._current_thread.error_occurred.connect(
            lambda err: self._on_error(current_id, err)
        )
        self._current_thread.finished.connect(lambda: self._on_thread_finished(current_id))
        self._current_thread.start()

    def _on_results_ready(self, task_id, available, unavailable):
        if task_id != self._task_id:
            return
        if self._current_view:
            self._current_view.display_results(available, unavailable)

    def _on_error(self, task_id, error):
        if task_id != self._task_id:
            return
        if self._current_view:
            self._current_view.dismiss_loading()
        tools_res = ori_res.GUI.Tools
        InfoBar.error(
            title='', content=f"{tools_res.doamin_error_tip}\n{error}",
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=7500, parent=self.gui.BrowserWindow
        )

    def _on_thread_finished(self, task_id):
        if task_id == self._task_id:
            if self._current_thread:
                self._current_thread.deleteLater()
            self._current_thread = None
