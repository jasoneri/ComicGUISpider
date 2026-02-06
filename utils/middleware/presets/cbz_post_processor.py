# -*- coding: utf-8 -*-
from utils.middleware.executor import Action
from utils.middleware.timeline import TimelineStage


class CBZPostProcessor:
    def __init__(self, **params):
        self.params = params

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.POSTPROCESSING:
            return None
        return Action(
            kind="postprocess_cbz",
            payload={},
            stop_propagation=False,
        )
