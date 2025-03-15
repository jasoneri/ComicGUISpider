import types
from PyQt5.QtWebEngineWidgets import QWebEngineContextMenuData, QWebEngineSettings, QWebEnginePage
from PyQt5.QtCore import Qt
from qfluentwidgets import (
    Action, RoundMenu, FluentIcon
)
from assets import res as ori_res

from .components import *

__all__ = [
    'MonkeyPatch',
    'CustomFlyout', 'CustomInfoBar', 'TableFlyoutView',
]

res = ori_res.GUI.Uic


class MonkeyPatch:
    @staticmethod
    def rbutton_menu_lineEdit(line_edit):
        def new_context_menu(self, event):
            menu = RoundMenu(parent=self)
            undo_action = Action(FluentIcon.CANCEL, text=self.tr("Cancel"), triggered=self.undo)
            paste_action = Action(FluentIcon.PASTE, text=self.tr("Paste"), triggered=self.paste)
            select_all_action = Action(self.tr("Select all"), triggered=self.selectAll)
            show_completer = Action(FluentIcon.ALIGNMENT, text=self.tr(res.menu_show_completer), 
                                    triggered=self._showCompleterMenu)
            menu.addAction(show_completer)
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

