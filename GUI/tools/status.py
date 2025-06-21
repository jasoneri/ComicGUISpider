import json
import asyncio
import hashlib

import httpx
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, StrongBodyLabel,
    InfoBadge, InfoBadgePosition, InfoLevel, HyperlinkButton,
    FluentIcon as FIF, InfoBar, InfoBarPosition
)

from assets import res as ori_res
from variables import SPIDERS
from utils import ori_path, conf
from GUI.manager import AsyncTaskManager, TaskConfig

tools_res = ori_res.GUI.Tools

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
}
transport_kw = dict(retries=0)


class Api:
    raw_f = "https://gitee.com/json_eri/ComicGUISpider/raw/GUI"
    asset_f = "https://gitee.com/json_eri/ComicGUISpider/releases/tag/v2.0.0"

    @classmethod
    def raw(cls, filep):
        return f"{cls.raw_f}/{filep}"
    
    @classmethod
    def asset(cls, filen):
        return f"{cls.asset_f}/{filen}"
    
    @staticmethod
    def cloudflare_status(web=None, aggr=False):
        if  aggr:
            return "https://cgs-status-badges.pages.dev/aggr_status.json"
        return f"https://cgs-status-badges.pages.dev/status_{web}.json"


async def fetch(url, _transport_kw={}):
    try:
        async with httpx.AsyncClient(timeout=7, headers=headers,
                transport=httpx.AsyncHTTPTransport(**transport_kw, **_transport_kw)) as cli:
            _resp = await cli.get(url)
            _resp_body = _resp.content
    except Exception as e:
        raise e
    return _resp_body


class StatusToolService:
    """状态工具服务类 - 使用异步任务管理器重构"""
    webs = SPIDERS.values()

    def __init__(self, gui):
        self.gui = gui
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def _fetch_aggr_status(self):
        try:
            resp_body = await fetch(Api.cloudflare_status(aggr=True),
                                    dict(proxy=f"http://{conf.proxies[0]}") if conf.proxies else {})
            resp_json = json.loads(resp_body)
            return resp_json
        except Exception as e:
            return None

    def fetch_all_status(self):
        try:
            resp_json = self.loop.run_until_complete(self._fetch_aggr_status())
            if not resp_json:
                return []
            return [{"web": web, **info} for web, info in resp_json.items()]
        except Exception as e:
            return []

    async def _update_file(self, local_f, url):
        def to_md5(body: bytes):
            return hashlib.md5(body).hexdigest()
        def normalize_line_endings(content: bytes) -> bytes:
            return content.replace(b'\r\n', b'\n')
        resp_bytes = await fetch(url)
        local_bytes = local_f.read_bytes()
        if to_md5(normalize_line_endings(local_bytes)) != to_md5(resp_bytes):
            with open(local_f, 'w', encoding='utf-8', newline='\n') as f:
                f.write(resp_bytes.decode('utf-8'))
            return True
        return False

    def update_files(self, cfiles, progress_callback=None):
        try:
            local_files = [ori_path.joinpath(cfile) for cfile in cfiles]
            urls = [Api.raw(cfile) for cfile in cfiles]
            async def _update_with_progress():
                tasks = []
                for i, (local_f, url, cfile) in enumerate(zip(local_files, urls, cfiles)):
                    if progress_callback:
                        progress_callback(f"更新文件 {i+1}/{len(cfiles)}: {cfile}")
                    tasks.append(self._update_file(local_f, url))
                results = await asyncio.gather(*tasks)
                return any(results)
            return self.loop.run_until_complete(_update_with_progress())
        except Exception as e:
            raise e


class StatusToolView(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self)
        self.gui = parent
        self.service = StatusToolService(parent)
        self.task_manager = AsyncTaskManager(self)
        self.init_ui()

    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)

        first_row = QHBoxLayout()
        desc_label = StrongBodyLabel(tools_res.status_desc)
        first_row.addWidget(desc_label)

        self.second_row = QHBoxLayout()
        linkBtn = HyperlinkButton(FIF.LINK, "https://jasoneri.github.io/ComicGUISpider/", "CGS")
        self.second_row.insertWidget(1, linkBtn)
        self.second_row.addStretch()

        third_row = QHBoxLayout()
        self.copy2Btn = PrimaryPushButton(FIF.UPDATE, "Update 拷贝", self)
        self.copy2Btn.clicked.connect(self.update_copy2_files)
        self.hitomiBtn = PrimaryPushButton(FIF.UPDATE, "Update Hitomi", self)
        self.hitomiBtn.clicked.connect(self.update_hitomi_files)
        third_row.addWidget(self.copy2Btn)
        third_row.addWidget(self.hitomiBtn)

        for row in (first_row, self.second_row, third_row):
            self.main_layout.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        if len(self.gui.webs_status) < len(StatusToolService.webs):
            self.fetch_status()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.task_manager.cancel_all_tasks()

    def closeEvent(self, event):
        super().closeEvent(event)
        self.task_manager.cleanup()

    def fetch_status(self):
        def on_success(results):
            self.handle_status_results(results)

        def on_error(error):
            self.handle_status_results([])

        # 使用异步任务管理器执行状态获取
        self.task_manager.execute_simple_task(
            task_func=self.service.fetch_all_status,
            success_callback=on_success,
            error_callback=on_error,
            tooltip_title=tools_res.status_fetching, tooltip_parent=self,
            task_id="fetch_status"
        )

    def handle_status_results(self, resps_json):
        for resp_json in resps_json:
            level = InfoLevel.SUCCESS if resp_json['message']=="pass" else InfoLevel.ERROR
            self.second_row.insertWidget(1, InfoBadge.make(
                f"「 {resp_json['label']} 」{resp_json['web']} ",
                parent=self, level=level,
                target=self.second_row, position=InfoBadgePosition.RIGHT
            ))
            self.gui.webs_status.append(resp_json['web'])

        # 检查是否有网站状态异常
        if len(self.gui.webs_status) < len(StatusToolService.webs):
            InfoBar.warning(
                title='', content=tools_res.status_web_erratic,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=4000, parent=self
            )

    def update_copy2_files(self):
        config = TaskConfig(
            task_func=self.service.update_files,
            success_callback=lambda _: self.handle_update_result(_),
            error_callback=lambda _: self.handle_update_result(False),
            tooltip_title="更新拷贝文件", tooltip_content="正在更新拷贝相关文件...",
            cfiles=["utils/website/__init__.py", "ComicSpider/spiders/kaobei.py"]
        )
        self.task_manager.execute_task("update_copy2", config)

    def update_hitomi_files(self):
        config = TaskConfig(
            task_func=self.service.update_files,
            success_callback=lambda _: self.handle_update_result(_),
            error_callback=lambda _: self.handle_update_result(False),
            tooltip_title="更新Hitomi文件", tooltip_content="正在更新Hitomi相关文件...",
            cfiles=["utils/website/hitomi/__init__.py", "ComicSpider/spiders/hitomi.py"]
        )
        self.task_manager.execute_task("update_hitomi", config)

    def handle_update_result(self, updated):
        sec = 5
        if updated:
            InfoBar.success(
                title='', content=tools_res.reboot_tip % str(sec),
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=sec*1000, parent=self.gui.textBrowser
            )
            self.gui.toolWin.close()
            QTimer.singleShot(6000, self.gui.retrybtn.click)
        else:
            InfoBar.info(
                title='', content=tools_res.status_no_update,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=sec*1000, parent=self
            )
