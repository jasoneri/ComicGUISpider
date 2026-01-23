# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
import json
import typing as t

from utils.middleware.executor import MiddlewareDefinition
from utils.middleware.timeline import TimelineStage


SCHEMA_VERSION = 1


@dataclass
class WorkflowDefinition:
    schema_version: int = SCHEMA_VERSION
    workflow_name: str = "default"
    flow_type: str = "auto"
    middlewares: list[MiddlewareDefinition] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "workflow_name": self.workflow_name,
            "flow_type": self.flow_type,
            "middlewares": [middleware_to_dict(mw) for mw in self.middlewares],
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


def migrate_workflow_dict(raw: dict) -> dict:
    ver = int(raw.get("schema_version", 0) or 0)
    if ver == SCHEMA_VERSION:
        return raw
    if ver == 0:
        raw["schema_version"] = SCHEMA_VERSION
        if "middlewares" not in raw and "lanes" in raw:
            raw["middlewares"] = []
        return raw
    raise ValueError(f"unsupported schema_version: {ver}")


def middleware_to_dict(mw: MiddlewareDefinition) -> dict:
    return {
        "id": mw.id,
        "type": mw.type,
        "name": mw.name,
        "priority": mw.priority,
        "supported_stages": list(mw.supported_stages),
        "params": dict(mw.params or {}),
        "enabled": bool(mw.enabled),
    }


def middleware_from_dict(raw: dict) -> MiddlewareDefinition:
    mw_type = raw.get("type", "")
    mw_name = raw.get("name") or mw_type
    supported = raw.get("supported_stages") or []
    params = raw.get("params") or {}
    enabled = bool(raw.get("enabled", True))

    if not mw_type:
        mw_type = "__unknown__"
        enabled = False
        params = dict(params)
        params["_raw"] = dict(raw)

    return MiddlewareDefinition(
        id=str(raw.get("id") or f"mw:{mw_type}"),
        type=str(mw_type),
        name=str(mw_name),
        priority=int(raw.get("priority", 100)),
        supported_stages=[int(x) for x in supported],
        params=dict(params),
        enabled=enabled,
    )


def workflow_from_dict(raw: dict) -> WorkflowDefinition:
    raw = migrate_workflow_dict(dict(raw))
    middlewares = [middleware_from_dict(mw) for mw in raw.get("middlewares", [])]
    return WorkflowDefinition(
        schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
        workflow_name=str(raw.get("workflow_name", "default")),
        flow_type=str(raw.get("flow_type", "auto")),
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
