#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import platform
import pathlib


class Env:
    default_sv_path = r"D:\Comic"

    def __init__(self, _p: pathlib.Path):
        self.proj_p = _p

    def env_init(self):
        ...

    @staticmethod
    def open_folder(_p):
        os.startfile(_p)


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
