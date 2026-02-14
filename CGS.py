# -*- coding: utf-8 -*-
import os
import sys
import traceback
from datetime import datetime
from multiprocessing import freeze_support
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

# from multiprocessing.managers import RemoteError
# sys.setrecursionlimit(5000)


def _append_fatal_log(phase, trace_text):
    log_path = Path.cwd().joinpath("cgs_fatal.log")
    timestamp = datetime.now().isoformat()
    payload = (
        f"\n=== Fatal error at {timestamp} ({phase}) ===\n"
        f"python: {sys.executable}\n"
        f"cwd: {Path.cwd()}\n"
        f"{trace_text}"
    )
    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(payload)
    except OSError:
        pass
    return log_path


def _raise_with_context(exc, phase):
    trace_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_path = _append_fatal_log(phase, trace_text)
    msg = (
        f"[CGS Fatal] startup failed\n"
        f"phase: {phase}\n"
        f"error: {type(exc).__name__}: {exc}\n\n"
        f"trace log: {log_path}\n"
    )
    if sys.stderr is not None:
        try:
            sys.stderr.write("\n" + msg + "\n")
        except OSError:
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    box = QMessageBox()
    box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle("CGS Fatal Error")
    box.setText(msg)
    box.exec_()
    raise


def start():
    freeze_support()
    try:
        from GUI.gui import SpiderGUI
        import GUI.src.material_ct  # noqa: F401
    except Exception as exc:
        _raise_with_context(exc, "import GUI modules")

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
        sys.excepthook = ui.hook_exception
        QApplication.processEvents()
        app.exec_()
    except Exception as exc:
        _raise_with_context(exc, "initialize QApplication")


if __name__ == "__main__":
    start()
