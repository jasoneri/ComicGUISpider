from PySide6.QtCore import Qt, QTimer
from GUI.core.timer import safe_single_shot
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, FlyoutViewBase, FlyoutAnimationType,
    InfoBadge, InfoBar, InfoBarPosition, StateToolTip
)

from assets import res as ori_res
from GUI.uic.qfluent.components import CustomFlyout

tools_res = ori_res.GUI.Tools


class DomainToolView(FlyoutViewBase):
    _STAGED_CONTENT = ("正在检测可用性...", "检测到网络波动，正在尝试备用线路...", "正在为您切换最快线路...")

    def __init__(self, gui):
        super().__init__(gui.BrowserWindow)
        self.gui = gui
        self.browser = gui.BrowserWindow
        self._loading_tooltip = None
        self._stage_timer = None
        self._stage_index = 0
        self.setupUi()

    def setupUi(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        self.second_row = QHBoxLayout()
        self.second_row.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addLayout(self.second_row)

    def show_loading(self):
        self._clear_badges()
        self._stage_index = 0
        self._loading_tooltip = StateToolTip('域名检测中', self._STAGED_CONTENT[0], self.browser)
        self._loading_tooltip.show()
        self._stage_timer = QTimer(self)
        self._stage_timer.setInterval(1500)
        self._stage_timer.timeout.connect(self._advance_stage)
        self._stage_timer.start()

    def _advance_stage(self):
        self._stage_index = min(self._stage_index + 1, len(self._STAGED_CONTENT) - 1)
        if self._loading_tooltip:
            self._loading_tooltip.setContent(self._STAGED_CONTENT[self._stage_index])

    def dismiss_loading(self):
        if self._stage_timer is not None:
            self._stage_timer.stop()
            self._stage_timer = None
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
            gui_site_runtime = self.gui.gui_site_runtime
            if gui_site_runtime is None:
                raise RuntimeError("gui_site_runtime unavailable for domain cache update")
            self.gui.gui_site_runtime = gui_site_runtime.persist_domain(_domain)
            t_f = self.gui.gui_site_runtime.domain_cache_path()
            prefix_tip = tools_res.doamin_success_tip % (_domain, t_f)
            sc = 4
            InfoBar.success(
                title='', content=f"{prefix_tip}{tools_res.reboot_tip % str(sc)}",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                duration=sc*1000, parent=self.browser
            )
            safe_single_shot(sc*1000, self.gui.reset_search_context)
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
