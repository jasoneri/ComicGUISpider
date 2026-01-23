# -*- coding: utf-8 -*-
from utils.middleware.executor import Action
from utils.middleware.timeline import TimelineStage


class AutoSelectFirst:
    def __init__(self, **params):
        self.params = params

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.WAIT_BOOK_DECISION:
            return None
        if not getattr(ctx, "input_state", None):
            return None
        books = getattr(ctx, "books", None) or {}
        if not books:
            return None
        first_idx = sorted(books.keys())[0]
        book = books[first_idx]
        ctx.input_state.indexes = [book]
        ctx.input_state.pageTurn = ""
        return Action(
            kind="send_input_state",
            payload={"input_state": ctx.input_state},
            stop_propagation=True,
        )
