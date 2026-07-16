from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from GUI.manager.preview import PreviewMgr


class PreviewLoadingReason(str, Enum):
    SEARCH_INITIAL = "search_initial"
    PAGING = "paging"
    SUBMIT = "submit"


class PreviewLoadingController:
    """Owns chrome loadingBar and paging HTML overlay lifecycle by reason."""

    def __init__(self, mgr: PreviewMgr):
        self._mgr = mgr
        self._chrome_owner: PreviewLoadingReason | None = None
        self._paging_active = False

    def begin(self, reason: PreviewLoadingReason) -> None:
        if reason is PreviewLoadingReason.SEARCH_INITIAL:
            self._begin_search_initial()
        elif reason is PreviewLoadingReason.PAGING:
            self._begin_paging()
        elif reason is PreviewLoadingReason.SUBMIT:
            self._begin_chrome(PreviewLoadingReason.SUBMIT)

    def end(self, reason: PreviewLoadingReason | None = None) -> None:
        if reason is None:
            self.end_all()
            return
        if reason is PreviewLoadingReason.PAGING:
            self._end_paging()
            return
        if reason in (PreviewLoadingReason.SEARCH_INITIAL, PreviewLoadingReason.SUBMIT):
            self._end_chrome(reason)

    def end_all(self) -> None:
        self._end_chrome(None)
        self._end_paging()

    def _begin_search_initial(self) -> None:
        gui = self._mgr.gui
        gui.present_browser(
            ensure_handler=None,
            reload_tf=False,
            enable_page_frame=True,
            close_handler=self._mgr._on_preview_window_closed,
        )
        self._begin_chrome(PreviewLoadingReason.SEARCH_INITIAL)

    def _begin_paging(self) -> None:
        sent = self._mgr.send_command(
            "preview.paging.show",
            {"text": "paging.."},
        )
        # Track attempt so end_all can hide even if document reloads mid-flight.
        self._paging_active = True
        if not sent:
            logger = getattr(self._mgr.gui, "log", None)
            if logger:
                logger.debug("[preview.loading] paging.show skipped (page not ready)")

    def _begin_chrome(self, owner: PreviewLoadingReason) -> None:
        browser = getattr(self._mgr.gui, "BrowserWindow", None)
        if not browser:
            return
        self._chrome_owner = owner
        browser.start_loading()

    def _end_chrome(self, reason: PreviewLoadingReason | None) -> None:
        if reason is not None and self._chrome_owner is not reason:
            return
        browser = getattr(self._mgr.gui, "BrowserWindow", None)
        if browser:
            browser.stop_loading()
        self._chrome_owner = None

    def _end_paging(self) -> None:
        if self._paging_active:
            self._mgr.send_command("preview.paging.hide", {})
        self._paging_active = False
