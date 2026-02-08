# -*- coding: utf-8 -*-
from utils.middleware.executor import Action
from utils.middleware.timeline import TimelineStage


class AutoSelectLatest:
    def __init__(self, **params):
        self.params = params

    def on_event(self, stage: TimelineStage, ctx):
        # todo[0] 
        return Action(
            kind="send_input_state",
            payload={"input_state": ctx.input_state},
            stop_propagation=True,
        )
