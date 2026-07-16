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


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def normalize_provider_fields(
    *,
    url: object = None,
    key: object = None,
    model: object = None,
) -> dict[str, str | None]:
    return {
        "url": _blank_to_none(url),
        "key": _blank_to_none(key),
        "model": _blank_to_none(model),
    }


def load_ai_provider(config: object | None = None) -> AiProvider:
    root = config if isinstance(config, dict) else (getattr(script_conf, "ai", None) or {})
    provider_payload = root.get("provider") if isinstance(root, dict) else {}
    if not isinstance(provider_payload, dict):
        provider_payload = {}
    normalized = normalize_provider_fields(
        url=provider_payload.get("url"),
        key=provider_payload.get("key"),
        model=provider_payload.get("model"),
    )
    return AiProvider(**normalized)


def is_ai_provider_configured(config: object | None = None) -> bool:
    return load_ai_provider(config).is_configured()


def provider_to_payload(provider: AiProvider) -> dict[str, t.Any]:
    return {
        "provider": {
            "url": provider.url,
            "key": provider.key,
            "model": provider.model,
        }
    }
