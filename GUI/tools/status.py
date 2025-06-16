import json
import asyncio
import hashlib

import httpx
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, StrongBodyLabel,
    InfoBadge, InfoBadgePosition, InfoLevel, HyperlinkButton, 
    FluentIcon as FIF, InfoBar, InfoBarPosition, StateToolTip
)

from assets import res as ori_res
from utils import ori_path, conf

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


class StatusToolThread(QThread):
    status_signal = pyqtSignal(list)  # 发送网站状态信息
    update_signal = pyqtSignal(bool)  # 发送更新结果
    error_signal = pyqtSignal(str)    # 发送错误信息
    webs = {"kaobei", "mangabz", "hitomi", "wnacg", "ehentai", "jm"}
    gui = None
    
    def __init__(self, parent):
        super().__init__()
        self.gui = parent
        self.loop = asyncio.get_event_loop()

    def run(self):
        try:
            results = self.loop.run_until_complete(self._fetch_all_status())
            self.status_signal.emit(results)
        except Exception as e:
            self.status_signal.emit([])

    def stop(self):
        self.wait()

    async def _fetch_aggr_status(self):
        try:
            resp_body = await fetch(Api.cloudflare_status(aggr=True), 
                                    dict(proxy=f"http://{conf.proxies[0]}") if conf.proxies else {})
            resp_json = json.loads(resp_body)
            return resp_json
        except Exception as e:
            return None

    async def _fetch_all_status(self):
        resp_json = await self._fetch_aggr_status()
        if not resp_json:
            return []
        return [{"web": web, **info} for web, info in resp_json.items()]

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

    async def _update_files(self, cfiles):
        local_files = [ori_path.joinpath(cfile) for cfile in cfiles]
        urls = [Api.raw(cfile) for cfile in cfiles]
        tasks = [self._update_file(local_f, url) for local_f, url in zip(local_files, urls)]
        results = await asyncio.gather(*tasks)
        self.update_signal.emit(any(results))

    def request_update(self, cfiles):
        self.loop.run_until_complete(self._update_files(cfiles))

    def copy2(self):
        cfiles = ["utils/website/__init__.py", "ComicSpider/spiders/kaobei.py"]
        self.request_update(cfiles)

    def hitomi(self):
        cfiles = ["utils/website/hitomi/__init__.py", "ComicSpider/spiders/hitomi.py"]
        self.request_update(cfiles)


class StatusToolView(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self)
        self.gui = parent
        self.stateTooltip = None
        self.bthread = StatusToolThread(parent)
        self.bthread.status_signal.connect(self.handle_status)
        self.bthread.update_signal.connect(self.handle_update)
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
        self.copy2Btn.clicked.connect(self.bthread.copy2)
        self.hitomiBtn = PrimaryPushButton(FIF.UPDATE, "Update Hitomi", self)
        self.hitomiBtn.clicked.connect(self.bthread.hitomi)
        third_row.addWidget(self.copy2Btn)
        third_row.addWidget(self.hitomiBtn)
        for row in (first_row, self.second_row, third_row):
            self.main_layout.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        if len(self.gui.webs_status) < len(StatusToolThread.webs):
            self.stateTooltip = StateToolTip(tools_res.status_fetching, tools_res.status_waiting, self)
            self.stateTooltip.move(self.gui.toolWin.width()-self.stateTooltip.width()-30, 20)
            self.stateTooltip.setState(False)
            self.stateTooltip.show()
            if not self.bthread.isRunning():
                self.bthread.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.bthread.stop()

    def closeEvent(self, event):
        super().closeEvent(event)
        self.bthread.stop()

    def handle_status(self, resps_json):
        for resp_json in resps_json:
            level = InfoLevel.SUCCESS if resp_json['message']=="pass" else InfoLevel.ERROR
            self.second_row.insertWidget(1, InfoBadge.make(
                f"「 {resp_json['label']} 」{resp_json['web']} ",
                parent=self, level=level, 
                target=self.second_row, position=InfoBadgePosition.RIGHT
            ))
            self.gui.webs_status.append(resp_json['web'])
        
        if len(self.gui.webs_status) < len(StatusToolThread.webs) and self.stateTooltip:
            InfoBar.warning(
                title='', content=tools_res.status_web_erratic,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=4000, parent=self
            )
            QTimer.singleShot(5000, lambda: self.stateTooltip.setState(True))
        elif self.stateTooltip:
            self.stateTooltip.setContent("Finish..")
            self.stateTooltip.setState(True)
            self.stateTooltip = None

    # ===== updateBtn logic
    def handle_update(self, updated):
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
