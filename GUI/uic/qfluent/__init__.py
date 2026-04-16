import types
import contextlib
from PySide6.QtWidgets import QWidget, QHBoxLayout
from GUI.core.timer import safe_single_shot
from qfluentwidgets import (
    Action, RoundMenu, FluentIcon, PushButton, Flyout, FlyoutAnimationType,
    LineEdit, ToolButton
)
from assets import res as ori_res
from utils import extract_eps_range, conf
from .components import *

__all__ = [
    'MonkeyPatch',
    'CustomFlyout', 'CustomInfoBar', 'TableFlyoutView',
]

res = ori_res.GUI.Uic


def _exec_menu(menu, event):
    menu.exec(event.globalPos())


def _create_web_context_menu(web_view):
    with contextlib.suppress(AttributeError, RuntimeError):
        return web_view.createStandardContextMenu()
    return None


def _selected_web_text(web_view):
    request_getter = getattr(web_view, "lastContextMenuRequest", None)
    if callable(request_getter):
        with contextlib.suppress(RuntimeError):
            request = request_getter()
            if request is not None:
                if text := (request.selectedText() or "").strip():
                    return text
    with contextlib.suppress(AttributeError, RuntimeError):
        if text := (web_view.selectedText() or "").strip():
            return text
    with contextlib.suppress(AttributeError, RuntimeError):
        if text := (web_view.page().selectedText() or "").strip():
            return text
    return ""


class MonkeyPatch:
    @staticmethod
    def rbutton_menu_lineEdit(line_edit, extra_actions=None, sub_menu=None):
        def new_context_menu(self, event):
            def _showCompleterMenu():
                if not self.text().strip():
                    self.setText(" ")
                self._showCompleterMenu()

            menu = RoundMenu(parent=self)
            undo_action = Action(FluentIcon.CANCEL, text=self.tr("Cancel"), triggered=self.undo)
            paste_action = Action(FluentIcon.PASTE, text=self.tr("Paste"), triggered=self.paste)
            select_all_action = Action(self.tr("Select all"), triggered=self.selectAll)
            show_completer = Action(FluentIcon.ALIGNMENT, text=self.tr(res.menu_show_completer),
                                    triggered=_showCompleterMenu)
            if not extra_actions and not sub_menu:
                menu.addAction(show_completer)
            for action in extra_actions or []:
                menu.addAction(action)
            for _menu in sub_menu or []:
                menu.addMenu(_menu)
            menu.addSeparator()
            menu.addAction(paste_action)
            menu.addAction(undo_action)
            menu.addAction(select_all_action)

            _exec_menu(menu, event)
            event.accept()
        line_edit.contextMenuEvent = types.MethodType(new_context_menu, line_edit)

    @staticmethod
    def rbutton_menu_textBrowser(textBrowser, cb_idx, s2c=False):
        # TODO[2](2026-03-02): 废弃或改造
        """cb_idx: chooseBox index
        s2c: send to chooseinput"""
        def custom_context_menu(self, event):
            cursor = self.textCursor()
            selected_text = cursor.selectedText()
            fluent_menu = RoundMenu(parent=self)
            copy_action = Action(FluentIcon.COPY, text=self.tr("COPY"), triggered=self.copy)
            select_all_action = Action(self.tr("Select all"), triggered=self.selectAll)
            fluent_menu.addAction(copy_action)
            fluent_menu.addAction(select_all_action)
            if selected_text:
                fluent_menu.addSeparator()
                custom_action = Action(text="将选中文本加进预设", 
                    triggered=lambda: set_to_completer(selected_text))
                fluent_menu.addAction(custom_action)
            _exec_menu(fluent_menu, event)
            event.accept()
        def set_to_completer(text):
            conf.completer[cb_idx].insert(0, text)
            conf.update()
            textBrowser.gui.set_completer()
        textBrowser.contextMenuEvent = types.MethodType(custom_context_menu, textBrowser)

    @staticmethod
    def rbutton_menu_WebEngine(browserWindow):
        def custom_context_menu(self, event):
            native_menu = _create_web_context_menu(self)
            menu = _convert_menu(native_menu) if native_menu is not None else custom_menu()
            _exec_menu(menu, event)
            event.accept()
            if native_menu is not None:
                native_menu.deleteLater()

        def custom_menu():
            def route_turn(direction: str):
                if direction == "next":
                    browserWindow.gui.nextPageBtn.click()
                else:
                    browserWindow.gui.previousPageBtn.click()

            fluent_menu = RoundMenu(parent=web_view)
            next_page_action = Action(FluentIcon.PAGE_RIGHT, web_view.tr(res.menu_next_page),
                                      triggered=lambda: route_turn("next"), shortcut='Ctrl+.')
            previous_page_action = Action(FluentIcon.PAGE_LEFT, web_view.tr(res.menu_prev_page),
                                          triggered=lambda: route_turn("prev"), shortcut='Ctrl+,')
            fluent_menu.addAction(next_page_action)
            fluent_menu.addAction(previous_page_action)
            fluent_menu.addSeparator()
            return fluent_menu
            
        def _convert_menu(native_menu):
            """将原生菜单转换为Fluent风格"""
            fluent_menu = custom_menu()
            for action in native_menu.actions():
                # 过滤不需要的默认动作
                if not action.isVisible():
                    continue
                if action.isSeparator():
                    fluent_menu.addSeparator()
                    continue
                action_text = str(action.text() or "").replace("&", "").strip()
                if not action_text:
                    continue
                fluent_action = Action(text=action_text, shortcut=action.shortcut(), triggered=action.trigger)
                fluent_action.setEnabled(action.isEnabled())
                if action.isCheckable():
                    fluent_action.setCheckable(True)
                    fluent_action.setChecked(action.isChecked())
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

    @staticmethod
    def rbutton_menu_sauce(browserWindow):
        def send_to_search(text):
            if not text:
                return
            gui.searchinput.setText(text)
            safe_single_shot(10, gui.previewBtn.click)
            def close():
                browserWindow.close()
                gui.BrowserWindow = None
                if gui.toolWin.isVisible():
                    gui.toolWin.close()
            safe_single_shot(20, close)

        def custom_context_menu(self, event):
            selected_text = _selected_web_text(self)
            if selected_text:
                fluent_menu = RoundMenu(parent=web_view)
                sauce_action = Action(FluentIcon.SEARCH, text='Search by saucenao', triggered=lambda: send_to_search(selected_text))
                fluent_menu.addAction(sauce_action)
                _exec_menu(fluent_menu, event)
                event.accept()
            else:
                event.accept()

        web_view = browserWindow.view
        gui = browserWindow.gui
        web_view.contextMenuEvent = types.MethodType(custom_context_menu, web_view)

    @staticmethod
    def rbutton_menu_PulishPage(browserWindow):
        def manual_input():
            lineEdit = LineEdit()
            lineEdit.setPlaceholderText("输入后按确认检测")
            ensureBtn = ToolButton(FluentIcon.ACCEPT_MEDIUM)
            ensureBtn.clicked.connect(lambda: gui.publish_mgr.start_domain_test(lineEdit.text()))
            CustomInfoBar.show_custom(title='', content='', parent=browserWindow, _type="INFORMATION",
                ib_pos=InfoBarPosition.BOTTOM, widgets=[lineEdit, ensureBtn])

        def custom_context_menu(self, event):
            selected_text = _selected_web_text(self)
            fluent_menu = RoundMenu(parent=self)
            manual_action = Action(FluentIcon.PENCIL_INK, text="手输域名", triggered=manual_input)
            test_action = Action(FluentIcon.COMMAND_PROMPT, text="选中内地域名进行检测", triggered=lambda: gui.publish_mgr.start_domain_test(selected_text))
            test_action.setEnabled(bool(selected_text))
            fluent_menu.addAction(manual_action)
            fluent_menu.addAction(test_action)
            _exec_menu(fluent_menu, event)
            event.accept()

        web_view = browserWindow.view
        gui = browserWindow.gui
        web_view.contextMenuEvent = types.MethodType(custom_context_menu, web_view)
