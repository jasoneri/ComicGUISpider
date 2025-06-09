from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, 
    HyperlinkButton, FluentIcon as FIF
)


class DomainToolView(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.init_ui()

    def init_ui(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        first_row = QHBoxLayout()
        first_row.addStretch()
        # 通过gui获取url
        goBtn = HyperlinkButton(FIF.LINK, '', '发布页')
        handleBtn = PrimaryPushButton(FIF.HEADPHONE, '', self)
        # 1. 测试域名是否可用
        # 2. self.gui.retryBtn.click()
        first_row.addWidget(goBtn)
        first_row.addWidget(handleBtn)
        
        first_row.addStretch()
        self.main_layout.addLayout(first_row)
