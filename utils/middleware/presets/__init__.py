# -*- coding: utf-8 -*-
from utils.middleware.presets.auto_select_first import AutoSelectFirst
from utils.middleware.presets.auto_select_latest import AutoSelectLatest
from utils.middleware.presets.cbz_post_processor import CBZPostProcessor


def register_presets(manager):
    manager.register_middleware("auto_select_first", AutoSelectFirst)
    manager.register_middleware("auto_select_latest", AutoSelectLatest)
    manager.register_middleware("cbz_post_processor", CBZPostProcessor)
