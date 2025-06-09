from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, TransparentToolButton, 
    HyperlinkButton, FluentIcon as FIF
)
from qframelesswindow import FramelessWindow


class DomainToolView(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        w = int(parent.width()*0.7)
        h = int(parent.height()*1.1)
        self.resize(w, h)
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        self.move(int((screen_geo.width() - w) / 2.3),int((screen_geo.height() - h) / 2))
        self.init_ui()

    def init_ui(self):
        first_row = QHBoxLayout()
        first_row.addStretch()
        goBtn = HyperlinkButton()
        handleBtn = PrimaryPushButton()
        cancelBtn = TransparentToolButton(FIF.CLOSE, self)
        cancelBtn.clicked.connect(self.close)
        for btn in (goBtn, handleBtn, cancelBtn):
            first_row.addWidget(btn)
        
        first_row.addStretch()
        self.main_layout.addLayout(first_row)

