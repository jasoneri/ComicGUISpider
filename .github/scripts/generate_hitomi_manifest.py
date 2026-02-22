"""Generate hitomi-manifest.json for client-side download."""
import sys
import json
import hashlib
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone
from contextlib import closing


SOURCES = [
    {
        "id": "github",
        "priority": 10,
        "url": "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/hitomi.db"
    },
    {
        "id": "gitee",
        "priority": 20,
        "url": "https://gitee.com/json_eri/ComicGUISpider/releases/download/preset/hitomi.db"
    },
]


def generate(db_path, output_path):
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"[ERROR] {db_path} not found")
        return False

    # sha256
    h = hashlib.sha256()
    with open(db_file, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    sha256 = h.hexdigest()
    size = db_file.stat().st_size

    # stats
    table_count = 0
    row_count = 0
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'language' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        table_count = len(tables)
        for (t,) in tables:
            count = cursor.execute(f"SELECT COUNT(*) FROM `{t}`").fetchone()[0]
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
        "sources": SOURCES,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[OK] manifest written to {out}")
    print(f"  version: {manifest['version']}")
    print(f"  sha256:  {sha256[:16]}...")
    print(f"  size:    {size} bytes")
    print(f"  tables:  {table_count}, rows: {row_count}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate hitomi-manifest.json")
    parser.add_argument("db_path", help="Path to hitomi.db")
    parser.add_argument("--output", "-o", default="hitomi-manifest.json", help="Output manifest path")
    args = parser.parse_args()
    sys.exit(0 if generate(args.db_path, args.output) else 1)
