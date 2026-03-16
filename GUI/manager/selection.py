# -*- coding: utf-8 -*-
from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal

from GUI.types import GUIFlowStage
from utils import conf
from utils.sql import SqlRecorder


class SelectionFlowManager(QObject):
    """Manage BOOK/EP selection flow and idempotent filtering.

    Domain State: book_choose, _current_indexes
    Signals: decision_made, skip_notified
    """

    decision_made = pyqtSignal(str, list)  # (lane, filtered_indexes)
    skip_notified = pyqtSignal(dict)       # skip_info for UI display

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.book_choose: list = []
        self._current_indexes: list = []

    @property
    def book_num(self) -> int:
        return len(self.book_choose)

    @property
    def current_indexes(self) -> list:
        return self._current_indexes

    def reset(self):
        self.book_choose = []
        self._current_indexes = []

    @staticmethod
    def _dedupe_items(items: list) -> list:
        deduped = []
        seen = set()
        for item in items:
            if hasattr(item, "id_and_md5"):
                key = item.id_and_md5()[1]
            else:
                key = id(item)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _clear_keep_state(self):
        self.book_choose = []

    def submit_decision(self, lane: str, indexes, *, page_turn: str = "", flow_stage=None):
        if lane == "EP":
            book = indexes
            episodes = list(getattr(book, "episodes", None) or [])
            filtered_indexes, skip_info = self._filter_idempotent(episodes, lane)
            if skip_info["running"] or skip_info["downloaded"]:
                self.skip_notified.emit(skip_info)

            self._current_indexes = filtered_indexes if isinstance(filtered_indexes, list) else []
            if not self._current_indexes:
                return []

            book.episodes = list(self._current_indexes)
            self.gui.dl_mgr.submit_download(book)
            self._clear_keep_state()
            self.decision_made.emit(lane, list(self._current_indexes))
            return list(self._current_indexes)

        if lane == "BOOK":
            selected_books = indexes if isinstance(indexes, list) else ([indexes] if indexes else [])
            self._current_indexes = self._dedupe_items(selected_books)
        else:
            self._current_indexes = indexes if isinstance(indexes, list) else ([indexes] if indexes else [])

        filtered_indexes, skip_info = self._filter_idempotent(self._current_indexes, lane)
        if skip_info["running"] or skip_info["downloaded"]:
            self.skip_notified.emit(skip_info)

        self._current_indexes = filtered_indexes if isinstance(filtered_indexes, list) else []
        if not self._current_indexes:
            return []

        if lane == "BOOK":
            stage = flow_stage if flow_stage is not None else getattr(self.gui, "flow_stage", None)
            if stage == GUIFlowStage.SEARCHED:
                self.book_choose = list(self._current_indexes)
            for book in self._current_indexes:
                self.gui.dl_mgr.submit_download(book)
            self._clear_keep_state()

        self.decision_made.emit(lane, list(self._current_indexes))
        return list(self._current_indexes)

    def _filter_idempotent(self, indexes, lane: str):
        skip_info = {"running": 0, "downloaded": 0}
        if not indexes:
            return indexes, skip_info

        dl_mgr = getattr(self.gui, "dl_mgr", None)
        running_ids = dl_mgr.get_running_task_ids() if dl_mgr else set()

        downloaded_ids = set()
        if conf.isDeduplicate:
            sql = SqlRecorder()
            try:
                if lane == "BOOK" and isinstance(indexes, list):
                    md5s = [item.id_and_md5()[1] for item in indexes if hasattr(item, "id_and_md5")]
                    downloaded_ids = sql.batch_check_dupe(md5s) if md5s else set()
                elif lane == "EP" and isinstance(indexes, list):
                    md5s = [ep.id_and_md5()[1] for ep in indexes if hasattr(ep, "id_and_md5")]
                    downloaded_ids = sql.batch_check_dupe(md5s) if md5s else set()
            finally:
                sql.close()

        if lane == "BOOK" and isinstance(indexes, list):
            filtered = []
            for item in indexes:
                if not hasattr(item, "id_and_md5"):
                    filtered.append(item)
                    continue
                _, item_md5 = item.id_and_md5()
                if item_md5 in running_ids:
                    skip_info["running"] += 1
                elif item_md5 in downloaded_ids:
                    skip_info["downloaded"] += 1
                else:
                    filtered.append(item)
            return filtered, skip_info

        if lane == "EP" and isinstance(indexes, list):
            filtered_eps = []
            for ep in indexes:
                if not hasattr(ep, "id_and_md5"):
                    filtered_eps.append(ep)
                    continue
                _, ep_md5 = ep.id_and_md5()
                if ep_md5 in running_ids:
                    skip_info["running"] += 1
                elif ep_md5 in downloaded_ids:
                    skip_info["downloaded"] += 1
                else:
                    filtered_eps.append(ep)
            return filtered_eps, skip_info

        return indexes, skip_info
