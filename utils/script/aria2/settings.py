from __future__ import annotations

from typing import Any

import yaml

from utils.script import conf as script_conf
from utils.script.aria2.conf import normalize_proxy
from utils.script.aria2.import_motrix import import_motrix_proxy_once


def load_script_yaml() -> dict[str, Any]:
    if not script_conf.file.exists():
        return {}
    with open(script_conf.file, "r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle.read()) or {}


def get_cgs_aria2_section(config_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = config_data if config_data is not None else load_script_yaml()
    section = data.get("cgs_aria2")
    return dict(section) if isinstance(section, dict) else {}


def _section_proxy_value(section: dict[str, Any]) -> str:
    # Prefer cgs_aria2.proxy; accept legacy all_proxy once if present.
    if "proxy" in section:
        return normalize_proxy(section.get("proxy"))
    return normalize_proxy(section.get("all_proxy", ""))


def get_proxy(config_data: dict[str, Any] | None = None) -> str:
    return _section_proxy_value(get_cgs_aria2_section(config_data))


def ensure_motrix_proxy_seed(config_data: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool]:
    data = dict(config_data) if config_data is not None else load_script_yaml()
    section = get_cgs_aria2_section(data)
    if section.get("migrated_from_motrix"):
        return data, False
    if _section_proxy_value(section):
        section["proxy"] = _section_proxy_value(section)
        section.pop("all_proxy", None)
        section["migrated_from_motrix"] = True
        data["cgs_aria2"] = section
        script_conf.update(**data)
        return data, False

    imported_proxy = import_motrix_proxy_once()
    section["proxy"] = imported_proxy
    section.pop("all_proxy", None)
    section["migrated_from_motrix"] = True
    data["cgs_aria2"] = section
    script_conf.update(**data)
    return data, bool(imported_proxy)


def set_proxy(proxy: object, *, config_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(config_data) if config_data is not None else load_script_yaml()
    section = get_cgs_aria2_section(data)
    section["proxy"] = normalize_proxy(proxy)
    section.pop("all_proxy", None)
    if "migrated_from_motrix" not in section:
        section["migrated_from_motrix"] = False
    data["cgs_aria2"] = section
    return data


# Temporary aliases while call sites finish renaming.
get_all_proxy = get_proxy
set_all_proxy = set_proxy
