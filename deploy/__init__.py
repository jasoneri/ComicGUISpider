#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import platform
import pathlib
import subprocess


class Env:
    default_sv_path = r"D:\Comic"
    default_clip_db = pathlib.Path.home().joinpath(r"AppData\Roaming\Ditto\Ditto.db")
    clip_sql = "SELECT `mText` FROM `MAIN` order by `LID` desc"
    shell = "powershell"

    def __init__(self, _p: pathlib.Path):
        self.proj_p = _p
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = str(
            proj_path.parent.joinpath(r"site-packages\PyQt5\Qt5\plugins\platforms"))

    def env_init(self):
        ...

    @staticmethod
    def open_folder(_p):
        os.startfile(_p)

    @staticmethod
    def open_file(_f):
        subprocess.run(["start", "", f"{_f}"], shell=True, check=True)


proj_path = pathlib.Path(__file__).parent.parent
curr_os_module = Env
if platform.system().startswith("Darwin"):
    import sys
    sys.path.append(str(proj_path))
    from deploy.launcher.mac import macOS
    curr_os_module = macOS
curr_os = curr_os_module(proj_path)

if __name__ == '__main__':
    curr_os.env_init()
