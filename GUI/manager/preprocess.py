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
from utils.website.preprocess import run_script_preprocess, site_db_path
from variables import SPIDERS, VER, Spider


def _script_preprocess_task(progress_callback=None):
    """script 入口流的任务体：与站点流分开，不经 gui_site_runtime。"""
    return run_script_preprocess(conf_state=conf, progress_callback=progress_callback)


class PreprocessManager(QObject):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.show_err = conf.log_level.lower() == "debug"
        self.task_manager = AsyncTaskManager(gui, gui)
        self._switch_generation = 0
        # 流程标识：站点流为站点索引；script 入口流为 None（script 不是站点，见 _is_current_flow）。
        self._active_preprocess: tuple[int | None, int] | None = None
        # infobar 落点按触发来源分流：站点流打 SpiderGUI 的 showArea；script 入口流由
        # run_script_entry 改置工作区窗（cell 所在窗，挡在 SpiderGUI 前，打 SpiderGUI 看不见）。
        self._infobar_host = self.gui.showArea

    def _next_generation(self):
        self._switch_generation += 1
        self.task_manager.cancel_all_tasks()
        return self._switch_generation

    def handle_choosebox_changed(self, index: int, gui_site_runtime: GuiSiteRuntime | None):
        generation = self._next_generation()
        # 站点流：提示落点回到 SpiderGUI 的 showArea（上一轮 script 入口流可能改置过工作区窗）
        self._infobar_host = self.gui.showArea
        self._active_preprocess = (index, generation)
        self._sync_preview_runtime(index, gui_site_runtime, runtime_ready=False)
        self._start_preprocess(index, generation)

        if index in Spider.aggr():
            self._add_aggr_search()
        if index in Spider.clip():
            self.gui.clipBtn.setVisible(True)
            self.gui.clipBtn.setEnabled(1)

    def run_script_entry(self):
        """acggrCell 触发点：script 预处理（服务/依赖/数据检查）→ infobar → 开 scriptWin。

        script 不是站点：不借伪站点索引、也不与 chooseBox 选中态挂钩（用户没选任何站点），
        故货币判据只认 generation + 工作区窗存活（见 _is_current_flow）。提示落点改置
        工作区窗——cell 在该窗内，该窗挡在 SpiderGUI 前。
        """
        generation = self._next_generation()
        self._infobar_host = getattr(self.gui, "toolWorkspaceWindow", None) or self.gui.showArea
        self._active_preprocess = (None, generation)
        self.task_manager.execute_simple_task(
            task_func=_script_preprocess_task,
            success_callback=lambda result: self._on_preprocess_success(None, generation, result),
            error_callback=lambda error: self._on_preprocess_error(None, generation, error),
            show_error_info=self.show_err,
            tooltip_title=f"{self.gui.res.Script.site_name} 预处理", tooltip_content="处理中...",
            task_id=f"preprocess_script_{generation}",
        )

    def _sync_preview_runtime(self, index: int, gui_site_runtime: GuiSiteRuntime | None, *, runtime_ready: bool):
        if index not in SPIDERS or gui_site_runtime is None or not runtime_ready:
            return self.gui.preview_mgr.handle_choosebox_changed(index, None)
        self.gui.preview_mgr.handle_choosebox_changed(index, gui_site_runtime)

    def _start_preprocess(self, index: int, generation: int):
        def task(progress_callback=None):
            gui_site_runtime = self.gui.gui_site_runtime
            if gui_site_runtime is None:
                raise RuntimeError("gui_site_runtime unavailable for preprocess flow")
            return gui_site_runtime.preprocess(conf_state=conf, progress_callback=progress_callback)

        self.task_manager.execute_simple_task(
            task_func=task, success_callback=lambda result: self._on_preprocess_success(index, generation, result),
            error_callback=lambda error: self._on_preprocess_error(index, generation, error), show_error_info=self.show_err,
            tooltip_title=f"{SPIDERS.get(index, str(index))} 预处理", tooltip_content="处理中...",
            task_id=f"preprocess_{index}_{generation}",
        )

    def _on_preprocess_success(self, index: int | None, generation: int, result: PreprocessResult):
        try:
            if not self._is_current_flow(index, generation):
                return
            if not isinstance(result, PreprocessResult):
                raise TypeError(f"unexpected preprocess result: {type(result)!r}")

            if index is not None:
                self._apply_site_preprocess_result(index, result)

            for message in result.messages:
                self._display_message(message)
            for action in result.actions:
                self._apply_action(action, index, generation)
        finally:
            self._clear_active_preprocess(index, generation)

    def _apply_site_preprocess_result(self, index: int, result: PreprocessResult):
        """站点流专属收尾：script 入口流无站点，故无域刷新 / 预览运行时 / block_search。"""
        if result.domain and index in SPIDERS:
            self._refresh_runtime_domain(index, result.domain)
        self._sync_preview_runtime(index, self.gui.gui_site_runtime, runtime_ready=result.runtime_ready)
        if result.block_search:
            self.gui.disable_start()

    def _on_preprocess_error(self, index: int | None, generation: int, error: str):
        try:
            if not self._is_current_flow(index, generation):
                return
            if index is not None:
                self._sync_preview_runtime(index, None, runtime_ready=False)
            # script 入口流同样收口搜索入口（与旧伪站点路径同语义：index=None ≠ HITOMI）。
            if index != Spider.HITOMI:
                self.gui.disable_start()
            self.gui.say("<br>❌ 预处理执行失败，请查看日志")
            self.gui.log.error(error)
        finally:
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
                duration=message.get("duration", -1 if level == "error" else 2500), parent=message.get("parent", self._infobar_host),
            )
            return
        if channel == "custom":
            CustomInfoBar.show(
                title=message.get("title", ""), content=text, parent=message.get("parent", self._infobar_host), url=message["url"], url_name=message["url_name"],
                _type={"success": "SUCCESS", "info": "INFORMATION", "warning": "WARNING", "error": "ERROR"}[level],
                position=message.get("position", InfoBarPosition.BOTTOM), duration=message.get("duration", -1),
            )
            return
        raise ValueError(f"unsupported preprocess message channel: {channel!r}")

    def _apply_action(self, action: dict, index: int | None, generation: int):
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
            script_entry_state = action.get("script_entry_state")
            delay_ms = max(0, int(action.get("delay_ms", 0) or 0))
            if delay_ms:
                return safe_single_shot(
                    delay_ms,
                    lambda state=script_entry_state, action_index=index, action_generation=generation: self._open_script_window_if_current(
                        action_index, action_generation, state,
                    ),
                )
            return self.gui.open_scriptWin(script_entry_state=script_entry_state)
        if action_type == "launch_update_flow":
            _UpdateLauncher(VER).run()
            self.gui.close()
            return
        raise ValueError(f"unsupported preprocess action: {action_type!r}")

    def _open_script_window_if_current(self, index: int | None, generation: int, script_entry_state: dict | None):
        if not self._is_current_flow(index, generation):
            return
        self.gui.open_scriptWin(script_entry_state=script_entry_state)

    def _is_current_flow(self, index: int | None, generation: int) -> bool:
        """货币判据：generation 未过期，且触发来源仍成立。

        - 站点流（index 为站点索引）：chooseBox 仍选中该站点。
        - script 入口流（index=None）：用户没在 chooseBox 选任何东西，只认工作区窗存活
          （窗关 → gui.toolWorkspaceWindow 置 None，即用户已离开该入口）。
        """
        if generation != self._switch_generation:
            return False
        if index is None:
            return getattr(self.gui, "toolWorkspaceWindow", None) is not None
        return self.gui.chooseBox.currentIndex() == index

    def _add_hitomi_tool(self):
        # CGS011: hitomi.db 受管预设资产的落盘状态即挂载门；CGS006 P4: 窗按需建，页随预处理链路挂。
        if not site_db_path("hitomi").exists():
            return
        self.gui.request_tool_page("htInterface")
        self.gui.htBtn.setVisible(True)

    def _add_aggr_search(self):
        # CGS006 P4: 窗按需建，页随站点选择/预处理链路挂，不等按钮点击。
        self.gui.request_tool_page("asInterface")
        self.gui.aggrBtn.setVisible(True)

    def server_mode_switch_blockers(self) -> list[str]:
        blockers = []
        if self._active_preprocess is not None:
            blockers.append("preprocess")
        preprocess_tasks = [task_id for task_id in self.task_manager.get_running_tasks() if str(task_id).startswith("preprocess_")]
        if preprocess_tasks:
            blockers.append("preprocess task")
        return blockers

    def cleanup(self):
        self._next_generation()
        self._active_preprocess = None
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

    def _clear_active_preprocess(self, index: int | None, generation: int):
        if self._active_preprocess == (index, generation):
            self._active_preprocess = None
