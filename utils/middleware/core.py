# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
import typing as t

from utils.middleware.executor import Action, MiddlewareChain, MiddlewareDefinition
from utils.middleware.timeline import Event, TimelineStage
from utils.middleware.providers import PresetProvider
from utils.middleware.presets import register_presets


@dataclass
class ExecutionContext:
    session_id: str
    current_stage: TimelineStage = TimelineStage.SESSION_INIT
    flow_type: t.Any = None
    input_state: t.Any = None
    process_state: t.Any = None

    books: dict = field(default_factory=dict)
    eps: dict = field(default_factory=dict)

    processed_events: set[str] = field(default_factory=set)
    selected_book_id: t.Optional[str] = None
    selected_ep_ids: list[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)


class CGSMid:
    def __init__(
        self,
        ctx: ExecutionContext,
        chain: MiddlewareChain,
        action_sink: t.Optional[t.Callable[[Action], None]] = None,
    ):
        self.ctx = ctx
        self.chain = chain
        self.action_sink = action_sink

    def handle_event(self, stage: TimelineStage, evt: t.Optional[Event] = None) -> list[Action]:
        self.ctx.current_stage = stage
        actions = self.chain.run(stage, self.ctx)
        if self.action_sink:
            for action in actions:
                self.action_sink(action)
        return actions


class CGSMidManager:
    _instance = None

    def __init__(self):
        self._registry: dict[str, t.Any] = {}
        self.providers = [PresetProvider()]
        register_presets(self)

    @classmethod
    def get_instance(cls) -> "CGSMidManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_middleware(self, mw_type: str, mw_cls):
        self._registry[mw_type] = mw_cls

    def is_known_type(self, mw_type: str) -> bool:
        return mw_type in self._registry

    def compile_workflow(self, workflow) -> list[MiddlewareDefinition]:
        if workflow is None:
            return []
        if hasattr(workflow, "middlewares"):
            return list(workflow.middlewares)
        return []

    def build_chain(self, definitions: list[MiddlewareDefinition]) -> MiddlewareChain:
        entries: list[tuple[MiddlewareDefinition, t.Any]] = []
        for definition in definitions:
            mw_cls = self._registry.get(definition.type)
            if mw_cls is None:
                mw = _UnknownMiddleware(definition.type, definition.params)
                entries.append((definition, mw))
                continue
            mw = mw_cls(**(definition.params or {}))
            entries.append((definition, mw))
        return MiddlewareChain(entries)

    def create_session(
        self,
        ctx: ExecutionContext,
        workflow=None,
        action_sink: t.Optional[t.Callable[[Action], None]] = None,
    ) -> CGSMid:
        definitions = self.compile_workflow(workflow)
        chain = self.build_chain(definitions)
        return CGSMid(ctx=ctx, chain=chain, action_sink=action_sink)


class _UnknownMiddleware:
    def __init__(self, mw_type: str, params: dict):
        self.mw_type = mw_type
        self.params = params

    def on_event(self, stage: TimelineStage, ctx):
        return None
