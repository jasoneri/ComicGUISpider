from PyQt5.QtWidgets import QWidget, QStackedWidget, QHBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from qfluentwidgets import Pivot
from qframelesswindow import FramelessWindow
from qfluentwidgets import TransparentToolButton, FluentIcon as FIF, VBoxLayout

from GUI.tools.hitomi_tool import HitomiTools, hitomi_db_path
from GUI.tools.rv_tool import rvTool
from GUI.tools.domain import DomainToolView
from GUI.tools.status import StatusToolView
from GUI.tools.chore import *


class ToolWindow(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        if parent:
            window_width = int(parent.width() * 0.8)
        else:
            window_width = int(screen_geo.width() * 0.4)
        window_height = int(screen_geo.height() * 0.22)
        self.setMinimumSize(window_width, window_height)
        self.resize(window_width, 120)
        self.move(
            int((screen_geo.width() - window_width) / 2),
            int((screen_geo.height() - window_height) / 2)
        )
        
        self.init_ui()
    
    def init_ui(self):
        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.main_layout = VBoxLayout(self)

        first_row = QHBoxLayout()
        self.rvInterface = rvTool(self)
        self.addSubInterface(self.rvInterface, 'rvInterface', 'rvTool')
        self.stInterface = StatusToolView(self.gui)
        self.addSubInterface(self.stInterface, 'stInterface', 'statusTool')

        # 连接信号并初始化当前标签页
        self.stackedWidget.currentChanged.connect(self.onCurrentIndexChanged)
        self.stackedWidget.setCurrentWidget(self.rvInterface)
        self.pivot.setCurrentItem(self.rvInterface.objectName())

        first_row.addWidget(self.pivot, alignment=Qt.AlignCenter)
        self.cancelBtn = TransparentToolButton(FIF.CLOSE, self)
        self.cancelBtn.clicked.connect(self.close)
        first_row.addWidget(self.cancelBtn, alignment=Qt.AlignRight)
        
        second_row = QHBoxLayout()
        second_row.addWidget(self.stackedWidget)
        
        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)

    def addDomainTool(self):
        self.dmInterface = DomainToolView(self.gui)
        self.addSubInterface(self.dmInterface, 'dmInterface', 'domainTool')

    def addHitomiTool(self):
        if hitomi_db_path.exists():
            self.htInterface = HitomiTools(self.gui)
            self.addSubInterface(self.htInterface, 'htInterface', 'hitomiTool')

    def addSubInterface(self, widget: QWidget, objectName: str, text: str):
        widget.setObjectName(objectName)
        if isinstance(widget, QLabel):
            widget.setAlignment(Qt.AlignCenter)
        self.stackedWidget.addWidget(widget)

        # 使用全局唯一的 objectName 作为路由键
        self.pivot.addItem(
            routeKey=objectName,
            text=text,
            onClick=lambda: self.stackedWidget.setCurrentWidget(widget)
        )

    def onCurrentIndexChanged(self, index):
        widget = self.stackedWidget.widget(index)
        if widget.objectName() == "htInterface" and hitomi_db_path.exists():
            self.pivot.removeWidget("htInterface")
            self.htInterface = HitomiTools(self.gui)
            self.addSubInterface(self.htInterface, 'htInterface', 'hitomiTool')
        self.pivot.setCurrentItem(widget.objectName())


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication([])
    window = ToolWindow()
    window.show()
    app.exec_()


if __name__ == '__main__':
    import GUI.src.material_ct
    main()
