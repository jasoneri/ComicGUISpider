# -*- coding: utf-8 -*-
"""Subscription binding persistence.

Architecture:

- ``BindingRepository`` — pure YAML file gateway (paths + raw dict I/O only).
- ``SchemaCodec`` — single decode/encode owner for the **current flat** document.
  No permanent dual-shape→flat migrate: 2.11.x subscribe was trial-level; trial
  dual-shape files are disposable (fail loud / recreate). Future *mass-shipped*
  schema bumps may add ordered ``RawTransform`` steps here only when provenance
  + field adoption justify the debt.
- ``SubscriptionStore`` — document session / aggregate handle for one binding
  profile (load → edit ``SubscriptionConfig`` → validate → save).
- ``BindingProfileCatalog`` — profile name list + active profile (qconfig).
- ``CatchupPresetSetting`` — tray-global catch-up preset (qconfig).

Public names ``SubscriptionStore`` / ``DEFAULT_CUSTOMNAME`` / list-active helpers
stay stable; module-level helpers only forward to the owners above.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from utils.config import conf_dir
from utils.subscription.schema import SubscriptionConfig, VALID_CATCHUP_PRESETS

DEFAULT_CUSTOMNAME = "default"
SUBSCRIPTION_DIR = conf_dir.joinpath("subscription")
SUBSCRIPTION_DIR.mkdir(parents=True, exist_ok=True)

_CUSTOMNAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_YAML_NAME_RE = re.compile(r"^subscription_(?P<name>[A-Za-z0-9_-]+)\.yml$")


def require_customname(value: str) -> str:
    name = str(value or "").strip() or DEFAULT_CUSTOMNAME
    if name in {".", ".."} or not _CUSTOMNAME_RE.fullmatch(name):
        raise ValueError(f"invalid subscription customname: {value!r}")
    return name


class RawTransform(Protocol):
    """Optional pre-decode rewrite (only for future mass-shipped schema bumps)."""

    def apply(self, raw: dict[str, Any]) -> dict[str, Any]:
        ...


class SchemaCodec:
    """Typed codec for the current flat binding document only."""

    def __init__(self, transforms: list[RawTransform] | None = None) -> None:
        self._transforms = list(transforms or [])

    def decode(self, raw: Any) -> SubscriptionConfig:
        if not isinstance(raw, dict):
            raise ValueError(f"subscription yaml root must be a mapping, got {type(raw).__name__}")
        document = dict(raw)
        for transform in self._transforms:
            document = transform.apply(document)
            if not isinstance(document, dict):
                raise ValueError("schema transform must return a mapping")
        return SubscriptionConfig.from_mapping(document)

    def encode(self, config: SubscriptionConfig) -> dict[str, Any]:
        config.validate()
        return config.to_mapping()


class BindingRepository:
    """File gateway for ``subscription_{name}.yml`` — no domain rules."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else SUBSCRIPTION_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, customname: str) -> Path:
        name = require_customname(customname)
        return self.directory / f"subscription_{name}.yml"

    def exists(self, customname: str) -> bool:
        return self.path_for(customname).exists()

    def list_names(self, *, include_default: bool = True) -> list[str]:
        names: list[str] = []
        if self.directory.is_dir():
            for path in sorted(self.directory.glob("subscription_*.yml")):
                match = _YAML_NAME_RE.fullmatch(path.name)
                if match is None:
                    continue
                name = match.group("name")
                if name not in names:
                    names.append(name)
        if include_default and DEFAULT_CUSTOMNAME not in names:
            names.insert(0, DEFAULT_CUSTOMNAME)
        return names

    def read_mapping(self, customname: str) -> dict[str, Any] | None:
        path = self.path_for(customname)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle.read())
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError(
                f"subscription yaml root must be a mapping, got {type(raw).__name__}"
            )
        return raw

    def write_mapping(self, customname: str, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("subscription payload must be a mapping")
        path = self.path_for(customname)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


class SubscriptionStore:
    """Document session for one whole-library binding profile.

    Owns: customname identity, loaded ``SubscriptionConfig`` lifecycle.
    Does not own: profile catalog, catch-up preset, schema migration strategies.
    """

    def __init__(
        self,
        customname: str = DEFAULT_CUSTOMNAME,
        *,
        repository: BindingRepository | None = None,
        codec: SchemaCodec | None = None,
    ) -> None:
        self.customname = require_customname(customname)
        self._repository = repository or BindingRepository()
        self._codec = codec or SchemaCodec()
        self._config: SubscriptionConfig | None = None

    @property
    def path(self) -> Path:
        return self._repository.path_for(self.customname)

    @property
    def config(self) -> SubscriptionConfig:
        if self._config is None:
            return self.load()
        return self._config

    def rebind(self, customname: str) -> SubscriptionStore:
        return SubscriptionStore(
            customname,
            repository=self._repository,
            codec=self._codec,
        )

    def load(self) -> SubscriptionConfig:
        raw = self._repository.read_mapping(self.customname)
        if raw is None:
            config = SubscriptionConfig(customname=self.customname)
            config.validate()
            self._config = config
            self._persist(config)
            return config
        config = self._codec.decode(raw)
        config.customname = self.customname
        config.validate()
        self._config = config
        return config

    def save(self, config: SubscriptionConfig | None = None) -> None:
        document = config if config is not None else self._config
        if document is None:
            raise RuntimeError("SubscriptionStore.save requires a loaded or provided config")
        document.customname = self.customname
        document.validate()
        self._persist(document)
        self._config = document

    def replace(self, config: SubscriptionConfig) -> SubscriptionConfig:
        """In-memory replace without I/O (session edit)."""
        config.customname = self.customname
        config.validate()
        self._config = config
        return config

    def _persist(self, config: SubscriptionConfig) -> None:
        self._repository.write_mapping(self.customname, self._codec.encode(config))


class BindingProfileCatalog:
    """Profile names under the binding directory + active profile pointer."""

    def __init__(
        self,
        repository: BindingRepository | None = None,
        *,
        active_reader: Callable[[], str] | None = None,
        active_writer: Callable[[str], None] | None = None,
    ) -> None:
        self._repository = repository or BindingRepository()
        self._active_reader = active_reader or self._read_active_from_qconfig
        self._active_writer = active_writer or self._write_active_to_qconfig

    def list_names(self, *, include_default: bool = True) -> list[str]:
        return self._repository.list_names(include_default=include_default)

    def active_name(self) -> str:
        return require_customname(self._active_reader())

    def set_active_name(self, customname: str) -> str:
        name = require_customname(customname)
        self._active_writer(name)
        return name

    def open_active(self, *, codec: SchemaCodec | None = None) -> SubscriptionStore:
        return SubscriptionStore(
            self.active_name(),
            repository=self._repository,
            codec=codec,
        )

    def open(self, customname: str, *, codec: SchemaCodec | None = None) -> SubscriptionStore:
        return SubscriptionStore(
            customname,
            repository=self._repository,
            codec=codec,
        )

    @staticmethod
    def _read_active_from_qconfig() -> str:
        try:
            from utils.config.qc import cgs_cfg

            return str(getattr(cgs_cfg.activeSubscriptionCustomname, "value", None) or "")
        except Exception:
            return DEFAULT_CUSTOMNAME

    @staticmethod
    def _write_active_to_qconfig(name: str) -> None:
        from utils.config.qc import cgs_cfg

        if cgs_cfg.activeSubscriptionCustomname.value != name:
            cgs_cfg.activeSubscriptionCustomname.value = name
            cgs_cfg.save()


class CatchupPresetSetting:
    """Tray-global 后巡查 preset — not part of per-profile binding yaml."""

    def __init__(
        self,
        *,
        reader: Callable[[], str] | None = None,
        writer: Callable[[str], None] | None = None,
    ) -> None:
        self._reader = reader or self._read_from_qconfig
        self._writer = writer or self._write_to_qconfig

    def get(self) -> str:
        raw = str(self._reader() or "off").strip() or "off"
        if raw not in VALID_CATCHUP_PRESETS:
            return "off"
        return raw

    def set(self, preset: str) -> str:
        name = str(preset or "off").strip() or "off"
        if name not in VALID_CATCHUP_PRESETS:
            raise ValueError(f"invalid catchup preset: {preset!r}")
        self._writer(name)
        return name

    @staticmethod
    def _read_from_qconfig() -> str:
        try:
            from utils.config.qc import cgs_cfg

            return str(getattr(cgs_cfg.subscriptionCatchupPreset, "value", None) or "off")
        except Exception:
            return "off"

    @staticmethod
    def _write_to_qconfig(name: str) -> None:
        from utils.config.qc import cgs_cfg

        if cgs_cfg.subscriptionCatchupPreset.value != name:
            cgs_cfg.subscriptionCatchupPreset.value = name
            cgs_cfg.save()


# --- stable module surface (forward to owners; no business logic here) ---

_default_catalog = BindingProfileCatalog()
_default_catchup = CatchupPresetSetting()


def list_subscription_customnames(*, include_default: bool = True) -> list[str]:
    return _default_catalog.list_names(include_default=include_default)


def get_active_subscription_customname() -> str:
    return _default_catalog.active_name()


def set_active_subscription_customname(customname: str) -> str:
    return _default_catalog.set_active_name(customname)


def open_active_subscription_store() -> SubscriptionStore:
    return _default_catalog.open_active()


def get_subscription_catchup_preset() -> str:
    return _default_catchup.get()


def set_subscription_catchup_preset(preset: str) -> str:
    return _default_catchup.set(preset)
