# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod
import hashlib
import typing as t

from utils.middleware.executor import MiddlewareDefinition
from utils.middleware.timeline import TimelineStage, LaneStage


class MiddlewareProvider(ABC):
    provider_id: str
    icon: str
    category: str

    @abstractmethod
    def list_available(self) -> list[MiddlewareDefinition]:
        raise NotImplementedError


class PresetProvider(MiddlewareProvider):
    provider_id = "preset"
    icon = "\U0001F6E1\ufe0f"
    category = "Built-in"

    def list_available(self) -> list[MiddlewareDefinition]:
        def _preset(*, lane: LaneStage, stage: TimelineStage, **kwargs) -> MiddlewareDefinition:
            kwargs.setdefault("enabled", True)
            kwargs.setdefault("params", {})
            return MiddlewareDefinition(
                supported_stages=[int(stage)],
                allowed_lanes=[lane.value],
                **kwargs,
            )

        return [
            _preset(
                id="preset:auto_select_first",
                type="auto_select_first",
                name="Select First Book",
                default_priority=211,
                label="C1",
                lane=LaneStage.BOOK,
                stage=TimelineStage.WAIT_BOOK_DECISION,
            ),
            _preset(
                id="preset:auto_select_first_test",
                type="auto_select_first",
                name="Select First Book2",
                default_priority=212,
                label="C2",
                lane=LaneStage.BOOK,
                stage=TimelineStage.WAIT_BOOK_DECISION,
            ),
            _preset(
                id="preset:auto_select_latest",
                type="auto_select_latest",
                name="Select Latest n Episode",
                default_priority=311,
                label="D1",
                desc="选择最新n个章节",
                params={'num': 1},
                param_schema={'num': {'type': 'int', 'min': 1, 'max': 99, 'default': 1}},
                lane=LaneStage.EP,
                stage=TimelineStage.WAIT_EP_DECISION,
            ),
            _preset(
                id="preset:cbz_post_processor",
                type="cbz_post_processor",
                name="To CBZ",
                default_priority=601,
                label="E1",
                lane=LaneStage.POSTPROCESSING,
                stage=TimelineStage.POSTPROCESSING,
            ),
        ]


class UserProvider(MiddlewareProvider):
    provider_id = "user"
    icon = "\U0001F464"
    category = "My Rules"

    def __init__(self, definitions: t.Optional[list[MiddlewareDefinition]] = None):
        self._definitions = definitions or []

    def list_available(self) -> list[MiddlewareDefinition]:
        return list(self._definitions)


@dataclass(frozen=True)
class RemoteRulePackage:
    source: str
    name: str
    version: str
    sha256: str
    signature: str
    public_key_pem: str


class RemoteProvider(MiddlewareProvider):
    provider_id = "remote"
    icon = "\u2601\ufe0f"
    category = "Community Rules"

    def __init__(self, packages: t.Optional[list[RemoteRulePackage]] = None):
        self.packages = packages or []
        self._definitions: list[MiddlewareDefinition] = []

    def verify_sha256(self, payload: bytes, expected_hex: str) -> bool:
        return hashlib.sha256(payload).hexdigest() == expected_hex

    def verify_signature(self, payload: bytes, signature: str, public_key_pem: str) -> bool:
        raise NotImplementedError("Signature verification must be implemented with a vetted crypto backend")

    def sandbox_supported(self) -> bool:
        return True

    def list_available(self) -> list[MiddlewareDefinition]:
        return list(self._definitions)
