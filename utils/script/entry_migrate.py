"""One-shot data move for the kemono -> pawchive site rename.

Not a compatibility layer: it relocates what already sits on user disks under
the old site name, then gets deleted. Both sides of the move are spelled out
here on purpose — importing the descriptor would cycle back through
``utils.website.core`` -> ``utils.config.qc``, which loads while this runs.
"""
from __future__ import annotations

import shutil

MOVES = (
    ("config_section", "kemono", "pawchive"),
    ("qconfig_file", "qc_kemono.json", "qc_pawchive.json"),
    ("redis_key", "kemono", "pawchive"),
    ("db_name", "kemono.db", "pawchive.db"),
    ("avatar_cache", "kemono_avatars.pkl", "pawchive_avatars.pkl"),
)

SCRIPT_CONF_FILE = "conf_img.yml"


def _target(kind: str, *, legacy: bool = False) -> str:
    index = 1 if legacy else 2
    return next(row[index] for row in MOVES if row[0] == kind)


def _move_file(legacy_path, current_path) -> bool:
    if not legacy_path.exists() or current_path.exists():
        return False
    current_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy_path), str(current_path))
    return True


def _move_qconfig_file() -> bool:
    from utils.config import qconfig_dir

    return _move_file(
        qconfig_dir.joinpath(_target("qconfig_file", legacy=True)),
        qconfig_dir.joinpath(_target("qconfig_file")),
    )


def _move_conf_section() -> bool:
    from utils.config import conf_dir, yaml

    legacy_section = _target("config_section", legacy=True)
    current_section = _target("config_section")
    conf_file = conf_dir.joinpath(SCRIPT_CONF_FILE)
    if not conf_file.exists():
        return False
    data = yaml.load(conf_file.read_text(encoding="utf-8"), Loader=yaml.FullLoader) or {}
    section = data.get(legacy_section)
    if section is None or current_section in data:
        return False
    del data[legacy_section]
    if isinstance(section, dict) and section.get("redis_key") == _target("redis_key", legacy=True):
        section["redis_key"] = _target("redis_key")
    data[current_section] = section
    conf_file.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return True


def _move_temp_file(kind: str) -> bool:
    from utils import temp_p

    return _move_file(
        temp_p.joinpath(_target(kind, legacy=True)),
        temp_p.joinpath(_target(kind)),
    )


async def move_redis_queue(client) -> bool:
    legacy, current = _target("redis_key", legacy=True), _target("redis_key")
    if await client.exists(legacy) and not await client.exists(current):
        await client.rename(legacy, current)
        return True
    return False


def move_entry_identity() -> list[str]:
    """Move on-disk identity to the current site name. Idempotent."""
    moved = []
    if _move_qconfig_file():
        moved.append(_target("qconfig_file"))
    if _move_conf_section():
        moved.append(_target("config_section"))
    for kind in ("db_name", "avatar_cache"):
        if _move_temp_file(kind):
            moved.append(_target(kind))
    return moved
