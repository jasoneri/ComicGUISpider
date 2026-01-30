# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass, field
import typing as t

from utils.middleware.timeline import TimelineStage


@dataclass
class Action:
    kind: str
    payload: dict = field(default_factory=dict)
    stop_propagation: bool = False


_LABEL_PATTERN = re.compile(r"^[A-Z]\d+$")


@dataclass
class MiddlewareDefinition:
    id: str
    type: str
    name: str
    default_priority: int
    supported_stages: list[int]
    params: dict = field(default_factory=dict)
    param_schema: dict = field(default_factory=dict)
    enabled: bool = True
    label: str = ""
    desc: str = ""
    allowed_lanes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.label and not _LABEL_PATTERN.match(self.label):
            raise ValueError(f"Invalid label format: {self.label!r}. Expected format like 'A1', 'B2', etc.")
        if not self.allowed_lanes:
            raise ValueError("allowed_lanes must not be empty")

    @property
    def priority(self) -> int:
        return self.params.get('priority', self.default_priority)

    @priority.setter
    def priority(self, value: int):
        self.params['priority'] = value

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
