from PySide6.QtWidgets import QWidget, QStackedWidget, QHBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from utils import install_qfluentwidgets_notice_filter

install_qfluentwidgets_notice_filter()

from qfluentwidgets import Pivot
from qframelesswindow import FramelessWindow
from qfluentwidgets import TransparentToolButton, FluentIcon as FIF, VBoxLayout

from GUI.core.timer import safe_single_shot
from GUI.tools.hitomi_tool import HitomiTools, hitomi_db_path
from GUI.tools.rv_tool import rvTool
from GUI.tools.domain import DomainToolView
from GUI.tools.ags import AggrSearchView
from GUI.tools.mid_tool import MidToolInterface
from GUI.tools.chore import *


class ToolWindow(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.subscribeInterface = None  # CGS006: build on first subscribe open
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        if parent:
            self.window_width = int(parent.width() * 0.8)
        else:
            self.window_width = int(screen_geo.width() * 0.4)
        window_height = int(screen_geo.height() * 0.22)
        self.setMinimumSize(self.window_width, window_height)
        self.default_height = 120
        self.resize(self.window_width, self.default_height)
        self.move(
            int((screen_geo.width() - self.window_width) / 2),
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
        # CGS006: SubscribeInterface is P4 — create on first pivot click / open_subscribe.
        self.pivot.addItem(routeKey='subscribeInterface', text='subscribe',onClick=self._open_subscribe_tab,)

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

    def ensure_subscribe_interface(self):
        if self.subscribeInterface is not None:
            return self.subscribeInterface
        from GUI.tools.subscribe import SubscribeInterface
        self.subscribeInterface = SubscribeInterface(self)
        self.addSubInterface(self.subscribeInterface, 'subscribeInterface', 'subscribe', add_pivot=False)
        return self.subscribeInterface

    def _open_subscribe_tab(self):
        subscribe_interface = self.ensure_subscribe_interface()
        self.stackedWidget.setCurrentWidget(subscribe_interface)

    def addAggrSearchView(self):
        self.asInterface = AggrSearchView(self.gui)
        self.addSubInterface(self.asInterface, 'asInterface', 'aggrSearch')

    def addHitomiTool(self):
        if hitomi_db_path.exists():
            self.htInterface = HitomiTools(self.gui)
            self.addSubInterface(self.htInterface, 'htInterface', 'hitomiTool')

    def addMidTool(self):
        self.midInterface = MidToolInterface(self.gui)
        self.addSubInterface(self.midInterface, 'midInterface', 'midTool')

    def addSubInterface(self, widget: QWidget, objectName: str, text: str, *, add_pivot: bool = True):
        widget.setObjectName(objectName)
        if isinstance(widget, QLabel):
            widget.setAlignment(Qt.AlignCenter)
        self.stackedWidget.addWidget(widget)

        if add_pivot:
            self.pivot.addItem(
                routeKey=objectName,
                text=text,
                onClick=lambda: self.stackedWidget.setCurrentWidget(widget)
            )

    def onCurrentIndexChanged(self, index):
        widget = self.stackedWidget.widget(index)
        if widget is None:
            return
        if widget.objectName() == "htInterface" and hitomi_db_path.exists():
            self.pivot.removeWidget("htInterface")
            self.htInterface = HitomiTools(self.gui)
            self.addSubInterface(self.htInterface, 'htInterface', 'hitomiTool')
        if widget.objectName() == "asInterface":
            new_height = min(int(self.gui.height() * 0.85), 300)
            self.resize(self.gui.width(), new_height)
        elif widget.objectName() == "midInterface":
            self.resize(self.gui.width(), min(370, self.gui.height()))
        elif widget.objectName() == "subscribeInterface":
            self.resize(self.gui.width(), min(520, self.gui.height()))
        else:
            self.resize(self.window_width, self.default_height)
        self.pivot.setCurrentItem(widget.objectName())

    def open_subscribe_with_books(self, books):
        """Open the subscribe tab and persist preview BookInfo seeds directly (wizard-less)."""
        self.gui.show_toolWin("subscribe")
        payload = list(books)

        def _deliver():
            subscribe_interface = self.ensure_subscribe_interface()
            self.stackedWidget.setCurrentWidget(subscribe_interface)
            subscribe_interface.receive_pushed_books(payload)

        safe_single_shot(20, _deliver)

    def server_mode_switch_blockers(self) -> list[str]:
        if self.subscribeInterface is None:
            return []
        return self.subscribeInterface.server_mode_switch_blockers()


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([])
    window = ToolWindow()
    window.show()
    app.exec()


if __name__ == '__main__':
    import GUI.src.material_ct
    main()
