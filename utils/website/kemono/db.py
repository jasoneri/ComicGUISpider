from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KemonoAuthor:
    id: str
    name: str
    service: str
    updated: int
    favorited: int

    @property
    def avatar(self) -> str:
        return f"https://img.kemono.cr/icons/{self.service}/{self.id}"

    def to_payload(self) -> dict[str, str | int]:
        return asdict(self)


def _normalize_author(item: dict) -> KemonoAuthor:
    if not isinstance(item, dict):
        raise TypeError(f"invalid kemono creator row: {item!r}")
    return KemonoAuthor(
        id=str(item["id"]),
        name=str(item["name"]),
        service=str(item["service"]),
        updated=int(item["updated"]),
        favorited=int(item["favorited"]),
    )


class KemonoAuthorsDb:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS authors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    service TEXT NOT NULL,
                    updated INTEGER NOT NULL,
                    favorited INTEGER NOT NULL
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_authors_service ON authors(service)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_authors_favorited ON authors(favorited DESC)")
            conn.commit()

    def replace_from_creators(self, creators: list[dict]) -> int:
        self.ensure_schema()
        authors = [_normalize_author(item) for item in creators]
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO authors (id, name, service, updated, favorited)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    service=excluded.service,
                    updated=excluded.updated,
                    favorited=excluded.favorited
                """,
                [(author.id, author.name, author.service, author.updated, author.favorited) for author in authors],
            )
            conn.commit()
        return len(authors)

    def load_all(self) -> dict[str, KemonoAuthor]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"kemono db not found: {self.db_path}")
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, service, updated, favorited FROM authors")
            rows = cursor.fetchall()
        return {
            str(row_id): KemonoAuthor(
                id=str(row_id),
                name=str(name),
                service=str(service),
                updated=int(updated),
                favorited=int(favorited),
            )
            for row_id, name, service, updated, favorited in rows
        }


def build_kemono_db_from_creators_bytes(db_path: Path, payload: bytes) -> int:
    data = json.loads(payload.decode("utf-8"))
    return KemonoAuthorsDb(db_path).replace_from_creators(data)


def load_kemono_authors(db_path: Path) -> dict[str, KemonoAuthor]:
    return KemonoAuthorsDb(db_path).load_all()
