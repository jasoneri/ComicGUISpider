# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod
import hashlib
import typing as t

from utils.middleware.executor import MiddlewareDefinition
from utils.middleware.timeline import TimelineStage


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
        return [
            MiddlewareDefinition(
                id="preset:auto_select_first",
                type="auto_select_first",
                name="Auto Select First Book",
                priority=100,
                supported_stages=[int(TimelineStage.WAIT_BOOK_DECISION)],
                params={},
                enabled=True,
            ),
            MiddlewareDefinition(
                id="preset:auto_select_latest",
                type="auto_select_latest",
                name="Auto Select Latest Episode",
                priority=100,
                supported_stages=[int(TimelineStage.WAIT_EP_DECISION)],
                params={},
                enabled=True,
            ),
            MiddlewareDefinition(
                id="preset:cbz_post_processor",
                type="cbz_post_processor",
                name="CBZ Post Processor",
                priority=600,
                supported_stages=[int(TimelineStage.POSTPROCESSING)],
                params={},
                enabled=True,
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
