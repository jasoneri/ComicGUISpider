from __future__ import annotations

import contextlib
import platform
import sys
import threading
import traceback


def _prime_windows_platform_cache() -> None:
    if sys.platform != "win32" or getattr(platform, "_uname_cache", None) is not None:
        return
    winver = sys.getwindowsversion()
    platform._uname_cache = platform.uname_result("Windows", "", str(winver.major), f"{winver.major}.{winver.minor}.{winver.build}", "")


_prime_windows_platform_cache()

import GUI.src.material_ct
import uvicorn
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
)
from qfluentwidgets import Action, FluentIcon as FIF

from utils.server_control import (
    DEFAULT_SERVER_BIND_HOST,
    DEFAULT_SERVER_MCP_PATH,
    ServerDiscoveryRecord,
    TRAY_SERVER_SURFACE,
    bind_tcp_socket,
    create_server_record,
    remove_server_record,
    server_launch_log_path,
    socket_port,
    sync_redviewer_server_endpoint,
    wait_for_server,
    write_server_record,
)
from utils.subscript import load_subscript
from utils.tray.event_log import TrayEventLog
from utils.tray.notification_policy import (
    ScheduleNotification,
    explain_schedule_blocker,
    explain_schedule_error,
    notification_for_schedule_blocker,
    notification_for_schedule_error,
    notification_for_schedule_result,
)
from utils.tray.schedule_presentation import SchedulePresentation, build_schedule_presentation, read_schedule_summary
from utils.tray.subscription_scheduler import ScheduleDecision, ScheduleStatus, SubscriptionScheduler, default_scheduler_state_path
from server.tray.dialog import ManageDialogController
from server.tray.mcp_panel import McpPanel
from server.tray.schedule_panel import SchedulePanel
from server.tray.server_panel import ServerPanel
from server.tray.ui_common import (
    ServerManageDialog,
    TrayUiContext,
    configure_tray_qt_fonts,
)
from utils import conf, temp_p
from variables import VER


class ServerRuntimeDownloadSubmitter:
    def __call__(self, site_index: int, payload, *, timeout_sec: int = 60) -> bool:
        from server.runtime import runtime

        return runtime.submit_payload_and_wait(site_index, payload, timeout_sec=timeout_sec, origin="subscription")


class ServerScheduleController:
    def __init__(self) -> None:
        self.event_log = TrayEventLog()
        self.scheduler = SubscriptionScheduler(load_subscript, state_path=default_scheduler_state_path())
        self.run_thread: threading.Thread | None = None
        self.last_result = "-"
        self.latest_summary: dict | None = None

    def status(self) -> ScheduleStatus | None:
        return self.scheduler.status()

    def events(self, limit: int = 20) -> list[dict]:
        return self.event_log.tail(limit)

    def refresh_summary(self) -> dict | None:
        try:
            self.latest_summary = read_schedule_summary()
        except FileNotFoundError:
            self.latest_summary = None
        return self.latest_summary

    def presentation(self, *, blocker: str = "") -> SchedulePresentation:
        cfg = load_subscript()
        return build_schedule_presentation(
            cfg, status=self.status(), cache_summary=self.refresh_summary(), events=self.events(20), blocker=blocker
        )


class ServerTrayHost(QObject):
    server_ready = Signal(int)
    server_failed = Signal(int, str)
    server_stopped = Signal(int)
    schedule_finished = Signal(object)
    schedule_failed = Signal(object)
    schedule_progress = Signal(object)

    def __init__(self, *, sock, record: ServerDiscoveryRecord):
        super().__init__()
        self.sock = sock
        self.record = record
        self.qt_app: QApplication | None = None
        self.ui = TrayUiContext(token_provider=lambda: self.record.token, app_provider=lambda: self.qt_app or QApplication.instance())
        self.tray_icon: QSystemTrayIcon | None = None
        self.menu: QMenu | None = None
        self.dialog = ManageDialogController(self)
        self.mcp_panel = McpPanel(self)
        self.status_timer: QTimer | None = None
        self.schedule_timer: QTimer | None = None
        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.ready_thread: threading.Thread | None = None
        self._server_generation = 0
        self._restart_requested = False
        self._previous_sys_excepthook = None
        self._previous_threading_excepthook = None
        self._installed_sys_excepthook = None
        self._installed_threading_excepthook = None
        self._last_notification_context = "Server"
        self.schedule = self._create_schedule_controller()
        self.schedule_panel = SchedulePanel(self)
        self.server_panel = ServerPanel(self)
        self.shutdown_requested = False
        self.state = "starting"
        self.error_detail = ""
        self.server_ready.connect(self._on_server_ready)
        self.server_failed.connect(self._on_server_failed)
        self.server_stopped.connect(self._on_server_stopped)
        self.schedule_finished.connect(self._on_schedule_finished)
        self.schedule_failed.connect(self._on_schedule_failed)
        self.schedule_progress.connect(self._on_schedule_progress)

    @property
    def manage_dialog(self) -> ServerManageDialog | None:
        return self.dialog.dialog

    @property
    def events_dialog(self) -> ServerManageDialog | None:
        return self.dialog.events_dialog

    def _create_schedule_controller(self) -> ServerScheduleController:
        return ServerScheduleController()

    def _install_exception_hooks(self) -> None:
        if self._previous_sys_excepthook is None:
            self._previous_sys_excepthook = sys.excepthook
            self._installed_sys_excepthook = self._server_excepthook
            sys.excepthook = self._installed_sys_excepthook
        if self._previous_threading_excepthook is None:
            self._previous_threading_excepthook = threading.excepthook
            self._installed_threading_excepthook = self._threading_excepthook
            threading.excepthook = self._installed_threading_excepthook

    def _restore_exception_hooks(self) -> None:
        if self._previous_sys_excepthook is not None and sys.excepthook is self._installed_sys_excepthook:
            sys.excepthook = self._previous_sys_excepthook
        if self._previous_threading_excepthook is not None and threading.excepthook is self._installed_threading_excepthook:
            threading.excepthook = self._previous_threading_excepthook
        self._previous_sys_excepthook = None
        self._previous_threading_excepthook = None
        self._installed_sys_excepthook = None
        self._installed_threading_excepthook = None

    def _server_excepthook(self, exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return self._delegate_sys_excepthook(exc_type, exc_value, exc_traceback)
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.error_detail = detail
        self.state = "error"
        self.server_panel.diagnostics.record_error("Uncaught server exception", detail)
        self._delegate_sys_excepthook(exc_type, exc_value, exc_traceback)

    def _threading_excepthook(self, args) -> None:
        thread_name = getattr(args.thread, "name", "unknown")
        detail = (
            f"thread: {thread_name}\n"
            + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        )
        self.error_detail = detail
        self.state = "error"
        self.server_panel.diagnostics.record_error("Uncaught server thread exception", detail)
        previous = self._previous_threading_excepthook or threading.__excepthook__
        previous(args)

    def _delegate_sys_excepthook(self, exc_type, exc_value, exc_traceback) -> None:
        previous = self._previous_sys_excepthook or sys.__excepthook__
        previous(exc_type, exc_value, exc_traceback)

    def run(self) -> int:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        configure_tray_qt_fonts(app)
        QApplication.setQuitOnLastWindowClosed(False)
        self.qt_app = app
        self._install_exception_hooks()
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                raise RuntimeError("CGS Server tray is unavailable")
            self._build_tray_icon()
            self.tray_icon.show()
            self._show_server_mode_notice()
            self._start_server()
        except Exception:
            self.shutdown()
            raise
        app.aboutToQuit.connect(self.shutdown)
        try:
            return app.exec()
        finally:
            self.shutdown()

    def _build_tray_icon(self) -> None:
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self._icon_for_state())
        self.tray_icon.setToolTip(self._tooltip())
        self.menu = self._build_menu()
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start()

    def _show_server_mode_notice(self) -> None:
        if self.tray_icon is None:
            return
        self._last_notification_context = "Server"
        self.tray_icon.showMessage("进入后台托盘模式", "可在系统托盘 / 菜单栏图标中管理 CGS Server", QSystemTrayIcon.MessageIcon.Information, 8000)

    def _start_schedule_timer(self) -> None:
        self.schedule_timer = QTimer(self)
        self.schedule_timer.setInterval(60_000)
        self.schedule_timer.timeout.connect(self._on_schedule_tick)
        self.schedule_timer.start()
        self._on_schedule_tick()

    def _build_menu(self) -> QMenu:
        self.menu = QMenu("CGS Server")
        manage_action = Action(FIF.APPLICATION, text="管理面板", parent=self, triggered=lambda _checked=False: self.show_manage_dialog())
        self.menu.addAction(manage_action)

        schedule_menu = QMenu("Schedule", self.menu)
        run_now = Action(FIF.PLAY, text="立刻执行", parent=self, triggered=lambda _checked=False: self.run_schedule_now())
        schedule_menu.addAction(run_now)
        self.menu.addMenu(schedule_menu)

        self.menu.addSeparator()
        quit_action = Action(FIF.POWER_BUTTON, text="退出", parent=self, triggered=lambda _checked=False: self.shutdown())
        self.menu.addAction(quit_action)
        return self.menu

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_manage_dialog("Server")

    @Slot()
    def _on_tray_message_clicked(self) -> None:
        self.show_manage_dialog(self._last_notification_context or "Server")

    def _start_server(self) -> None:
        self._server_generation += 1
        generation = self._server_generation
        from server.api import create_app
        from server.mcp import create_runtime_mcp_surface

        mcp_surface = create_runtime_mcp_surface(mount_path=DEFAULT_SERVER_MCP_PATH)
        self.mcp_panel.set_call_log(mcp_surface.call_log)
        app = create_app(surfaces=(mcp_surface,), auth_token=self.record.token)
        write_server_record(self.record)
        config = uvicorn.Config(app, host=self.record.bind_host, port=self.record.port, log_level="info")
        self.server = uvicorn.Server(config)
        endpoint = self.record.endpoint
        self.server_thread = threading.Thread(
            target=self._run_server, args=(generation, self.server, self.sock), name="CGSServerHTTP", daemon=True
        )
        self.server_thread.start()
        self.ready_thread = threading.Thread(
            target=self._wait_for_server_ready, args=(generation, endpoint), name="CGSServerReady", daemon=True
        )
        self.ready_thread.start()
        self.refresh_status()

    def _run_server(self, generation: int, server: uvicorn.Server, sock) -> None:
        try:
            server.run(sockets=[sock])
        except Exception:
            self.server_failed.emit(generation, traceback.format_exc())
            return
        self.server_stopped.emit(generation)

    def _wait_for_server_ready(self, generation: int, endpoint) -> None:
        try:
            wait_for_server(endpoint, timeout=30.0)
            sync_redviewer_server_endpoint(endpoint)
        except Exception:
            if self.server is not None:
                self.server.should_exit = True
            self.server_failed.emit(generation, traceback.format_exc())
            return
        self.server_ready.emit(generation)

    @Slot(int)
    def _on_server_ready(self, generation: int) -> None:
        if generation != self._server_generation:
            return
        if self.shutdown_requested or self.state == "error":
            return
        self.state = "ready"
        self.error_detail = ""
        if self.schedule_timer is None:
            self._start_schedule_timer()
        self.refresh_status(schedule_full=True)

    @Slot(int, str)
    def _on_server_failed(self, generation: int, detail: str) -> None:
        if generation != self._server_generation:
            return
        self.error_detail = detail
        self.server_panel.diagnostics.record_error("Server failed", detail)
        self.state = "error"
        self._remove_record()
        self.refresh_status(schedule_full=True)

    @Slot(int)
    def _on_server_stopped(self, generation: int) -> None:
        if generation != self._server_generation:
            return
        self._remove_record()
        if not self.shutdown_requested and not self._restart_requested:
            self.state = "error"
            self.error_detail = "CGS Server HTTP surface stopped unexpectedly"
            self.server_panel.diagnostics.record_error("Server stopped unexpectedly", self.error_detail)
            self.refresh_status(schedule_full=True)

    @Slot()
    def show_events(self) -> None:
        self.show_manage_dialog("Server")

    @Slot()
    def show_manage_dialog(self, tab_name: str = "Server") -> None:
        self.dialog.show(tab_name)

    @Slot()
    def restart_server_surface(self) -> None:
        blocker = self._server_restart_blocker()
        if blocker:
            self.server_panel.diagnostics.record_error("Server restart blocked", blocker)
            self.refresh_status(schedule_full=True)
            return
        self._restart_requested = True
        self.state = "starting"
        self.error_detail = "Restarting CGS Server / MCP surface"
        self.refresh_status(schedule_full=True)
        try:
            self._stop_current_server_surface()
            self.sock = bind_tcp_socket(DEFAULT_SERVER_BIND_HOST, 0)
            self.record = create_server_record(
                bind_host=DEFAULT_SERVER_BIND_HOST, port=socket_port(self.sock),
                surfaces=("http", "mcp", TRAY_SERVER_SURFACE), version=VER,
            )
            self.dialog.refresh_title()
            self.mcp_panel.on_surface_restarted()
            self._start_server()
        except Exception:
            detail = traceback.format_exc()
            self.state = "error"
            self.error_detail = detail
            self.server_panel.diagnostics.record_error("Server restart failed", detail)
            self.refresh_status(schedule_full=True)
            raise
        finally:
            self._restart_requested = False

    def _server_restart_blocker(self) -> str:
        if self.schedule.run_thread is not None and self.schedule.run_thread.is_alive():
            return "subscription schedule run is active"
        status = self.runtime_status_payload()
        runtime_status = str(status.get("status") or "")
        job = status.get("job") if isinstance(status.get("job"), dict) else None
        job_status = str((job or {}).get("status") or runtime_status)
        if job_status in {"starting", "running"}:
            return self.ui.redact(f"CGS Server job is active: {job_status}")
        return ""

    def _stop_current_server_surface(self) -> None:
        self._server_generation += 1
        old_server = self.server
        old_server_thread = self.server_thread
        old_ready_thread = self.ready_thread
        old_sock = self.sock
        self.server = None
        self.server_thread = None
        self.ready_thread = None
        errors: list[str] = []
        first_error: BaseException | None = None
        if old_server is not None:
            old_server.should_exit = True
        if old_server_thread is not None and old_server_thread is not threading.current_thread() and old_server_thread.is_alive():
            old_server_thread.join(timeout=5)
            if old_server_thread.is_alive():
                errors.append("CGS Server HTTP surface did not stop")
        if old_ready_thread is not None and old_ready_thread is not threading.current_thread() and old_ready_thread.is_alive():
            old_ready_thread.join(timeout=1)
        from server.runtime import runtime

        try:
            runtime.shutdown(timeout=5)
        except Exception as exc:
            first_error = exc
            errors.append(str(exc))
        self._remove_record()
        with contextlib.suppress(OSError):
            old_sock.close()
        if errors:
            message = "; ".join(error for error in errors if error)
            if first_error is not None:
                raise RuntimeError(message) from first_error
            raise RuntimeError(message)

    @Slot()
    def run_schedule_now(self) -> None:
        self._start_schedule_run("manual run requested")

    @Slot()
    def _on_schedule_tick(self) -> None:
        try:
            decision = self.schedule.scheduler.evaluate()
        except Exception as exc:
            self._on_schedule_failed(exc)
            return
        if decision is None:
            self.refresh_status(schedule_full=True)
            return
        self._start_schedule_run(decision.reason, decision)

    def _start_schedule_run(self, detail: str, decision: ScheduleDecision | None = None) -> bool:
        blocker = self.schedule_run_blocker()
        if blocker:
            self.schedule.event_log.append("subscription", result="skip", detail=explain_schedule_blocker(blocker))
            self._show_schedule_notification(notification_for_schedule_blocker(blocker, trigger=detail))
            self.refresh_status(schedule_full=True)
            return False
        if self.schedule.run_thread is not None and self.schedule.run_thread.is_alive():
            blocker = "subscription run already in progress"
            self.schedule.event_log.append("subscription", result="skip", detail=explain_schedule_blocker(blocker))
            self._show_schedule_notification(notification_for_schedule_blocker(blocker, trigger=detail))
            self.refresh_status(schedule_full=True)
            return False
        self.schedule.run_thread = threading.Thread(target=self._run_schedule_once, args=(detail,), name="CGSServerScheduleRun", daemon=True)
        try:
            self.schedule.run_thread.start()
        except Exception as exc:
            self.schedule.run_thread = None
            self._on_schedule_failed(exc)
            return False
        self.schedule.event_log.append("subscription", result="start", detail=detail)
        if decision is not None:
            self.schedule.scheduler.mark_triggered(decision)
        self.schedule_panel.start_run_state(detail)
        self.refresh_status(schedule_full=True)
        return True

    def schedule_run_blocker(self) -> str:
        if self.state != "ready":
            return f"CGS Server is not ready: {self.state}"
        status = self.runtime_status_payload()
        runtime_status = str(status.get("status") or "")
        if runtime_status and runtime_status != "idle":
            reason = status.get("reason") or runtime_status
            return self.ui.redact(f"CGS Server runtime is not idle: {reason}")
        if status.get("available") is False:
            return self.ui.redact("CGS Server runtime is unavailable")
        return ""

    def _run_schedule_once(self, trigger: str) -> None:
        try:
            from utils.tray.subscription_runner import SubscriptionRunner

            runner = SubscriptionRunner(
                download_submitter=ServerRuntimeDownloadSubmitter(),
                progress_callback=self.schedule_progress.emit,
            )
            try:
                summary = runner.run_once()
                summary.trigger = trigger
            finally:
                runner.shutdown()
        except Exception as exc:
            self.schedule_failed.emit(exc)
            return
        self.schedule_finished.emit(summary)

    @Slot(object)
    def _on_schedule_finished(self, summary) -> None:
        self.schedule.last_result = getattr(summary, "message", str(summary))
        self.schedule.event_log.append("subscription", result="ok", detail=self.schedule.last_result)
        self.schedule_panel.finish_run_state()
        self._show_schedule_notification(notification_for_schedule_result(summary, trigger=getattr(summary, "trigger", "")))
        self.refresh_status(schedule_full=True)

    @Slot(object)
    def _on_schedule_failed(self, exc: BaseException) -> None:
        error_message = explain_schedule_error(exc)
        self.schedule.last_result = f"error: {error_message}"
        self.schedule.event_log.append("subscription", result="error", detail=error_message, exc=exc)
        self.state = "error" if self.state == "starting" else self.state
        self.server_panel.diagnostics.record_error("Schedule failed", "".join(traceback.format_exception(exc)))
        self.schedule_panel.fail_run_state(exc)
        self._show_schedule_notification(notification_for_schedule_error(exc, trigger="schedule"))
        self.refresh_status(schedule_full=True)

    def _show_schedule_notification(self, notification: ScheduleNotification | None) -> None:
        if notification is None or self.tray_icon is None:
            return
        self._last_notification_context = notification.context or "Schedule"
        icon = {
            "error": QSystemTrayIcon.MessageIcon.Critical,
            "warning": QSystemTrayIcon.MessageIcon.Warning,
        }.get(notification.level, QSystemTrayIcon.MessageIcon.Information)
        self.tray_icon.showMessage(notification.title, self.ui.redact(notification.message), icon, 8000)

    @Slot(object)
    def _on_schedule_progress(self, snap: dict) -> None:
        """Live in-memory run-state update marshalled from the runner thread (no disk read)."""
        self.schedule_panel.update_run_state(snap)
        if self.manage_dialog is not None and self.manage_dialog.isVisible():
            self.schedule_panel.refresh_live()

    @Slot()
    def shutdown(self) -> None:
        if self.shutdown_requested:
            return
        self.shutdown_requested = True
        self._restore_exception_hooks()
        if self.status_timer is not None:
            self.status_timer.stop()
            self.status_timer = None
        if self.schedule_timer is not None:
            self.schedule_timer.stop()
            self.schedule_timer = None
        self._stop_current_server_surface()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        app = self.qt_app or QApplication.instance()
        if app is not None:
            app.quit()

    def _remove_record(self) -> None:
        remove_server_record(self.record)

    @Slot()
    def refresh_status(self, *, schedule_full: bool = False) -> None:
        if self.tray_icon is not None:
            self.tray_icon.setIcon(self._icon_for_state())
            self.tray_icon.setToolTip(self._tooltip())
        if self.dialog.is_visible():
            self.dialog.refresh(schedule_full=schedule_full)

    def _status_label(self) -> str:
        return f"CGS Server: {self.projected_state()}"

    def _schedule_label(self) -> str:
        try:
            status = self.schedule.status()
        except Exception as exc:
            return f"Schedule: error {self.ui.redact(str(exc))}"
        next_run = status.next_run_at.isoformat(timespec="minutes") if status.next_run_at is not None else "-"
        running = self.schedule.run_thread is not None and self.schedule.run_thread.is_alive()
        state = "running" if running else status.mode
        return f"Schedule: {state} next={next_run}"

    def _tooltip(self) -> str:
        base = (
            f"CGS Server\n"
            f"state={self.projected_state()}\n"
            f"schedule={self._schedule_label()}\n"
            f"mcp={self.mcp_panel.status_label()}\n"
            f"url={self.record.connect_url}\n"
            f"mcp_path={DEFAULT_SERVER_MCP_PATH}"
        )
        if self.error_detail:
            return f"{base}\nerror={self.last_error_line()}"
        return base

    def version_label(self) -> str:
        version = str(self.record.version or VER)
        return version if version.lower().startswith("v") else f"v{version}"

    def last_error_line(self) -> str:
        return self.ui.redact(self.error_detail.splitlines()[-1])

    def runtime_status_payload(self) -> dict:
        try:
            from server.runtime import runtime

            return runtime.status()
        except Exception as exc:
            return {"status": "error", "available": False, "reason": self.ui.redact(str(exc))}

    def surfaces_label(self) -> str:
        labels = {"http": "HTTP API", "mcp": "MCP", TRAY_SERVER_SURFACE: "Tray"}
        return " · ".join(labels.get(surface, str(surface)) for surface in self.record.surfaces)

    def projected_state(self) -> str:
        if self.state != "ready":
            return self.state
        status = resolve_runtime_status()
        if status == "idle":
            return "ready"
        if status == "unavailable":
            return "foreground-blocked"
        return str(status or "ready")

    def _icon_for_state(self):
        return QIcon(":/CGS-logo.png")


def resolve_runtime_status() -> str:
    from server.runtime import runtime

    return runtime.status().get("status")
