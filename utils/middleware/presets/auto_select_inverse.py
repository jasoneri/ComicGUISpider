# -*- coding: utf-8 -*-
from utils.middleware.executor import Action
from utils.middleware.timeline import TimelineStage


class AutoSelectLatest:
    def __init__(self, **params):
        self.params = params

    @staticmethod
    def _to_num(raw, default=1):
        try:
            num = int(raw)
        except (TypeError, ValueError):
            return default
        return max(1, num)

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.WAIT_EP_DECISION:
            return None
        if not getattr(ctx, "input_state", None):
            return None
        eps = getattr(ctx, "eps", None) or {}
        if not eps:
            return None
        episodes = list(eps.values())
        episodes.sort(key=lambda ep: getattr(ep, "idx", 0), reverse=True)
        num = self._to_num(self.params.get("num", 1))
        selected = episodes[:num]
        if not selected:
            return None
        ctx.input_state.indexes = selected
        return Action(
            kind="send_input_state",
            payload={"input_state": ctx.input_state},
            stop_propagation=True,
        )


AutoSelectInverse = AutoSelectLatest
