# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QListWidget,
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
)
from qfluentwidgets import Action, FluentIcon as FIF

from utils.tray.event_log import TrayEventLog
from utils.tray.subscription_scheduler import ScheduleDecision, ScheduleStatus, SubscriptionScheduler, default_scheduler_state_path
from utils.tray.subscription_runner import SubscriptionRunner, SubscriptionRunSummary


class IconState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class TrayApp(QObject):
    request_run_now = Signal()
    _run_finished = Signal(object)
    _run_failed = Signal(object)

    def __init__(
        self,
        event_log: Optional[TrayEventLog] = None,
        runner: Optional[SubscriptionRunner] = None,
        scheduler: Optional[SubscriptionScheduler] = None,
    ) -> None:
        super().__init__()
        self.event_log = event_log or TrayEventLog()
        self._runner = runner or SubscriptionRunner()
        self._scheduler = scheduler or SubscriptionScheduler(self._runner.load_config, state_path=default_scheduler_state_path())
        self._scheduler_timer: Optional[QTimer] = None
        self._run_thread: Optional[threading.Thread] = None
        self._qt_app: Optional[QApplication] = None
        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._events_dialog: Optional[QDialog] = None
        self.icon_state = IconState.IDLE
        self._status_error_detail: Optional[str] = None
        self._run_finished.connect(self._on_run_finished)
        self._run_failed.connect(self._on_run_failed)

    def run(self) -> int:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)
        self._qt_app = app
        self._build_tray_icon()
        self._start_scheduler()
        self._tray_icon.show()
        self._show_startup_notice()
        try:
            return app.exec()
        finally:
            self.shutdown()

    def set_icon_state(self, state: IconState) -> None:
        self.icon_state = state
        if self._tray_icon is not None:
            self._tray_icon.setIcon(self._icon_for_state(state))

    def _build_tray_icon(self) -> None:
        self._tray_icon = QSystemTrayIcon()
        self._update_tray_tooltip()
        self._tray_icon.setIcon(self._icon_for_state(self.icon_state))
        self._menu = self._build_menu()
        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _start_scheduler(self) -> None:
        if self._scheduler_timer is not None:
            self._scheduler_timer.stop()
        self._scheduler_timer = QTimer(self)
        self._scheduler_timer.setInterval(60_000)
        self._scheduler_timer.timeout.connect(self._on_schedule_tick)
        self._scheduler_timer.start()
        self._on_schedule_tick()

    def _build_menu(self) -> QMenu:
        self._menu = QMenu("ComicGUISpider")

        run_now = Action(FIF.PLAY, text="立刻执行", parent=self, triggered=self._emit_run_now)
        self._menu.addAction(run_now)

        show_events = Action(FIF.HISTORY, text="最近事件", parent=self, triggered=self.show_event_log)
        self._menu.addAction(show_events)

        self._menu.addSeparator()

        quit_action = Action(FIF.POWER_BUTTON, text="退出", parent=self, triggered=self.shutdown)
        self._menu.addAction(quit_action)
        return self._menu

    def _show_startup_notice(self) -> None:
        if self._tray_icon is None:
            return
        self._tray_icon.showMessage(
            "ComicGUISpider 后台托盘已启动",
            "可在系统托盘图标中执行订阅任务或查看最近事件。",
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )

    def _icon_for_state(self, state: IconState) -> QIcon:
        asset_path = Path(__file__).with_name("assets") / f"tray_{state.value}.png"
        if asset_path.exists():
            return QIcon(str(asset_path))

        app = self._qt_app or QApplication.instance()
        style = app.style() if app is not None else None
        if style is None:
            return QIcon()
        fallback = {
            IconState.IDLE: QStyle.StandardPixmap.SP_ComputerIcon,
            IconState.RUNNING: QStyle.StandardPixmap.SP_BrowserReload,
            IconState.ERROR: QStyle.StandardPixmap.SP_MessageBoxCritical,
        }[state]
        return style.standardIcon(fallback)

    @Slot()
    def _emit_run_now(self) -> None:
        self.request_run_now.emit()
        self._start_subscription_run("manual run requested")

    def _start_subscription_run(self, detail: str, decision: Optional[ScheduleDecision] = None) -> bool:
        if self._run_thread is not None and self._run_thread.is_alive():
            self.event_log.append("subscription", result="skip", detail="subscription run already in progress")
            return False
        self._run_thread = threading.Thread(target=self._run_subscription_once, name="CGSSubscriptionRunNow", daemon=True)
        try:
            self._run_thread.start()
        except Exception as exc:
            self._run_thread = None
            self._on_run_failed(exc)
            return False
        self.set_icon_state(IconState.RUNNING)
        self.event_log.append("subscription", result="start", detail=detail)
        if decision is not None:
            self._scheduler.mark_triggered(decision)
        return True

    @Slot()
    def _on_schedule_tick(self) -> None:
        try:
            decision = self._scheduler.evaluate()
            if decision is not None:
                self._start_subscription_run(decision.reason, decision)
        except Exception as exc:
            self._on_run_failed(exc)
            return
        if decision is None:
            self._update_tray_tooltip()
            return
        self._update_tray_tooltip()

    def _run_subscription_once(self) -> None:
        try:
            summary = self._runner.run_once()
        except Exception as exc:
            self._run_failed.emit(exc)
            return
        self._run_finished.emit(summary)

    @Slot(object)
    def _on_run_finished(self, summary: SubscriptionRunSummary) -> None:
        self.set_icon_state(IconState.IDLE)
        self.event_log.append("subscription", result="ok", detail=summary.message)
        self._update_tray_tooltip()

    @Slot(object)
    def _on_run_failed(self, exc: BaseException) -> None:
        self.set_icon_state(IconState.ERROR)
        self.event_log.append("subscription", result="error", detail=str(exc), exc=exc)
        self._update_tray_tooltip()

    @Slot()
    def show_event_log(self) -> None:
        dialog = QDialog()
        dialog.setWindowTitle("最近事件")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self._format_status(self._schedule_status()), dialog))
        event_list = QListWidget(dialog)
        for entry in self.event_log.tail(20):
            event_list.addItem(self._format_event(entry))
        layout.addWidget(event_list)
        dialog.setMinimumSize(720, 360)
        self._events_dialog = dialog
        dialog.show()

    def _update_tray_tooltip(self) -> None:
        if self._tray_icon is not None:
            self._tray_icon.setToolTip(f"ComicGUISpider subscription tray\n{self._format_status(self._schedule_status())}")

    def _schedule_status(self) -> Optional[ScheduleStatus]:
        try:
            status = self._scheduler.status()
        except Exception as exc:
            detail = f"schedule status failed: {exc}"
            if detail != self._status_error_detail:
                self._status_error_detail = detail
                self.set_icon_state(IconState.ERROR)
                self.event_log.append("subscription", result="error", detail=detail, exc=exc)
            return None
        self._status_error_detail = None
        return status

    @staticmethod
    def _format_status(status: Optional[ScheduleStatus]) -> str:
        if status is None:
            return "mode=unknown next=-"
        next_run = status.next_run_at.isoformat(timespec="minutes") if status.next_run_at is not None else "-"
        return f"{status.summary} next={next_run}"

    @staticmethod
    def _format_event(entry: dict) -> str:
        ts = entry.get("ts", "")
        kind = entry.get("kind", "")
        result = entry.get("result", "")
        book = entry.get("book") or "-"
        detail = entry.get("detail", "")
        return f"{ts} [{kind}/{result}] {book} {detail}".strip()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_event_log()

    @Slot()
    def shutdown(self) -> None:
        if self._scheduler_timer is not None:
            self._scheduler_timer.stop()
            self._scheduler_timer = None
        self._runner.shutdown()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        app = self._qt_app or QApplication.instance()
        if app is not None:
            app.quit()
