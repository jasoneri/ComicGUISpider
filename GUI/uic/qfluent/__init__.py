import types
from PyQt5.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import (
    Action, RoundMenu, FluentIcon, PushButton, Flyout, FlyoutAnimationType
)
from assets import res as ori_res

from .components import *

__all__ = [
    'MonkeyPatch',
    'CustomFlyout', 'CustomInfoBar', 'TableFlyoutView',
]

res = ori_res.GUI.Uic


class NumberKeypadWidget(QWidget):
    def __init__(self, line_edit, parent=None):
        super().__init__(parent)
        self.line_edit = line_edit
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)

        _size = (32, 32)
        for i in range(10):
            btn = PushButton(str(i))
            btn.setFixedSize(*_size)
            btn.clicked.connect(lambda _, num=str(i): self.append_to_input(num))
            layout.addWidget(btn)

        layout.addSpacing(8)
        for i in ("+", "-"):
            btn = PushButton(i)
            btn.setFixedSize(*_size)
            btn.clicked.connect(lambda _, num=i: self.append_to_input(num))
            layout.addWidget(btn)

        layout.addSpacing(8)
        close_btn = PushButton("×")
        close_btn.setFixedSize(*_size)
        close_btn.clicked.connect(self.close_keypad)
        layout.addWidget(close_btn)

    def append_to_input(self, text):
        self.line_edit.insert(text)

    def close_keypad(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, 'close') and 'Flyout' in parent.__class__.__name__:
                parent.close()
                break
            parent = parent.parent()


def show_number_keypad(line_edit, target_widget):
    keypad_widget = NumberKeypadWidget(line_edit)
    Flyout.make(
        view=keypad_widget,
        target=target_widget,
        parent=target_widget.window(),
        aniType=FlyoutAnimationType.DROP_DOWN
    )


class MonkeyPatch:
    @staticmethod
    def rbutton_menu_lineEdit(line_edit):
        def new_context_menu(self, event):
            def _showCompleterMenu():
                if not self.text().strip():
                    self.setText(" ")
                self._showCompleterMenu()

            def _showNumberKeypad():
                show_number_keypad(self, self)

            menu = RoundMenu(parent=self)
            undo_action = Action(FluentIcon.CANCEL, text=self.tr("Cancel"), triggered=self.undo)
            paste_action = Action(FluentIcon.PASTE, text=self.tr("Paste"), triggered=self.paste)
            select_all_action = Action(self.tr("Select all"), triggered=self.selectAll)
            show_completer = Action(FluentIcon.ALIGNMENT, text=self.tr(res.menu_show_completer),
                                    triggered=_showCompleterMenu)
            menu.addAction(show_completer)
            if hasattr(self, 'objectName') and self.objectName() == 'chooseinput':
                number_keypad_action = Action(
                    FluentIcon.EDIT, text="点击输入", triggered=_showNumberKeypad)
                menu.addAction(number_keypad_action)
            menu.addSeparator()
            menu.addAction(paste_action)
            menu.addAction(undo_action)
            menu.addAction(select_all_action)

            menu.exec_(event.globalPos())
            event.accept()
        line_edit.contextMenuEvent = types.MethodType(new_context_menu, line_edit)

    @staticmethod
    def rbutton_menu_WebEngine(browserWindow):
        def custom_context_menu(self, event):
            page = self.page()
            native_menu = page.createStandardContextMenu()
            menu = _convert_menu(native_menu)
            menu.exec(event.globalPos())
            event.accept()
            native_menu.deleteLater()

        def custom_menu():
            fluent_menu = RoundMenu(parent=web_view)
            next_page_action = Action(FluentIcon.PAGE_RIGHT, web_view.tr(res.menu_next_page),
                                      triggered=browserWindow.gui.nextPageBtn.click, shortcut='Ctrl+.')
            previous_page_action = Action(FluentIcon.PAGE_LEFT, web_view.tr(res.menu_prev_page),
                                          triggered=browserWindow.gui.previousPageBtn.click, shortcut='Ctrl+,')
            fluent_menu.addAction(next_page_action)
            fluent_menu.addAction(previous_page_action)
            fluent_menu.addSeparator()
            return fluent_menu
            
        def _convert_menu(native_menu):
            """将原生菜单转换为Fluent风格"""
            fluent_menu = custom_menu()
            for action in native_menu.actions():
                # 过滤不需要的默认动作
                if action.isSeparator():
                    fluent_menu.addSeparator()
                    continue
                action_text = action.text()
                fluent_action = Action(text=action_text, shortcut=action.shortcut(), triggered=action.trigger)
                match action_text:  # icon mapping
                    case 'Copy' | 'Copy link address':
                        fluent_action.setIcon(FluentIcon.COPY.icon())
                    case 'Cut':
                        fluent_action.setIcon(FluentIcon.CUT.icon())
                    case 'Paste':
                        fluent_action.setIcon(FluentIcon.PASTE.icon())
                    case 'Undo':
                        fluent_action.setIcon(FluentIcon.CANCEL.icon())
                    case 'Reload':
                        fluent_action.setIcon(FluentIcon.SYNC.icon())
                    case 'Back':
                        fluent_action.setIcon(FluentIcon.LEFT_ARROW.icon())
                    case 'Forward':
                        fluent_action.setIcon(FluentIcon.RIGHT_ARROW.icon())
                    case _:
                        pass
                fluent_menu.addAction(fluent_action)
            return fluent_menu

        web_view = browserWindow.view
        web_view.contextMenuEvent = types.MethodType(custom_context_menu, web_view)
