from PySide6.QtCore import Qt, QObject
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.browser_window import BrowserWindow
from GUI.core.timer import safe_single_shot
from GUI.manager import _UpdateLauncher
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components import CustomInfoBar
from utils import conf
from utils.website.contracts import PreprocessResult
from utils.website.site_runtime import GuiSiteRuntime
from utils.website.preprocess import run_script_preprocess
from variables import SPIDERS, VER, Spider


class PreprocessManager(QObject):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.show_err = conf.log_level.lower() == "debug"
        self.task_manager = AsyncTaskManager(gui)
        self._switch_generation = 0
        self._active_preprocess: tuple[int, int] | None = None
        self._queued_search: tuple[int, int, str] | None = None

    def _next_generation(self):
        self._switch_generation += 1
        self.task_manager.cancel_all_tasks()
        return self._switch_generation

    def handle_choosebox_changed(self, index: int, gui_site_runtime: GuiSiteRuntime | None):
        generation = self._next_generation()
        self._active_preprocess = (index, generation)
        self._queued_search = None
        self._sync_preview_runtime(index, gui_site_runtime, runtime_ready=False)
        self._start_preprocess(index, generation)

        if index in Spider.aggr():
            self._add_aggr_search()
        if index in Spider.clip():
            self.gui.clipBtn.setVisible(True)
            self.gui.clipBtn.setEnabled(1)

    def _sync_preview_runtime(self, index: int, gui_site_runtime: GuiSiteRuntime | None, *, runtime_ready: bool):
        if index not in SPIDERS or gui_site_runtime is None or not runtime_ready:
            return self.gui.preview_mgr.handle_choosebox_changed(index, None)
        self.gui.preview_mgr.handle_choosebox_changed(index, gui_site_runtime)

    def _start_preprocess(self, index: int, generation: int):
        def task(progress_callback=None):
            if index == 7:
                return run_script_preprocess(conf_state=conf, progress_callback=progress_callback)
            gui_site_runtime = self.gui.gui_site_runtime
            if gui_site_runtime is None:
                raise RuntimeError("gui_site_runtime unavailable for preprocess flow")
            return gui_site_runtime.preprocess(conf_state=conf, progress_callback=progress_callback)

        site_name = "Script" if index == 7 else SPIDERS.get(index, str(index))
        self.task_manager.execute_simple_task(
            task_func=task, success_callback=lambda result: self._on_preprocess_success(index, generation, result),
            error_callback=lambda error: self._on_preprocess_error(index, generation, error), show_error_info=self.show_err,
            tooltip_title=f"{site_name} 预处理", tooltip_content="处理中...",
            task_id=f"preprocess_{index}_{generation}",
        )

    def _on_preprocess_success(self, index: int, generation: int, result: PreprocessResult):
        try:
            if not self._is_current_site(index, generation):
                return
            if not isinstance(result, PreprocessResult):
                raise TypeError(f"unexpected preprocess result: {type(result)!r}")

            if result.domain and index in SPIDERS:
                self._refresh_runtime_domain(index, result.domain)
            self._sync_preview_runtime(index, self.gui.gui_site_runtime, runtime_ready=result.runtime_ready)
            if result.block_search:
                self.gui.disable_start()

            for message in result.messages:
                self._display_message(message)
            for action in result.actions:
                self._apply_action(action)

            self._dispatch_queued_search(index, generation, ready=bool(result.runtime_ready and not result.block_search))
        finally:
            self._clear_active_preprocess(index, generation)

    def _on_preprocess_error(self, index: int, generation: int, error: str):
        try:
            if not self._is_current_site(index, generation):
                return
            self._sync_preview_runtime(index, None, runtime_ready=False)
            if index != Spider.HITOMI:
                self.gui.disable_start()
            self.gui.say("<br>❌ 预处理执行失败，请查看日志")
            self.gui.log.error(error)
        finally:
            self._clear_queued_search(index, generation)
            self._clear_active_preprocess(index, generation)

    def _display_message(self, message: dict):
        channel = message.get("channel", "text")
        level = str(message.get("level", "info")).lower()
        text = str(message.get("text", ""))
        text_key = message.get("text_key")
        if not text and text_key:
            text = getattr(self.gui.res, text_key)
        if channel == "text":
            self.gui.say(text, ignore_http=bool(message.get("ignore_http", False)))
            return
        if channel == "infobar":
            factory = {"success": InfoBar.success, "info": InfoBar.info, "warning": InfoBar.warning, "error": InfoBar.error}[level]
            factory(
                title=message.get("title", ""),
                content=text, orient=Qt.Horizontal, isClosable=True, position=message.get("position", InfoBarPosition.BOTTOM), 
                duration=message.get("duration", -1 if level == "error" else 2500), parent=message.get("parent", self.gui.showArea),
            )
            return
        if channel == "custom":
            CustomInfoBar.show(
                title=message.get("title", ""), content=text, parent=message.get("parent", self.gui.showArea), url=message["url"], url_name=message["url_name"],
                _type={"success": "SUCCESS", "info": "INFORMATION", "warning": "WARNING", "error": "ERROR"}[level],
            )
            return
        raise ValueError(f"unsupported preprocess message channel: {channel!r}")

    def _apply_action(self, action: dict):
        action_type = action.get("type")
        if action_type == "open_publish_flow":
            return self.gui.do_publish()
        if action_type == "attach_ehentai_runtime":
            runtime = action["runtime"]
            self.gui.sut = runtime
            BrowserWindow.eh_kits = runtime
            return
        if action_type == "add_hitomi_tool":
            return self._add_hitomi_tool()
        if action_type == "open_scriptWin":
            return self.gui.open_scriptWin()
        if action_type == "launch_update_flow":
            _UpdateLauncher(VER, script=True).run()
            self.gui.close()
            return
        raise ValueError(f"unsupported preprocess action: {action_type!r}")

    def _is_current_site(self, index: int, generation: int) -> bool:
        return generation == self._switch_generation and self.gui.chooseBox.currentIndex() == index

    def _add_hitomi_tool(self):
        self.gui.toolWin.addHitomiTool()
        self.gui.htBtn.setVisible(True)

    def _add_aggr_search(self):
        if not hasattr(self.gui.toolWin, "asInterface"):
            self.gui.toolWin.addAggrSearchView()
        self.gui.aggrBtn.setVisible(True)

    def sync_gui_site_runtime(self, gui_site_runtime: GuiSiteRuntime | None):
        _ = gui_site_runtime

    def queue_search_after_preprocess(self, index: int, keyword: str) -> bool:
        active_preprocess = self._active_preprocess
        if active_preprocess is None:
            return False
        active_index, generation = active_preprocess
        if active_index != index or self.gui.chooseBox.currentIndex() != index:
            return False
        self._queued_search = (generation, index, keyword)
        return True

    def cleanup(self):
        self._next_generation()
        self._active_preprocess = None
        self._queued_search = None
        self.task_manager.reset()

    def _refresh_runtime_domain(self, index: int, domain: str | None):
        if not domain:
            return
        gui_site_runtime = self.gui.gui_site_runtime
        if gui_site_runtime is None or gui_site_runtime.site_index != index:
            return
        self.gui.gui_site_runtime = gui_site_runtime.with_domain(domain)
        if getattr(self.gui, "BrowserWindow", None):
            self.gui.BrowserWindow.apply_standard_environment()

    def _dispatch_queued_search(self, index: int, generation: int, *, ready: bool):
        queued_search = self._queued_search
        if queued_search is None:
            return
        queued_generation, queued_index, keyword = queued_search
        if queued_generation != generation or queued_index != index:
            return
        self._queued_search = None
        if not ready:
            return
        safe_single_shot(0, lambda kw=keyword: self.gui.start_and_search(keyword=kw))

    def _clear_queued_search(self, index: int, generation: int):
        queued_search = self._queued_search
        if queued_search is None:
            return
        queued_generation, queued_index, _keyword = queued_search
        if queued_generation == generation and queued_index == index:
            self._queued_search = None

    def _clear_active_preprocess(self, index: int, generation: int):
        if self._active_preprocess == (index, generation):
            self._active_preprocess = None
