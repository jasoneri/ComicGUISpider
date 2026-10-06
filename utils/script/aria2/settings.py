from __future__ import annotations

from typing import Any

import yaml

from utils.script import conf as script_conf
from utils.script.aria2.conf import normalize_proxy
from utils.script.aria2.lock import DEFAULT_RPC_PORT


def load_script_yaml() -> dict[str, Any]:
    if not script_conf.file.exists():
        return {}
    with open(script_conf.file, "r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle.read()) or {}


def get_cgs_aria2_section(config_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = config_data if config_data is not None else load_script_yaml()
    section = data.get("cgs_aria2")
    return dict(section) if isinstance(section, dict) else {}


def get_proxy(config_data: dict[str, Any] | None = None) -> str:
    return normalize_proxy(get_cgs_aria2_section(config_data).get("proxy"))


def get_rpc_port(config_data: dict[str, Any] | None = None) -> int:
    """Fixed RPC port; a bad configured value is a config error, not a fallback."""
    raw = get_cgs_aria2_section(config_data).get("rpc_port")
    if raw in (None, ""):
        return DEFAULT_RPC_PORT
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cgs_aria2.rpc_port must be an integer, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"cgs_aria2.rpc_port out of range: {port}")
    return port


def singleton_enabled(config_data: dict[str, Any] | None = None) -> bool:
    return bool(get_cgs_aria2_section(config_data).get("singleton_enabled", True))


def set_proxy(proxy: object, *, config_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(config_data) if config_data is not None else load_script_yaml()
    section = get_cgs_aria2_section(data)
    section["proxy"] = normalize_proxy(proxy)
    data["cgs_aria2"] = section
    return data
