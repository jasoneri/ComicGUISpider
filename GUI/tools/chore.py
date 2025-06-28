from copy import deepcopy

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from assets import res
from utils import curr_os, ori_path


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


class TextUtils:
    @staticmethod
    def description():
        return r"""<style>* {margin: 1px;padding: 1px;}</style><div>
    <div style="text-align: center;align-items: center;height: 75px">
        <img alt="描述" src="%s" height="128"><span style="font-weight: bold;font-size: 40px">CGS</span>
    </div>
    <div style="color: blue">
        <p>%s</p>
        <p>%s<span style="color: white"> %s</span></p>
        <hr><p></p>
    </div></div>
    """ % (rf'file:///{ori_path.joinpath("docs/public/CGS-girl.png")}',
             res.GUI.DESC1 % rf'file:///{ori_path.joinpath("assets/config_icon.png")}', 
             res.GUI.DESC2, res.GUI.DESC_ELSE)
