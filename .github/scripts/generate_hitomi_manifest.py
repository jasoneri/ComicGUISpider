"""Generate hitomi-manifest.json for client-side download.

Sources come from ``utils.preset_assets.managed_asset_sources`` (GitHub primary +
ImgBed ``ASSETS_FALLBACK`` when mapped in ``variables.IMGBED_ASSET_OBJECTS``).
No hard-coded gitee / dual-mirror list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _managed_hitomi_sources() -> list[dict]:
    repo_root = _repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from utils.preset_assets import managed_asset_sources

    sources: list[dict] = []
    for index, item in enumerate(managed_asset_sources("hitomi.db")):
        priority = 10 if item["id"] == "github" else 20 + index
        sources.append({"id": item["id"], "priority": priority, "url": item["url"]})
    return sources


def generate(db_path, output_path):
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"[ERROR] {db_path} not found")
        return False

    digest = hashlib.sha256()
    with open(db_file, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    size = db_file.stat().st_size

    table_count = 0
    row_count = 0
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'language' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        table_count = len(tables)
        for (table_name,) in tables:
            count = cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`").fetchone()[0]
            row_count += count

    now = datetime.now(timezone.utc)
    manifest = {
        "schema_version": 1,
        "version": now.strftime("%Y.%m.%d.%H%M"),
        "generated_at": now.isoformat(),
        "file": {
            "name": "hitomi.db",
            "size": size,
            "sha256": sha256,
            "table_count": table_count,
            "row_count": row_count,
        },
        "sources": _managed_hitomi_sources(),
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as file_handle:
        json.dump(manifest, file_handle, indent=2, ensure_ascii=False)

    print(f"[OK] manifest written to {out}")
    print(f"  version: {manifest['version']}")
    print(f"  sha256:  {sha256[:16]}...")
    print(f"  size:    {size} bytes")
    print(f"  tables:  {table_count}, rows: {row_count}")
    print(f"  sources: {[item['id'] for item in manifest['sources']]}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate hitomi-manifest.json")
    parser.add_argument("db_path", help="Path to hitomi.db")
    parser.add_argument("--output", "-o", default="hitomi-manifest.json", help="Output manifest path")
    args = parser.parse_args()
    sys.exit(0 if generate(args.db_path, args.output) else 1)
