from __future__ import annotations

from utils import conf

from . import SqlRecorder


class DownloadStateStore:
    """Query persisted downloaded state for id_and_md5-capable items."""

    def __init__(self, sql_factory=SqlRecorder):
        self._sql_factory = sql_factory

    @staticmethod
    def _md5_by_item(items) -> dict[str, object]:
        lookup = {}
        for item in items or []:
            if not hasattr(item, "id_and_md5"):
                continue
            _, item_md5 = item.id_and_md5()
            lookup[item_md5] = item
        return lookup

    def downloaded_md5s(self, items) -> set[str]:
        if not conf.isDeduplicate:
            return set()
        md5_lookup = self._md5_by_item(items)
        if not md5_lookup:
            return set()
        sql = self._sql_factory()
        try:
            return sql.batch_check_dupe(list(md5_lookup))
        finally:
            sql.close()

    def downloaded_items(self, items) -> list:
        md5_lookup = self._md5_by_item(items)
        if not md5_lookup:
            return []
        downloaded_md5s = self.downloaded_md5s(md5_lookup.values())
        return [item for item_md5, item in md5_lookup.items() if item_md5 in downloaded_md5s]

    def filter_pending(self, items, running_ids=()) -> tuple[list, dict]:
        skip_info = {"running": 0, "downloaded": 0}
        if not items:
            return [], skip_info

        running_lookup = set(running_ids or ())
        downloaded_lookup = self.downloaded_md5s(items)
        pending = []
        for item in items:
            if not hasattr(item, "id_and_md5"):
                pending.append(item)
                continue
            _, item_md5 = item.id_and_md5()
            if item_md5 in running_lookup:
                skip_info["running"] += 1
                continue
            if item_md5 in downloaded_lookup:
                skip_info["downloaded"] += 1
                continue
            pending.append(item)
        return pending, skip_info
