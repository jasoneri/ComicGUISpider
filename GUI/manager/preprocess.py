from dataclasses import replace

import httpx
from PySide6.QtCore import Qt, QObject
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.browser_window import BrowserWindow
from GUI.core.theme import setupTheme
from GUI.manager import _UpdateLauncher
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components import CustomInfoBar
from GUI.types import SearchContextSnapshot
from utils import conf
from utils.website.contracts import PreprocessResult
from utils.website.preprocess import run_site_preprocess
from variables import SPIDERS, VER, Spider


data_cli = None


class PreprocessManager(QObject):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.show_err = conf.log_level.lower() == "debug"
        self.task_manager = AsyncTaskManager(gui)
        self._switch_generation = 0

    def _next_generation(self):
        self._switch_generation += 1
        self.task_manager.cancel_all_tasks()
        return self._switch_generation

    def _reset_data_cli(self, proxies: list[str]):
        global data_cli
        if data_cli is not None:
            data_cli.close()
        transport = dict(proxy=f"http://{proxies[0]}", retries=2) if proxies else dict(retries=2)
        data_cli = httpx.Client(transport=httpx.HTTPTransport(**transport))

    def handle_choosebox_changed(self, index: int, snapshot: SearchContextSnapshot | None):
        generation = self._next_generation()
        self._reset_data_cli(list(snapshot.proxies) if snapshot else [])

        gateway = getattr(self.gui, "site_gateway", None)
        if index in {Spider.MANGA_COPY, Spider.JM, Spider.WNACG, Spider.EHENTAI, Spider.HITOMI, 7} or (
            gateway and getattr(gateway, "supports_test_index", False)
        ):
            self._start_preprocess(index, generation)

        if index in Spider.aggr():
            self._add_aggr_search()
        if index in Spider.clip():
            self.gui.clipBtn.setVisible(True)
            self.gui.clipBtn.setEnabled(1)

    def _start_preprocess(self, index: int, generation: int):
        def task(progress_callback=None):
            gateway = getattr(self.gui, "site_gateway", None)
            if gateway is not None and hasattr(gateway, "preprocess"):
                return gateway.preprocess(
                    index,
                    conf_state=conf,
                    data_client=data_cli,
                    progress_callback=progress_callback,
                )
            return run_site_preprocess(
                index,
                gateway=gateway,
                conf_state=conf,
                data_client=data_cli,
                progress_callback=progress_callback,
            )

        site_name = "kemono" if index == 7 else SPIDERS.get(index, str(index))
        self.task_manager.execute_simple_task(
            task_func=task,
            success_callback=lambda result: self._on_preprocess_success(index, generation, result),
            error_callback=lambda error: self._on_preprocess_error(index, generation, error),
            show_error_info=self.show_err,
            tooltip_title=f"{site_name} 预处理",
            tooltip_content="处理中...",
            task_id=f"preprocess_{index}_{generation}",
        )

    def _on_preprocess_success(self, index: int, generation: int, result: PreprocessResult):
        if not self._is_current_site(index, generation):
            return
        if not isinstance(result, PreprocessResult):
            raise TypeError(f"unexpected preprocess result: {type(result)!r}")

        if result.domain and index in SPIDERS:
            self._refresh_snapshot_domain(index, SPIDERS[index], result.domain)
        if result.block_search:
            self.gui.disable_start()

        for message in result.messages:
            self._display_message(message)
        for action in result.actions:
            self._apply_action(action)

    def _on_preprocess_error(self, index: int, generation: int, error: str):
        if not self._is_current_site(index, generation):
            return
        if index != Spider.HITOMI:
            self.gui.disable_start()
        self.gui.say("<br>❌ 预处理执行失败，请查看日志")
        logger = getattr(self.gui, "log", None)
        if logger is not None:
            logger.error(error)

    def _display_message(self, message: dict):
        channel = message.get("channel", "text")
        level = str(message.get("level", "info")).lower()
        text = str(message.get("text", ""))
        text_key = message.get("text_key")
        if not text and text_key:
            site_res = getattr(self.gui, "res", None)
            text = getattr(site_res, text_key)
        if channel == "text":
            self.gui.say(text, ignore_http=bool(message.get("ignore_http", False)))
            return
        if channel == "infobar":
            factory = {
                "success": InfoBar.success,
                "info": InfoBar.info,
                "warning": InfoBar.warning,
                "error": InfoBar.error,
            }[level]
            factory(
                title=message.get("title", ""),
                content=text,
                orient=Qt.Horizontal,
                isClosable=True,
                position=message.get("position", InfoBarPosition.BOTTOM),
                duration=message.get("duration", -1 if level == "error" else 2500),
                parent=message.get("parent", self.gui.showArea),
            )
            return
        if channel == "custom":
            CustomInfoBar.show(
                title=message.get("title", ""),
                content=text,
                parent=message.get("parent", self.gui.showArea),
                url=message["url"],
                url_name=message["url_name"],
                _type={
                    "success": "SUCCESS",
                    "info": "INFORMATION",
                    "warning": "WARNING",
                    "error": "ERROR",
                }[level],
            )
            return
        raise ValueError(f"unsupported preprocess message channel: {channel!r}")

    def _apply_action(self, action: dict):
        action_type = action.get("type")
        if action_type == "open_publish_flow":
            self.gui.do_publish()
            return
        if action_type == "attach_ehentai_runtime":
            runtime = action["runtime"]
            self.gui.sut = runtime
            BrowserWindow.eh_kits = runtime
            return
        if action_type == "add_hitomi_tool":
            self._try_add_hitomi_tool()
            return
        if action_type == "open_script_window":
            self.gui.hide()
            from GUI.script import ScriptWindow

            script_window = ScriptWindow(self.gui)
            setupTheme(script_window.kemonoInterface)
            script_window.show()
            return
        if action_type == "launch_update_flow":
            _UpdateLauncher(VER, script=True).run()
            self.gui.close()
            return
        raise ValueError(f"unsupported preprocess action: {action_type!r}")

    def _is_current_site(self, index: int, generation: int) -> bool:
        return generation == self._switch_generation and self.gui.chooseBox.currentIndex() == index

    def _try_add_hitomi_tool(self):
        if hasattr(self.gui, "toolWin"):
            self.gui.toolWin.addHitomiTool()

    def _add_aggr_search(self):
        if not hasattr(self.gui.toolWin, "asInterface"):
            self.gui.toolWin.addAggrSearchView()
        self.gui.aggrBtn.setVisible(True)

    def cleanup(self):
        global data_cli
        self._next_generation()
        self.task_manager.reset()
        if data_cli is not None:
            data_cli.close()
            data_cli = None

    def _refresh_snapshot_domain(self, index: int, name: str, domain: str | None):
        if not domain:
            return
        snapshot = getattr(self.gui, "_search_context", None)
        if snapshot is None or snapshot.site_index != index:
            return
        domains = {**snapshot.domains, name: domain}
        updated = replace(snapshot, domains=domains)
        self.gui.update_search_context(updated)
