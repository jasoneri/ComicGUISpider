from __future__ import annotations

from dataclasses import dataclass
import typing as t

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
