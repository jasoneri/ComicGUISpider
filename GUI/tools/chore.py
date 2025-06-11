from copy import deepcopy

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from utils import curr_os


class CopyUnfinished:
    copy_delay = 150 if curr_os != "macOS" else 300
    copied = 0
    
    def __init__(self, tasks):
        self.tasks = deepcopy(tasks)
        self.length = len(self.tasks)

    def to_clip(self):
        def copy_to_clipboard(text):
            QApplication.clipboard().setText(text)
        for i, task in enumerate(self.tasks):
            QTimer.singleShot(self.copy_delay * (i + 1), 
                lambda t=task.title_url: copy_to_clipboard(t))
