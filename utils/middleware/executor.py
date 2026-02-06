# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
import typing as t

from utils.middleware.timeline import TimelineStage


@dataclass
class Action:
    kind: str
    payload: dict = field(default_factory=dict)
    stop_propagation: bool = False


@dataclass
class MiddlewareDefinition:
    id: str
    type: str
    name: str
    priority: int
    supported_stages: list[int]
    params: dict = field(default_factory=dict)
    enabled: bool = True

    def supports(self, stage: TimelineStage) -> bool:
        return int(stage) in self.supported_stages


class MiddlewareChain:
    def __init__(self, entries: list[tuple[MiddlewareDefinition, t.Any]]):
        self.entries = sorted(entries, key=lambda x: x[0].priority)

    def run(self, stage: TimelineStage, ctx) -> list[Action]:
        actions: list[Action] = []
        for definition, middleware in self.entries:
            if not definition.enabled:
                continue
            if not definition.supports(stage):
                continue
            action = middleware.on_event(stage, ctx)
            if action is None:
                continue
            actions.append(action)
            if action.stop_propagation:
                break
        return actions
