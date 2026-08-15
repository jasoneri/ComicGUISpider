from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path


_SORT_COLUMNS = frozenset({"name", "service", "updated", "favorited"})
_FTS_SPECIAL_RE = re.compile(r'["\'\*\^\~\(\)\:\{\}\[\]\\]')


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


@dataclass(frozen=True, slots=True)
class AuthorQuery:
    text: str = ""
    favorite_ids: tuple[str, ...] | None = None
    sort_column: str = "favorited"
    sort_desc: bool = True


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


def _author_from_row(row: tuple) -> KemonoAuthor:
    row_id, name, service, updated, favorited = row
    return KemonoAuthor(
        id=str(row_id),
        name=str(name),
        service=str(service),
        updated=int(updated),
        favorited=int(favorited),
    )


def _sanitize_fts_query(raw_text: str) -> str:
    cleaned = _FTS_SPECIAL_RE.sub(" ", raw_text.strip())
    tokens = [token for token in cleaned.split() if token]
    if not tokens:
        return ""
    return " ".join(f'"{token}"' for token in tokens)


class KemonoAuthorsDb:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._fts_ready_cached: bool | None = None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
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
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_authors_service ON authors(service)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_authors_favorited ON authors(favorited DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_authors_updated ON authors(updated DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kemono_db_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _fts_table_exists(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authors_fts'"
        ).fetchone()
        return row is not None

    def fts_ready(self) -> bool:
        if self._fts_ready_cached is not None:
            return self._fts_ready_cached
        if not self.db_path.exists():
            self._fts_ready_cached = False
            return False
        with closing(self._connect()) as conn:
            if not self._fts_table_exists(conn):
                self._fts_ready_cached = False
                return False
            meta_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='kemono_db_meta'"
            ).fetchone()
            if meta_exists is None:
                self._fts_ready_cached = False
                return False
            meta = conn.execute(
                "SELECT value FROM kemono_db_meta WHERE key='fts_built'"
            ).fetchone()
            if meta is None or meta[0] != "1":
                self._fts_ready_cached = False
                return False
            authors_count = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
            fts_count = conn.execute("SELECT COUNT(*) FROM authors_fts").fetchone()[0]
            ready = int(authors_count) == int(fts_count)
            self._fts_ready_cached = ready
            return ready

    def ensure_fts(self, *, force: bool = False) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"kemono db not found: {self.db_path}")
        self.ensure_schema()
        if not force and self.fts_ready():
            return
        with closing(self._connect()) as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS authors_fts")
            cursor.execute(
                """
                CREATE VIRTUAL TABLE authors_fts USING fts5(
                    name,
                    content='authors',
                    content_rowid='rowid'
                )
                """
            )
            cursor.execute(
                "INSERT INTO authors_fts(rowid, name) SELECT rowid, name FROM authors"
            )
            cursor.execute(
                """
                INSERT INTO kemono_db_meta(key, value) VALUES('fts_built', '1')
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """
            )
            conn.commit()
        self._fts_ready_cached = True

    def replace_from_creators(self, creators: list[dict]) -> int:
        self.ensure_schema()
        self._fts_ready_cached = None
        authors = [_normalize_author(item) for item in creators]
        with closing(self._connect()) as conn:
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
                [
                    (author.id, author.name, author.service, author.updated, author.favorited)
                    for author in authors
                ],
            )
            conn.commit()
        self.ensure_fts(force=True)
        return len(authors)

    def load_all(self) -> dict[str, KemonoAuthor]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"kemono db not found: {self.db_path}")
        with closing(self._connect()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, service, updated, favorited FROM authors")
            rows = cursor.fetchall()
        return {str(row[0]): _author_from_row(row) for row in rows}

    def _resolve_sort(self, query: AuthorQuery) -> tuple[str, str]:
        sort_column = query.sort_column if query.sort_column in _SORT_COLUMNS else "favorited"
        sort_direction = "DESC" if query.sort_desc else "ASC"
        return sort_column, sort_direction

    def _build_where(self, query: AuthorQuery) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []

        if query.favorite_ids is not None:
            if not query.favorite_ids:
                return "1=0", []
            placeholders = ",".join("?" for _ in query.favorite_ids)
            clauses.append(f"authors.id IN ({placeholders})")
            params.extend(query.favorite_ids)

        text = (query.text or "").strip()
        if text and query.favorite_ids is None:
            like_pattern = f"%{text}%"
            fts_match = _sanitize_fts_query(text)
            text_clauses: list[str] = []
            text_params: list = []
            if fts_match and self.fts_ready():
                text_clauses.append(
                    "authors.rowid IN (SELECT rowid FROM authors_fts WHERE authors_fts MATCH ?)"
                )
                text_params.append(fts_match)
            text_clauses.extend(
                [
                    "authors.service LIKE ?",
                    "CAST(authors.favorited AS TEXT) LIKE ?",
                    "strftime('%Y-%m-%d', authors.updated, 'unixepoch') LIKE ?",
                    "authors.name LIKE ?",
                ]
            )
            text_params.extend([like_pattern, like_pattern, like_pattern, like_pattern])
            clauses.append("(" + " OR ".join(text_clauses) + ")")
            params.extend(text_params)

        if not clauses:
            return "1=1", []
        return " AND ".join(clauses), params

    def count(self, query: AuthorQuery) -> int:
        if not self.db_path.exists():
            raise FileNotFoundError(f"kemono db not found: {self.db_path}")
        where_sql, params = self._build_where(query)
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM authors WHERE {where_sql}",
                params,
            ).fetchone()
        return int(row[0])

    def fetch(self, query: AuthorQuery, *, offset: int, limit: int) -> list[KemonoAuthor]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"kemono db not found: {self.db_path}")
        if limit <= 0:
            return []
        safe_offset = max(0, int(offset))
        safe_limit = max(0, int(limit))
        where_sql, params = self._build_where(query)
        sort_column, sort_direction = self._resolve_sort(query)
        sql = (
            f"SELECT authors.id, authors.name, authors.service, authors.updated, authors.favorited "
            f"FROM authors WHERE {where_sql} "
            f"ORDER BY authors.{sort_column} {sort_direction}, authors.id ASC "
            f"LIMIT ? OFFSET ?"
        )
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, [*params, safe_limit, safe_offset]).fetchall()
        return [_author_from_row(row) for row in rows]


def build_kemono_db_from_creators_bytes(db_path: Path, payload: bytes) -> int:
    data = json.loads(payload.decode("utf-8"))
    return KemonoAuthorsDb(db_path).replace_from_creators(data)


def load_kemono_authors(db_path: Path) -> dict[str, KemonoAuthor]:
    return KemonoAuthorsDb(db_path).load_all()
