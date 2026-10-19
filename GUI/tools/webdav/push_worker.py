# -*- coding: utf-8 -*-
"""WebDAV 推送后台线程。CGS013 §6：推送必须有真实进度 owner，且不得阻塞 GUI 主线程。"""
from __future__ import annotations

import traceback
import typing as t
from copy import deepcopy
from types import MappingProxyType

from PySide6.QtCore import QThread, Signal


class WebdavPushThread(QThread):
    progress = Signal(dict)
    succeeded = Signal(dict)
    # 失败传异常对象本身：UI 按类型决策，不解析字符串。
    failed = Signal(object)

    def __init__(self, gui, entries: t.Sequence[dict], *, config: t.Mapping[str, t.Any]):
        super().__init__(gui)
        self.gui = gui
        self.entries = deepcopy(list(entries))
        self.config = MappingProxyType(deepcopy(dict(config)))

    def run(self):
        from utils.webdav import WebDavClient, push_entries
        from utils.webdav.client import proxy_kwargs

        cfg = self.config
        password = cfg["password"]
        try:
            with WebDavClient(cfg["endpoint"], cfg["user"], password, root=cfg["root"],
                              **proxy_kwargs(cfg.get("use_proxy"))) as client:
                result = push_entries(client, self.entries, on_progress=self.progress.emit)
        except Exception as exc:
            details = traceback.format_exc()
            message = f"[{type(exc).__name__}] {exc}"
            if password:
                details = details.replace(password, "***")
                message = message.replace(password, "***")
            self.gui.log.error(details)
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)
