import asyncio
from urllib.parse import urlparse
from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from qfluentwidgets import InfoBar, InfoBarPosition

from assets import res as ori_res
from utils.chore import extract_domains
from utils.config.qc import cgs_cfg
from GUI.tools.domain import DomainToolView


class DomainTestThread(QThread):
    results_ready = Signal(set, set)
    error_occurred = Signal(str)

    def __init__(self, domains, provider_cls):
        super().__init__()
        self._domains = domains
        self._provider_cls = provider_cls

    def cancel(self):
        self.requestInterruption()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(
                asyncio.gather(
                    *[self._provider_cls.test_aviable_domain(d) for d in self._domains],
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


class PublishUrlThread(QThread):
    """跑一遍 provider_cls.by_publish()（多候选并行竞速），首个可用域名胜出。"""
    results_ready = Signal(set, set)
    error_occurred = Signal(str)

    def __init__(self, provider_cls):
        super().__init__()
        self._provider_cls = provider_cls

    def cancel(self):
        self.requestInterruption()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            domain = loop.run_until_complete(self._provider_cls.by_publish())
            if self.isInterruptionRequested():
                return
            available = {domain} if domain else set()
            self.results_ready.emit(available, set())
        except Exception as e:
            if self.isInterruptionRequested():
                return
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

    @Slot(str)
    def tpp(self, text):
        self._mgr.set_publish_url(text)

    @Slot(str)
    def publishAccess(self, url):
        self._mgr.open_publish_access(url)


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
        gui_site_runtime = self.gui.gui_site_runtime
        if gui_site_runtime is None:
            raise RuntimeError("gui_site_runtime unavailable for publish domain test")
        provider_cls = gui_site_runtime.provider_cls
        self._current_view = DomainToolView(self.gui)
        self.gui.BrowserWindow.domain_v = self._current_view
        self._current_thread = DomainTestThread(domains, provider_cls)
        self._current_view.show_loading()
        self._current_thread.results_ready.connect(
            lambda av, un: self._on_results_ready(current_id, av, un)
        )
        self._current_thread.error_occurred.connect(
            lambda err: self._on_error(current_id, err)
        )
        self._current_thread.finished.connect(lambda: self._on_thread_finished(current_id))
        self._current_thread.start()

    def server_mode_switch_blockers(self) -> list[str]:
        thread = self._current_thread
        if thread is not None and thread.isRunning():
            return ["domain test"]
        return []

    def set_publish_url(self, text):
        """发布页地址输入位：持久化到 qc.json 并立即跑一遍 by_publish 竞速。空串=清除用户设置。"""
        url = str(text or "").strip()
        gui_site_runtime = self.gui.gui_site_runtime
        if gui_site_runtime is None:
            raise RuntimeError("gui_site_runtime unavailable for publish url set")
        tools_res = ori_res.GUI.Tools
        if not url:
            cgs_cfg.publish.set_url(gui_site_runtime.name, "")
            InfoBar.success(
                title='', content="已清除用户发布页地址，回退程序静态默认",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=4000, parent=self.gui.BrowserWindow
            )
            return
        if urlparse(url).scheme not in ("http", "https"):
            InfoBar.error(
                title='', content=f"{tools_res.doamin_error_tip}\n发布页地址需以 http:// 或 https:// 开头",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=7500, parent=self.gui.BrowserWindow
            )
            return
        self._task_id += 1
        current_id = self._task_id
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.cancel()
        cgs_cfg.publish.set_url(gui_site_runtime.name, url)
        self._current_view = DomainToolView(self.gui)
        self.gui.BrowserWindow.domain_v = self._current_view
        self._current_thread = PublishUrlThread(gui_site_runtime.provider_cls)
        self._current_view.show_loading()
        self._current_thread.results_ready.connect(
            lambda av, un: self._on_results_ready(current_id, av, un)
        )
        self._current_thread.error_occurred.connect(
            lambda err: self._on_error(current_id, err)
        )
        self._current_thread.finished.connect(lambda: self._on_thread_finished(current_id))
        self._current_thread.start()

    def open_publish_access(self, url):
        """WebChannel 反调：用本机系统浏览器打开发布页地址。"""
        raw = str(url or "").strip()
        if not raw:
            return
        if urlparse(raw).scheme not in ("http", "https"):
            tools_res = ori_res.GUI.Tools
            InfoBar.error(
                title='', content=f"{tools_res.doamin_error_tip}\n发布页地址需以 http:// 或 https:// 开头",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=7500, parent=self.gui.BrowserWindow
            )
            return
        QDesktopServices.openUrl(QUrl(raw))

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
