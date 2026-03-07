from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, FlyoutViewBase, FlyoutAnimationType,
    InfoBadge, InfoBar, InfoBarPosition, StateToolTip
)

from assets import res as ori_res
from utils import temp_p
from GUI.uic.qfluent.components import CustomFlyout

tools_res = ori_res.GUI.Tools


class DomainToolView(FlyoutViewBase):
    def __init__(self, gui):
        super().__init__(gui.BrowserWindow)
        self.gui = gui
        self.browser = gui.BrowserWindow
        self._loading_tooltip = None
        self.setupUi()

    def setupUi(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        self.second_row = QHBoxLayout()
        self.second_row.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addLayout(self.second_row)

    def show_loading(self):
        self._clear_badges()
        self._loading_tooltip = StateToolTip('域名检测中', '正在检测可用性...', self.browser)
        self._loading_tooltip.show()

    def dismiss_loading(self):
        if self._loading_tooltip:
            self._loading_tooltip.close()
            self._loading_tooltip = None

    def display_results(self, available: set, unavailable: set):
        self.dismiss_loading()

        for domain in sorted(available):
            badge = InfoBadge.success(domain, parent=self)
            self.second_row.addWidget(badge)
        for domain in sorted(unavailable):
            badge = InfoBadge.error(domain, parent=self)
            self.second_row.addWidget(badge)
        self.layout().update()
        self.setFixedSize(self.layout().sizeHint())
        fly = CustomFlyout.make(
            view=self, target=self.gui, parent=self.gui,  
            aniType=FlyoutAnimationType.NONE
        )
        if self.browser.topHintBox.isChecked():
            self.browser.topHintBox.click()
        pos =  self.browser.pos()
        fly.move(pos.x(), pos.y()+40)

        if available:
            _domain = next(iter(sorted(available)))
            t_f = temp_p.joinpath(f"{self.gui.spiderUtils.name}_domain.txt")
            with open(t_f, 'w', encoding='utf-8') as f:
                f.write(_domain)
            prefix_tip = tools_res.doamin_success_tip % (_domain, t_f)
            sc = 4
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

    def _clear_badges(self):
        while self.second_row.count():
            item = self.second_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def close_later(self):
        self.browser.domain_v.close()
        self.browser.close()
        self.gui.retry_schedule()
