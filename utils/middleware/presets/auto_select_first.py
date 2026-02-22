# -*- coding: utf-8 -*-
from utils.middleware.executor import Action
from utils.middleware.timeline import TimelineStage


class AutoSelectFirst:
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
        if stage != TimelineStage.WAIT_BOOK_DECISION:
            return None
        if not getattr(ctx, "input_state", None):
            return None
        books = getattr(ctx, "books", None) or {}
        if not books:
            return None
        sorted_keys = sorted(books.keys())
        num = self._to_num(self.params.get("num", 1))
        selected = [books[k] for k in sorted_keys[:num]]
        if not selected:
            return None
        ctx.input_state.indexes = selected
        ctx.input_state.pageTurn = ""
        return Action(
            kind="send_input_state",
            payload={"input_state": ctx.input_state},
            stop_propagation=True,
        )
