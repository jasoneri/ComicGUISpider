import sys
from PySide6.QtCore import QTimer


def safe_single_shot(msec, callback):
    """Legacy helper retained for existing call sites only.

    Do not use this in new or updated code. Timer exception routing now relies on
    the native ``QTimer.singleShot -> sys.excepthook -> SpiderGUI.hook_exception``
    chain verified by ``tt_gui_ai`` smoke. Keep this helper only until old call
    sites are migrated away.
    """
    def guarded():
        try:
            callback()
        except Exception:
            sys.excepthook(*sys.exc_info())
    QTimer.singleShot(msec, guarded)
