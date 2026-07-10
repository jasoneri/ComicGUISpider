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

    @staticmethod
    def _episode_idx(ep):
        try:
            return int(getattr(ep, "idx", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def select_episodes(cls, episodes, num=1):
        selected = list(episodes)
        selected.sort(key=cls._episode_idx, reverse=True)
        return selected[:cls._to_num(num)]

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.WAIT_EP_DECISION:
            return None
        if not getattr(ctx, "input_state", None):
            return None
        eps = getattr(ctx, "eps", None) or {}
        if not eps:
            return None
        episodes = list(eps.values())
        selected = self.select_episodes(episodes, self.params.get("num", 1))
        if not selected:
            return None
        ctx.input_state.indexes = selected
        return Action(
            kind="send_input_state",
            payload={"input_state": ctx.input_state},
            stop_propagation=True,
        )


AutoSelectInverse = AutoSelectLatest
