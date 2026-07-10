#!/usr/bin/python
# -*- coding: utf-8 -*-
from .splash_screen import *
from .text_componet import *
from .icons import *
from .flyout_kit import *
from .cust import *
from .badge import *

# updater exports UpdaterMessageBox — deferred to avoid pulling in
# all GUI.manager + deploy.update at import time.
_lazy = {'UpdaterMessageBox'}


def __getattr__(name):
    if name in _lazy:
        from . import updater
        value = getattr(updater, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
