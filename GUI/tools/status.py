import json
import asyncio
import hashlib

import httpx
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, BodyLabel, StrongBodyLabel,
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
transport_kw = dict(retries=2)


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
    def cloudflare_status(web):
        return f"https://cgs-status-badges.pages.dev/status_{web}.json"


async def fetch(url, _transport_kw={}):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=10), 
                                     transport=httpx.AsyncHTTPTransport(**transport_kw, **_transport_kw)) as cli:
            _resp = await cli.get(url)
            _resp_body = _resp.content
    except:
        raise RuntimeError(f"access {url} failed")
    return _resp_body


class StatusToolView(QWidget):
    webs = {"kaobei", "mangabz", "hitomi", "wnacg", "ehentai", "jm"}
    
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.loop = asyncio.get_event_loop()
        self.stateTooltip = None
        self.init_ui()

    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        
        first_row = QHBoxLayout()
        desc_label = StrongBodyLabel(tools_res.status_desc)
        first_row.addWidget(desc_label)
        
        self.second_row = QHBoxLayout()
        self.second_row.addStretch()
        third_row = QHBoxLayout()
        copy2Btn = PrimaryPushButton(FIF.UPDATE, "Update 拷贝", self)
        copy2Btn.clicked.connect(self.copy2)
        hitomiBtn = PrimaryPushButton(FIF.UPDATE, "Update Hitomi", self)
        hitomiBtn.clicked.connect(self.hitomi)
        third_row.addWidget(copy2Btn)
        third_row.addWidget(hitomiBtn)
        for row in (first_row, self.second_row, third_row):
            self.main_layout.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        if len(self.gui.webs_status) < 6:
            self.stateTooltip = StateToolTip(tools_res.status_fetching, tools_res.status_waiting, self.gui.toolWin)
            self.stateTooltip.move(20, 20)
            self.stateTooltip.setState(False)
            self.stateTooltip.show()
            QTimer.singleShot(10, self.set_badges)

    def set_badges(self):
        remains = self.webs - set(self.gui.webs_status)
        async def set_badge(web):
            try:
                resp_body = await fetch(Api.cloudflare_status(web), 
                                        dict(proxy=f"http://{conf.proxies[0]}") if conf.proxies else {})
                resp_json = json.loads(resp_body)
                match resp_json['message']:
                    case "pass":
                        level = InfoLevel.SUCCESS
                    case _:
                        level = InfoLevel.ERROR
                self.second_row.insertWidget(0, InfoBadge.make(
                    f"「 {resp_json['label']} 」{web} ",
                    parent=self, level=level, 
                    target=self.second_row, position=InfoBadgePosition.RIGHT
                ))
                self.gui.webs_status.append(web)
            except Exception as e:
                ...
        async def fetch_all():
            tasks = [set_badge(remain) for remain in remains]
            return await asyncio.gather(*tasks)
        self.loop.run_until_complete(fetch_all())
        if len(self.gui.webs_status) < len(remains) and not hasattr(self, "errAccessStatus"):
            self.errAccessStatus = BodyLabel(tools_res.status_cf_error)
            self.second_row.insertWidget(0, self.errAccessStatus)
            self.second_row.insertWidget(1, HyperlinkButton(FIF.LINK, "https://jasoneri.github.io/ComicGUISpider/", "CGS"))
        if self.stateTooltip:
            self.stateTooltip.setContent("Finish..")
            self.stateTooltip.setState(True)
            self.stateTooltip = None

    def copy2(self):
        cfiles = ["utils/website/__init__.py", "ComicSpider/spiders/kaobei.py"]
        return self.update(cfiles)

    def hitomi(self):
        cfiles = [r"utils/website/hitomi/__init__.py", r"ComicSpider/spiders/hitomi.py"]
        return self.update(cfiles)

    def update(self, cfiles):
        local_files = [ori_path.joinpath(cfile) for cfile in cfiles]
        copy2decrypt_urls = [Api.raw(cfile) for cfile in cfiles]
        
        def to_md5(body: bytes):
            return hashlib.md5(body).hexdigest()

        def normalize_line_endings(content: bytes) -> bytes:
            return content.replace(b'\r\n', b'\n')

        async def update_file(local_f, url):
            resp_bytes = await fetch(url)
            local_bytes = local_f.read_bytes()
            if to_md5(normalize_line_endings(local_bytes)) != to_md5(resp_bytes):
                with open(local_f, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(resp_bytes.decode('utf-8'))
                return True
            return False

        async def update_all():
            tasks = [update_file(local_f, url) for local_f, url in zip(local_files, copy2decrypt_urls)]
            results = await asyncio.gather(*tasks)
            return any(results)

        updated = self.loop.run_until_complete(update_all())
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
