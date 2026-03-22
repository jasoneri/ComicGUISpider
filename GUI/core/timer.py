import sys
from PySide6.QtCore import QTimer


def safe_single_shot(msec, callback):
    def guarded():
        try:
            callback()
        except Exception:
            sys.excepthook(*sys.exc_info())
    QTimer.singleShot(msec, guarded)
