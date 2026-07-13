# -*- coding: utf-8 -*-
from utils.middleware.presets.auto_select_first import AutoSelectFirst
from utils.middleware.presets.auto_select_inverse import AutoSelectLatest
from utils.middleware.presets.c3_feature_diff import FeatureDiff
from utils.middleware.presets.cbz_post_processor import CBZPostProcessor
from utils.middleware.presets.d2_episode_diff import D2EpisodeDiff
from utils.middleware.presets.e2_publish_metadata import E2PublishMetadata


def register_presets(manager):
    manager.register_middleware("auto_select_first", AutoSelectFirst)
    manager.register_middleware("auto_select_latest", AutoSelectLatest)
    manager.register_middleware("cbz_post_processor", CBZPostProcessor)
    manager.register_middleware("c3_feature_diff", FeatureDiff)
    manager.register_middleware("d2_episode_diff", D2EpisodeDiff)
    manager.register_middleware("e2_publish_metadata", E2PublishMetadata)
