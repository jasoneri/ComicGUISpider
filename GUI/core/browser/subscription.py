from PySide6.QtCore import Qt
from qfluentwidgets import FluentIcon as FIF, InfoBar, InfoBarPosition, ToolButton


class PreviewSubscriptionController:
    def __init__(self, browser):
        self._browser = browser
        self._selection_active = False
        self._manga_like = False
        self._button = ToolButton(browser.groupBox)
        self._button.setIcon(FIF.SHARE)
        self._button.setToolTip("加入订阅/send selected to subscribe")
        self._button.hide()
        browser.horizontalLayout_2.insertWidget(browser.horizontalLayout_2.indexOf(browser.ensureBtn), self._button)
        self._button.clicked.connect(self.send_checked_books)

    @property
    def selection_active(self) -> bool:
        return self._selection_active

    @property
    def entry_visible(self) -> bool:
        return self._button.isVisible()

    def configure_entry(self, *, is_manga_like: bool) -> None:
        """Configure direct or selection-mode entry for the current preview card type."""
        self._exit_selection()
        self._manga_like = bool(is_manga_like)
        self._button.setVisible(not self._manga_like)

    def toggle_selection(self) -> None:
        if not self._preview_is_manga_like():
            InfoBar.info(
                title="",
                content="当前预览的卡片可直接勾选后点击「加入订阅」",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self._browser.view,
            )
            return
        if self._selection_active:
            self._exit_selection()
        else:
            self.enter_selection()

    def enter_selection(self) -> None:
        if self._selection_active:
            return
        self._selection_active = True
        self._browser.page_runtime.run_js("document.body.classList.add('subscribe-select-mode');")
        self._button.show()
        self._browser.ensureBtn.setEnabled(False)

    def _exit_selection(self) -> None:
        if not self._selection_active:
            return
        self._selection_active = False
        self._browser.page_runtime.run_js(
            "document.body.classList.remove('subscribe-select-mode');"
            "window.previewRuntime && window.previewRuntime.clearChecked"
            " && window.previewRuntime.clearChecked(window.previewRuntime.getItemIds({kind:'book'}));"
        )
        self._button.setVisible(not self._manga_like)
        self._browser.ensureBtn.setEnabled(True)

    def _preview_is_manga_like(self) -> bool:
        preview_manager = self._browser.gui.preview_mgr
        return bool(preview_manager.is_manga or preview_manager.is_fix)

    def send_checked_books(self) -> None:
        if not self._browser.page_runtime.page_ready:
            InfoBar.info(
                title="",
                content="页面仍在加载，稍后再试",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2200,
                parent=self._browser.view,
            )
            return

        def show_script_error(_exception):
            InfoBar.error(
                title="",
                content="页面脚本返回异常，请刷新预览后重试",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self._browser.view,
            )

        self._browser.page_runtime.run_js_result(
            "return window.previewRuntime.getCheckedIds({kind:'book'});",
            self._handover_checked_books,
            expected_kind="array",
            description="subscribe getCheckedIds(book)",
            error_callback=show_script_error,
        )

    def _handover_checked_books(self, checked_ids) -> None:
        books_cache = self._browser.gui.preview_mgr.books_cache
        checked_keys = [str(book_id) for book_id in checked_ids]
        selected_books = [books_cache[book_id] for book_id in checked_keys if book_id in books_cache]
        if not selected_books:
            message = "请先勾选要订阅的书" if not checked_keys else "选中的预览数据已过期，请刷新预览后重新勾选"
            InfoBar.info(
                title="",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2200,
                parent=self._browser.view,
            )
            return
        self._exit_selection()
        self._browser.gui.push_books_to_subscribe(selected_books)
