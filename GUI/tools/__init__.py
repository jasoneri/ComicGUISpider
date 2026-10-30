# -*- coding: utf-8 -*-
"""GUI.tools 包：工具页与工作区窗口壳。

窗口壳见 ``GUI.tools.workspace.ToolWorkspaceWindow``；工具页为平级业务包
（``addons/`` / ``hitomi/`` / ``mid_tool/`` / ``rv/`` / ``subscribe/`` / ``webdav/``）。
"""
from utils import install_qfluentwidgets_notice_filter

install_qfluentwidgets_notice_filter()

from .chore import CopyUnfinished, TextUtils  # noqa: E402  (notice filter 须先装)

__all__ = ["CopyUnfinished", "TextUtils"]
