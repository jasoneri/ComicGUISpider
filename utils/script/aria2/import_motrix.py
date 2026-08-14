from __future__ import annotations

import json
import os
import pathlib as p
from typing import Iterable

from loguru import logger

from utils.script.aria2.conf import normalize_proxy


def motrix_system_json_candidates() -> list[p.Path]:
    candidates: list[p.Path] = []
    appdata = os.environ.get("APPDATA") or ""
    if appdata:
        candidates.append(p.Path(appdata) / "Motrix" / "system.json")
    home = p.Path.home()
    candidates.append(home / "Library" / "Application Support" / "Motrix" / "system.json")
    candidates.append(home / ".config" / "Motrix" / "system.json")
    return candidates


def read_motrix_proxy(paths: Iterable[p.Path] | None = None) -> str:
    """Read Motrix UI proxy from system.json (Motrix stores key as all-proxy)."""
    for path in paths or motrix_system_json_candidates():
        try:
            if not path.exists() or not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            logger.debug(f"[CgsAria2] skip motrix system.json path={path} err={exc}")
            continue
        if not isinstance(payload, dict):
            continue
        # Motrix electron-store key is "all-proxy"; map into CGS field "proxy".
        proxy = normalize_proxy(payload.get("all-proxy") or payload.get("all_proxy") or "")
        if proxy:
            logger.info(f"[CgsAria2] imported Motrix proxy from {path}")
            return proxy
        logger.info(f"[CgsAria2] Motrix system.json found without proxy path={path}")
        return ""
    return ""


def import_motrix_proxy_once() -> str:
    return read_motrix_proxy()


# Legacy aliases
read_motrix_all_proxy = read_motrix_proxy
import_motrix_all_proxy_once = import_motrix_proxy_once
