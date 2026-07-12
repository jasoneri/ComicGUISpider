# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import threading
import traceback
import contextlib
from datetime import datetime
from multiprocessing import freeze_support
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from utils import install_qfluentwidgets_notice_filter


install_qfluentwidgets_notice_filter()


class ExceptionRouter:
    def __init__(self):
        self._runtime_handler = None

    def bind_runtime_handler(self, runtime_handler):
        self._runtime_handler = runtime_handler

    def install(self):
        sys.excepthook = self.excepthook

    def raise_fatal(self, exc, phase):
        trace_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log_path = self._append_fatal_log(phase, trace_text)
        msg = (
            f"[CGS Fatal] startup failed\n"
            f"phase: {phase}\n"
            f"error: {type(exc).__name__}: {exc}\n\n"
            f"trace log: {log_path}\n"
        )
        self._write_stderr("\n" + msg + "\n")
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("CGS Fatal Error")
        box.setText(msg)
        box.exec()
        raise

    def show_server_launch_error(self, exc):
        trace_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log_path = self._append_fatal_log("launch CGS Server", trace_text)
        msg = (
            "CGS Server 启动失败。\n"
            "当前 GUI 已关闭，但 Server 没有完成 tray/HTTP 就绪。\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"trace log: {log_path}"
        )
        self._write_stderr("\n" + msg + "\n")
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("CGS Server 启动失败")
        box.setText("CGS Server 启动失败")
        box.setInformativeText("Server 没有完成 tray/HTTP 就绪。详情已写入日志。")
        box.setDetailedText(msg)
        box.exec()

    def excepthook(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        self.handle_exception(exc_type, exc_value, exc_traceback, phase="uncaught exception")

    def handle_current_exception(self, phase):
        self.handle_exception(*sys.exc_info(), phase=phase)

    def handle_exception(self, exc_type, exc_value, exc_traceback, phase):
        if self._runtime_handler is not None:
            return self._runtime_handler(exc_type, exc_value, exc_traceback)
        trace_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_path = self._append_fatal_log(phase, trace_text)
        self._write_stderr(f"\n[CGS uncaught] log: {log_path}\n{trace_text}\n")

    def _resolve_fatal_log_path(self):
        """Prefer writable runtime-adjacent paths in portable mode."""
        exe_dir = Path(sys.executable).resolve().parent
        candidates = []
        for marker_dir in (exe_dir, exe_dir.parent):
            if marker_dir.joinpath("_pystand_static.int").exists():
                candidates.append(marker_dir.joinpath("cgs_fatal.log"))
        candidates.extend([
            Path.cwd().joinpath("cgs_fatal.log"),
            exe_dir.joinpath("cgs_fatal.log"),
            exe_dir.parent.joinpath("cgs_fatal.log"),
        ])
        seen = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                return path
            except OSError:
                continue
        return Path.cwd().joinpath("cgs_fatal.log")

    def _append_fatal_log(self, phase, trace_text):
        log_path = self._resolve_fatal_log_path()
        timestamp = datetime.now().isoformat()
        payload = (
            f"\n=== Fatal error at {timestamp} ({phase}) ===\n"
            f"python: {sys.executable}\n"
            f"cwd: {Path.cwd()}\n"
            f"log_path: {log_path}\n"
            f"{trace_text}"
        )
        with contextlib.suppress(OSError):
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(payload)
        return log_path

    def _write_stderr(self, message):
        if sys.stderr is None:
            return
        with contextlib.suppress(OSError):
            sys.stderr.write(message)


EXCEPTION_ROUTER = ExceptionRouter()


class ServerForegroundClaim:
    def __init__(self):
        self.endpoint = None
        self._release_requested = False
        self._released = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._enter_foreground, name="CGSServerForegroundClaim")

    def start(self):
        self._thread.start()

    def release(self):
        with self._lock:
            self._release_requested = True
            endpoint = self.endpoint
            should_leave = endpoint is not None and not self._released
            if should_leave:
                self._released = True
        if should_leave:
            self._leave_foreground(endpoint)
        if self._thread.is_alive():
            self._thread.join()

    def _enter_foreground(self):
        try:
            from utils.server_control import notify_server_foreground

            endpoint = notify_server_foreground("/foreground/enter")
            release_now = False
            with self._lock:
                self.endpoint = endpoint
                release_now = self._release_requested and endpoint is not None and not self._released
                if release_now:
                    self._released = True
            if release_now:
                self._leave_foreground(endpoint)
        except Exception:
            EXCEPTION_ROUTER.handle_current_exception("enter CGS Server foreground")

    def _leave_foreground(self, endpoint):
        from utils.server_control import notify_server_foreground

        notify_server_foreground("/foreground/leave", endpoint=endpoint)


def _run_gui_app(SpiderGUI) -> bool:
    from GUI.core.exception_feedback import (
        GuiExceptionCoordinator,
        GuiExceptionFeedbackDispatcher,
        SpiderGuiExceptionPresenter,
    )
    from utils import conf

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    ui = SpiderGUI()
    feedback_dispatcher = GuiExceptionFeedbackDispatcher(app)
    exception_coordinator = GuiExceptionCoordinator(
        logger=ui.log,
        dispatcher=feedback_dispatcher,
        log_path=conf.log_path.joinpath("GUI.log"),
    )
    EXCEPTION_ROUTER.bind_runtime_handler(exception_coordinator.handle_exception)
    ui.exception_feedback_dispatcher = feedback_dispatcher
    ui.exception_feedback_scope_registration = feedback_dispatcher.register_scope(
        owner=ui,
        surfaces=(),
        presenter=SpiderGuiExceptionPresenter(ui._show_exception_feedback, ui.res.global_err_hook),
    )
    QApplication.processEvents()
    foreground_claim = ServerForegroundClaim()

    try:
        foreground_claim.start()
        ui.start_post_first_paint_setup()
        app.exec()
        return ui.server_mode_switch_requested
    finally:
        foreground_claim.release()


def _launch_subscription_tray():
    return subprocess.Popen(
        [sys.executable, "-m", "utils.tray"],
        cwd=Path(__file__).resolve().parent,
    )


def start():
    freeze_support()
    EXCEPTION_ROUTER.install()
    try:
        from GUI.gui import SpiderGUI
        import GUI.src.material_ct  # noqa: F401
    except Exception as exc:
        EXCEPTION_ROUTER.raise_fatal(exc, "import GUI modules")

    if os.environ.get("CGS_CHECK_MODE") == "1":
        return

    try:
        server_mode_requested = _run_gui_app(SpiderGUI)
    except Exception as exc:
        EXCEPTION_ROUTER.raise_fatal(exc, "initialize QApplication")
    if server_mode_requested:
        try:
            from utils.server_control import ServerLauncher

            ServerLauncher().launch_or_resolve()
        except Exception as exc:
            EXCEPTION_ROUTER.show_server_launch_error(exc)
            raise SystemExit(1) from exc


if __name__ == "__main__":
    start()
