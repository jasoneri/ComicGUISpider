from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from PySide6.QtCore import QEvent, QObject, QRect, QUrl
from PySide6.QtGui import QGuiApplication
from qfluentwidgets import InfoBarPosition, ToolButton, TransparentPushButton

from GUI.browser_window import BrowserWindow
from GUI.core.anim import PopupAnimator
from GUI.uic.qfluent.components import CustomInfoBar
from GUI.uic.qfluent.components.icons import CgsIcon
from utils import conf_dir, get_httpx_verify
from variables import CGS_TIMELINE_API


class _InfoBarClickToClose(QObject):
    """点击 InfoBar 非按钮区即关闭；按钮（含「查看」/link/关闭钮）仍独立响应。"""

    def __init__(self, info_bar, parent=None):
        super().__init__(parent)
        self._info_bar = info_bar
        info_bar.installEventFilter(self)
        info_bar._click_to_close_filter = self

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            # 能冒泡到 InfoBar 的鼠标事件说明未被子按钮消费 → 非按钮区点击
            self._info_bar.close()
            return True
        return False


@dataclass(frozen=True, slots=True)
class TimelineTip:
    event_id: str
    tip: str
    timeline_url: str
    link_label: str = ""
    link_url: str = ""

    @classmethod
    def from_payload(cls, payload: object) -> TimelineTip:
        if not isinstance(payload, dict):
            raise TypeError("timeline tip payload must be an object")
        event_id = str(payload.get("id") or "").strip()
        tip = str(payload.get("tip") or "").strip()
        timeline_url = str(payload.get("timeline_url") or "").strip()
        if not event_id or not tip or len(tip) > 80 or not timeline_url:
            raise ValueError("timeline tip payload is invalid")
        parsed_url = QUrl(timeline_url)
        if not parsed_url.isValid() or parsed_url.scheme() != "https":
            raise ValueError("timeline tip URL must be HTTPS")
        link_label = str(payload.get("link_label") or "").strip()
        link_url = str(payload.get("link_url") or "").strip()
        if bool(link_label) != bool(link_url):
            raise ValueError("timeline tip link fields must be provided together")
        if link_url:
            parsed_link = QUrl(link_url)
            if not parsed_link.isValid() or parsed_link.scheme() != "https":
                raise ValueError("timeline tip link URL must be HTTPS")
        return cls(
            event_id=event_id,
            tip=tip,
            timeline_url=timeline_url,
            link_label=link_label,
            link_url=link_url,
        )


class TimelineTipState:
    """公告已读状态。

    只记最新一条的 event_id：/tip 端点结构上只返回最新公告，
    infobar 不可能弹出旧条目，存集合是多余的。
    version 用于将来加字段时的迁移，与文档站 localStorage 同构。
    """

    _file = conf_dir / "timeline_tip_state.json"
    _version = 1

    def __init__(self):
        self.read_event_id = ""

    def load(self) -> None:
        """读取失败由调用方记录并降级为「未读」，本方法不吞异常。"""
        if not self._file.exists():
            return
        with open(self._file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 版本不认识就当未读：降级方向只能是「多提示一次」，不能是「吞掉公告」
        if not isinstance(data, dict) or data.get("version") != self._version:
            return
        self.read_event_id = str(data.get("read_event_id") or "")

    def save(self) -> None:
        payload = {"version": self._version, "read_event_id": self.read_event_id}
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


class TimelineTipManager:
    def __init__(self, gui):
        self.gui = gui
        self._browser_window: BrowserWindow | None = None
        self.state = TimelineTipState()
        try:
            self.state.load()
        except (OSError, ValueError) as err:
            # 状态文件损坏/不可读：本次按未读处理并留痕，绝不能因此静默吞掉公告
            self.gui.log.error(f"公告已读状态读取失败，本次将重新提示：{err}")

    def mark_read(self, event_id: str) -> None:
        if self.state.read_event_id == event_id:
            return
        self.state.read_event_id = event_id
        try:
            self.state.save()
        except OSError as err:
            self.gui.log.error(f"公告已读状态写入失败，下次仍会提示：{err}")

    def check_on_startup(self) -> None:
        self.gui.preprocess_mgr.task_manager.execute_simple_task(
            task_func=self.fetch_tip,
            success_callback=self.show_tip,
            error_callback=self.gui.log.error,
            show_tooltip=False,
            show_success_info=False,
            show_error_info=False,
            task_id="timeline_tip_startup",
        )

    async def fetch_tip(self) -> TimelineTip | None:
        transport = httpx.AsyncHTTPTransport(retries=0, verify=get_httpx_verify())
        async with httpx.AsyncClient(transport=transport, timeout=8.0, trust_env=False) as client:
            response = await client.get(f"{CGS_TIMELINE_API}/tip", headers={"accept": "application/json"})
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return TimelineTip.from_payload(response.json())

    def show_tip(self, timeline_tip: TimelineTip | None) -> None:
        if timeline_tip is None:
            return
        if timeline_tip.event_id == self.state.read_event_id:
            return
        widgets = []
        if timeline_tip.link_url:
            # CTA 文案是动态的（「填写问卷」等），必须留字，用带文字的透明按钮
            link_button = TransparentPushButton(timeline_tip.link_label, icon=CgsIcon.NOTICE_LINK)
            link_button.clicked.connect(lambda: self.open_timeline(timeline_tip.link_url))
            link_button.clicked.connect(lambda: self.mark_read(timeline_tip.event_id))
            widgets.append(link_button)
        # 「查看」语义恒定，图标足以表意（CGS009：icon-only 不叠 tip）
        view_button = ToolButton(CgsIcon.NOTICE_TIMELINE)
        widgets.append(view_button)
        info_bar = CustomInfoBar.show_custom(
            title="",
            content=timeline_tip.tip,
            parent=self.gui.showArea,
            _type="INFORMATION",
            ib_pos=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            widgets=widgets,
        )
        _InfoBarClickToClose(info_bar, self.gui)
        view_button.clicked.connect(lambda: self.open_timeline(timeline_tip.timeline_url))
        view_button.clicked.connect(lambda: self.mark_read(timeline_tip.event_id))
        # closedSignal 只在 closeEvent 触发。InfoBar 是 showArea 的子控件，
        # 主窗退出走析构不走 closeEvent，所以这里等价于「用户显式关掉了」
        info_bar.closedSignal.connect(lambda: self.mark_read(timeline_tip.event_id))

    def open_timeline(self, timeline_url: str) -> None:
        if self._browser_window is None:
            self._browser_window = BrowserWindow(self.gui, skip_env_mode=True, persistent_profile=True)
            self._browser_window.destroyed.connect(lambda *_args: setattr(self, "_browser_window", None))
        browser = self._browser_window
        browser._first_show = False
        browser.home_url = QUrl(timeline_url)
        browser.load_home()
        # 与文档按钮 open_url_by_browser 同几何：主窗 x/宽、屏高 5%–90%，右滑入场
        screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
        browser.setGeometry(QRect(
            self.gui.x(),
            int(screen_height * 0.05),
            self.gui.width(),
            int(screen_height * 0.9),
        ))
        PopupAnimator.show(browser, browser.geometry(), duration_ms=220, direction="right")
        browser.raise_()
        browser.activateWindow()

    def close(self) -> None:
        if self._browser_window is not None:
            self._browser_window.close()
            self._browser_window = None
