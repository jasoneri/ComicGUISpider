import re
import asyncio

from PyQt5.QtCore import Qt, QTimer
from urllib.parse import urlparse
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, 
    HyperlinkButton, FluentIcon as FIF, StrongBodyLabel, ImageLabel,
    InfoBadge, InfoBadgePosition, InfoBar, InfoBarPosition
)

from assets import res as ori_res
from utils import temp_p

tools_res = ori_res.GUI.Tools


class DomainToolView(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.spiderUtils = self.gui.spiderUtils
        self.init_ui()

    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        first_row = QHBoxLayout()
        desc = StrongBodyLabel(tools_res.domain_desc)
        imgLabel = ImageLabel(":/tools/domain_eg.png")
        imgLabel.scaledToHeight(int(self.gui.toolWin.height() * 0.4))
        imgLabel.setBorderRadius(8, 8, 8, 8)
        first_row.addStretch()
        first_row.addWidget(desc)
        first_row.addWidget(imgLabel)
        first_row.addStretch()
        self.second_row = QHBoxLayout()
        self.second_row.addStretch()
        goBtn = HyperlinkButton(FIF.LINK, self.gui.spiderUtils.publish_url, '发布页')
        handleBtn = PrimaryPushButton(FIF.COMMAND_PROMPT, '执行', self)
        handleBtn.clicked.connect(self.handle)
        self.second_row.addWidget(goBtn)
        self.second_row.addWidget(handleBtn)
        self.second_row.addStretch()
        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(self.second_row)

    def handle(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        def extract_domains(text):
            return set(
                netloc for line in text.split('\n') 
                if (netloc := urlparse('//' + line.strip()).netloc)  # 智能补全协议
                and re.match(r'^[\w.-]+\.[a-zA-Z]{2,}$', netloc)    # 严格域名验证
            )
        domains = extract_domains(text)
        loop = asyncio.get_event_loop()
        hosts = loop.run_until_complete(asyncio.gather(*[self.spiderUtils.test_aviable_domain(domain) for domain in domains]))
        hosts = set(hosts) or set()
        aviable_domains = hosts & domains
        unaviable_domains = domains - aviable_domains
        for aviable_domain in aviable_domains:
            self.second_row.insertWidget(3, InfoBadge.success(
                aviable_domain,
                parent=self,
                target=self.second_row,
                position=InfoBadgePosition.RIGHT
            ))
        for unaviable_domain in unaviable_domains:
            self.second_row.insertWidget(3+len(aviable_domains), InfoBadge.error(
                unaviable_domain,
                parent=self,
                target=self.second_row,
                position=InfoBadgePosition.RIGHT
            ))
        if aviable_domains:
            _domain = aviable_domains.pop()
            t_f = temp_p.joinpath(f"{self.spiderUtils.name}_domain.txt")
            with open(t_f, 'w', encoding='utf-8') as f:
                f.write(_domain)
            prefix_tip = tools_res.doamin_success_tip % (_domain, t_f)
            InfoBar.success(
                title='', content=f"{prefix_tip}{tools_res.reboot_tip % '10'}",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=10000, parent=self
            )
            QTimer.singleShot(10000, self.close_later)
        else:
            InfoBar.error(
                title='', content=tools_res.doamin_error_tip,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=7500, parent=self
            )
    
    def close_later(self):
        self.gui.toolWin.close()
        self.gui.retrybtn.click()
