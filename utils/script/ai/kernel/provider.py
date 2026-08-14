from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import typing as t

from PySide6.QtCore import QObject, Signal

from utils.script import conf as script_conf


@dataclass(frozen=True, slots=True)
class AiProvider:
    url: str | None
    key: str | None
    model: str | None

    def is_configured(self) -> bool:
        return self.url is not None and self.key is not None and self.model is not None


class AiProviderMgr:
    """Owns AI provider config state loaded from script conf / mapping."""

    def __init__(self, config: object | None = None):
        self.provider = self._parse(config)

    @staticmethod
    def _blank_to_none(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @classmethod
    def normalize_fields(
        cls,
        *,
        url: object = None,
        key: object = None,
        model: object = None,
    ) -> dict[str, str | None]:
        return {
            "url": cls._blank_to_none(url),
            "key": cls._blank_to_none(key),
            "model": cls._blank_to_none(model),
        }

    @classmethod
    def _parse(cls, config: object | None = None) -> AiProvider:
        root = config if isinstance(config, dict) else (getattr(script_conf, "ai", None) or {})
        provider_payload = root.get("provider") if isinstance(root, dict) else {}
        if not isinstance(provider_payload, dict):
            provider_payload = {}
        normalized = cls.normalize_fields(
            url=provider_payload.get("url"),
            key=provider_payload.get("key"),
            model=provider_payload.get("model"),
        )
        return AiProvider(**normalized)

    def reload(self, config: object | None = None) -> AiProvider:
        self.provider = self._parse(config)
        return self.provider

    def is_configured(self) -> bool:
        return self.provider.is_configured()

    def to_payload(self) -> dict[str, t.Any]:
        return {
            "provider": {
                "url": self.provider.url,
                "key": self.provider.key,
                "model": self.provider.model,
            }
        }


class AiProviderConfigState(StrEnum):
    """LLM provider presence only — configuration presence = capability."""

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"


class AiProviderConfigSession(QObject):
    """Process-wide LLM provider config state machine.

    Transitions (settings save is the only writer):
      NOT_CONFIGURED → CONFIGURED : url + key + model all non-empty
      CONFIGURED → NOT_CONFIGURED : any required field cleared

    UI features that share this gate (fav-tags-translate chrome, TagExport
    ``comfy_nl_row``) subscribe to ``state_changed`` and show/hide accordingly.
    No enable switches — presence alone is the capability bit.
    """

    state_changed = Signal(object, object)

    _instance: t.ClassVar[AiProviderConfigSession | None] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mgr = AiProviderMgr()
        self._state = self._state_from_provider(self._mgr.provider)

    @classmethod
    def instance(cls) -> AiProviderConfigSession:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def state(self) -> AiProviderConfigState:
        return self._state

    @property
    def provider(self) -> AiProvider:
        return self._mgr.provider

    def is_configured(self) -> bool:
        return self._state is AiProviderConfigState.CONFIGURED

    def reload(self, config: object | None = None) -> AiProviderConfigState:
        """Re-read provider fields and transition if presence flipped."""
        self._mgr.reload(config)
        return self._transition_to(self._state_from_provider(self._mgr.provider))

    def _transition_to(self, new_state: AiProviderConfigState) -> AiProviderConfigState:
        if new_state is self._state:
            return self._state
        previous_state = self._state
        self._state = new_state
        self.state_changed.emit(previous_state, new_state)
        return self._state

    @staticmethod
    def _state_from_provider(provider: AiProvider) -> AiProviderConfigState:
        if provider.is_configured():
            return AiProviderConfigState.CONFIGURED
        return AiProviderConfigState.NOT_CONFIGURED
