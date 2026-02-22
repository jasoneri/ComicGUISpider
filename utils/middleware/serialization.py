# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import typing as t

from utils.middleware.executor import MiddlewareDefinition
from utils.middleware.timeline import TimelineStage


SCHEMA_VERSION = 0

_PRESET_REGISTRY: dict[str, MiddlewareDefinition] = {}


def _init_preset_registry():
    if _PRESET_REGISTRY:
        return
    from utils.middleware.providers import PresetProvider
    for preset in PresetProvider().list_available():
        _PRESET_REGISTRY[preset.label] = preset


@dataclass
class WorkflowDefinition:
    workflow_name: str = "default"
    flow_type: str = "auto"
    auto_enabled: bool = False
    middlewares: list[MiddlewareDefinition] = field(default_factory=list)

    def to_dict(self) -> dict:
        _init_preset_registry()
        set_rules = []
        customs = {}
        for mw in self.middlewares:
            set_rules.append(mw.label)
            preset = _PRESET_REGISTRY.get(mw.label)
            if preset:
                diff_params = {}
                for k, v in mw.params.items():
                    if preset.params.get(k) != v:
                        diff_params[k] = v
                if mw.priority != preset.default_priority:
                    diff_params['priority'] = mw.priority
                if diff_params:
                    customs[mw.label] = diff_params
            elif mw.params:
                customs[mw.label] = dict(mw.params)
        return {
            "schema_version": SCHEMA_VERSION,
            "workflow_name": self.workflow_name,
            "flow_type": self.flow_type,
            "auto_enabled": self.auto_enabled,
            "set_rules": set_rules,
            "customs": customs,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)


@dataclass
class ExecutionState:
    session_id: str
    current_stage: int = int(TimelineStage.SESSION_INIT)
    processed_events: list[str] = field(default_factory=list)
    selected_book_id: t.Optional[str] = None
    selected_ep_ids: list[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "current_stage": self.current_stage,
            "processed_events": list(self.processed_events),
            "selected_book_id": self.selected_book_id,
            "selected_ep_ids": list(self.selected_ep_ids),
            "statistics": dict(self.statistics),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)


def workflow_from_dict(raw: dict) -> WorkflowDefinition:
    _init_preset_registry()
    set_rules = raw.get("set_rules", [])
    customs = raw.get("customs", {})

    middlewares = []
    for label in set_rules:
        preset = _PRESET_REGISTRY.get(label)
        if not preset:
            raise ValueError(f"Unknown rule label: {label}")
        mw = deepcopy(preset)
        if label in customs:
            mw.params.update(customs[label])
        middlewares.append(mw)

    return WorkflowDefinition(
        workflow_name=str(raw.get("workflow_name", "default")),
        flow_type=str(raw.get("flow_type", "auto")),
        auto_enabled=bool(raw.get("auto_enabled", False)),
        middlewares=middlewares,
    )


def workflow_from_json(text: str) -> WorkflowDefinition:
    return workflow_from_dict(json.loads(text))


def execution_state_from_dict(raw: dict) -> ExecutionState:
    return ExecutionState(
        session_id=str(raw["session_id"]),
        current_stage=int(raw.get("current_stage", int(TimelineStage.SESSION_INIT))),
        processed_events=[str(x) for x in raw.get("processed_events", [])],
        selected_book_id=raw.get("selected_book_id"),
        selected_ep_ids=[str(x) for x in raw.get("selected_ep_ids", [])],
        statistics=dict(raw.get("statistics", {})),
    )


def execution_state_from_json(text: str) -> ExecutionState:
    return execution_state_from_dict(json.loads(text))
