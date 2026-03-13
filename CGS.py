# -*- coding: utf-8 -*-
import os
import sys
import traceback
from datetime import datetime
from multiprocessing import freeze_support
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox


class ExceptionRouter:
    def __init__(self):
        self.ui = None

    def bind_ui(self, ui):
        self.ui = ui

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
        box.exec_()
        raise

    def excepthook(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        self.handle_exception(
            exc_type,
            exc_value,
            exc_traceback,
            phase="uncaught exception",
        )

    def handle_current_exception(self, phase):
        self.handle_exception(*sys.exc_info(), phase=phase)

    def handle_exception(self, exc_type, exc_value, exc_traceback, phase):
        if self.ui is not None:
            try:
                self.ui.hook_exception(exc_type, exc_value, exc_traceback)
                return
            except Exception:
                trace_text = "".join(traceback.format_exception(*sys.exc_info()))
                log_path = self._append_fatal_log("hook_exception failed", trace_text)
                self._write_stderr(f"\n[CGS hook_exception failed] log: {log_path}\n{trace_text}\n")
                return sys.__excepthook__(*sys.exc_info())

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
                with open(path, "a", encoding="utf-8"):
                    pass
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
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(payload)
        except OSError:
            pass
        return log_path

    @staticmethod
    def _write_stderr(message):
        if sys.stderr is None:
            return
        try:
            sys.stderr.write(message)
        except OSError:
            pass


EXCEPTION_ROUTER = ExceptionRouter()


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
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setPalette(app.style().standardPalette())
        ui = SpiderGUI()
        EXCEPTION_ROUTER.bind_ui(ui)
        QApplication.processEvents()
        app.exec_()
    except Exception as exc:
        EXCEPTION_ROUTER.raise_fatal(exc, "initialize QApplication")


if __name__ == "__main__":
    start()
