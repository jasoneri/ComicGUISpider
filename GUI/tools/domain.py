import asyncio

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, FlyoutViewBase,
    InfoBadge, InfoBadgePosition, InfoBar, InfoBarPosition
)

from assets import res as ori_res
from utils import temp_p
from utils.website import extract_domains

tools_res = ori_res.GUI.Tools


class DomainToolView(FlyoutViewBase):
    def __init__(self, gui):
        self.gui = gui
        self.browser = gui.BrowserWindow
        super(DomainToolView, self).__init__(self.browser)
        self.setupUi()

    def setupUi(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        self.second_row = QHBoxLayout()
        self.main_layout.addLayout(self.second_row)

    def handle(self, text):
        domains = extract_domains(text)
        loop = asyncio.get_event_loop()
        hosts = loop.run_until_complete(asyncio.gather(*[self.gui.spiderUtils.test_aviable_domain(domain) for domain in domains]))
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
            t_f = temp_p.joinpath(f"{self.gui.spiderUtils.name}_domain.txt")
            with open(t_f, 'w', encoding='utf-8') as f:
                f.write(_domain)
            prefix_tip = tools_res.doamin_success_tip % (_domain, t_f)
            sc = 6
            InfoBar.success(
                title='', content=f"{prefix_tip}{tools_res.reboot_tip % str(sc)}",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=sc*1000, parent=self.browser
            )
            QTimer.singleShot(sc*1000, self.close_later)
        else:
            InfoBar.error(
                title='', content=tools_res.doamin_error_tip,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=7500, parent=self.browser
            )

    def close_later(self):
        self.browser.domain_v.close()
        self.browser.close()
        self.gui.retrybtn.click()
