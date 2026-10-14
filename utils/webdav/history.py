#!/usr/bin/python
# -*- coding: utf-8 -*-
"""WebDAV 上传历史记录（落 `conf.sv_path/rV.db`，与 rv 的 metainfos/episodes 同库共存）。

契约（prd R-H1/R-H6/R-H9，DDL 为评审定稿，逐字落地）：

- 两表：`webdav_batches`（批次头，只存计数与时间）+ `webdav_uploads`（只记落地事实）。
- `result ∈ {pushed, skipped}`（CHECK 约束）；**失败不落条目行**——失败是环境态不是业务态，
  重推即重测（PROPFIND 幂等），头表 `failed` 只存计数。
- 本地路径一律相对库根（= rV.db 所在目录）的 posix 形式，禁存绝对路径；不存
  endpoint / root / entry_id / 远端目标列——端点与库根都不是批次业务数据。
- `episode_uid` 可空，声明式外键 → rv 既有 `episodes.id`（代理键，无 ON DELETE CASCADE：
  rv 拥有 episodes 生命周期，本表是消费方）；查不到填 NULL，不虚填。
- 并发：rv 扫描（短连接）与历史写入（GUI 线程批次开始/结束两个时点）靠 WAL 单写者 +
  `busy_timeout=5000` 串行化；一次 `finish_batch` = 单事务。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from utils import conf
from utils.chore import set_author_ahead

# 与 utils/sql._BATCH_IN_CHUNK 同约定：IN (...) 分块，避免超长 SQL / 变量上限。
_IN_CHUNK = 400

# rV.db 位于 Conf.sv_path；本地路径一律相对库根（= 本库目录 = rV.db 所在目录），禁存绝对路径
_BATCHES_DDL = """CREATE TABLE IF NOT EXISTS webdav_batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- 即 batch_num，自增即时增序
    started_at  TEXT NOT NULL,                       -- ISO-8601 本地时间
    finished_at TEXT,
    mode        TEXT NOT NULL,                       -- 批次时 resolved_mode()：manga|doujinshi
    pushed      INTEGER NOT NULL DEFAULT 0,          -- 冗余计数：flyout / 启动反馈只读头表
    skipped     INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,          -- 失败计数（失败不落条目行，见 R-H9）
    state       TEXT NOT NULL DEFAULT 'running'      -- running | done | aborted
)"""
_UPLOADS_DDL = """CREATE TABLE IF NOT EXISTS webdav_uploads (  -- 只记落地事实：pushed / skipped
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      INTEGER NOT NULL REFERENCES webdav_batches(id),
    episode_uid   INTEGER,                           -- 可空 FK → rv 既有 episodes.id（章节代理键）；解析不到不虚填
    book          TEXT NOT NULL,            -- 业务对象冗余展示列（免联表读取）
    ep            TEXT NOT NULL DEFAULT '',
    mode          TEXT NOT NULL,            -- 所属侧
    kind          TEXT NOT NULL,            -- cbz | dir
    relative_path TEXT NOT NULL,            -- 映射信息：相对库根的 posix 本地路径（行唯一锚点）
    size          INTEGER,                  -- 上传时本地字节和（cbz=单文件；dir=文件累加）
    result        TEXT NOT NULL CHECK (result IN ('pushed', 'skipped'))
)"""
_MATCH_INDEX_DDL = ("CREATE INDEX IF NOT EXISTS idx_webdav_uploads_match "
                    "ON webdav_uploads(relative_path, mode, batch_id)")

_INSERT_UPLOAD = """INSERT INTO webdav_uploads
    (batch_id, episode_uid, book, ep, mode, kind, relative_path, size, result)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
_FINISH_BATCH = """UPDATE webdav_batches
    SET finished_at = ?, pushed = ?, skipped = ?, failed = ?, state = 'done' WHERE id = ?"""
_LATEST_UPLOADS = """SELECT u.batch_id, u.relative_path, u.mode, u.book, u.ep, u.kind, u.size, u.result, u.episode_uid
    FROM webdav_uploads u JOIN webdav_batches b ON u.batch_id = b.id
    WHERE b.state = 'done' AND u.mode = ? AND u.relative_path IN ({placeholders})"""
_BATCH_HEADER_COLUMNS = "id, started_at, finished_at, mode, pushed, skipped, failed, state"


@dataclass(frozen=True)
class UploadRecord:
    """一条落地记录（快照真相）：行唯一锚点 (relative_path, mode)，取 batch_id 最大者。"""

    batch_id: int
    relative_path: str
    mode: str
    book: str
    ep: str
    kind: str
    size: int | None
    result: str
    episode_uid: int | None = None


@dataclass(frozen=True)
class BatchHeader:
    """批次头：flyout / 启动反馈只读它，不展开条目。"""

    id: int
    started_at: str
    finished_at: str | None
    mode: str
    pushed: int
    skipped: int
    failed: int
    state: str


def build_upload_rows(result: dict, mode: str) -> list[dict]:
    """pusher result 的 pushed/skipped 行 → 落地行（失败行不入库，R-H9）。

    mode 取批次值（resolved_mode()），不来自 result 行；size / relative_path 由 pusher
    result 行透出（对 pusher 的唯一改动）。
    """
    rows = []
    for outcome in ("pushed", "skipped"):
        for item in result.get(outcome) or ():
            rows.append({
                "book": item["book"],
                "ep": item.get("ep") or "",
                "mode": mode,
                "kind": item["kind"],
                "relative_path": item.get("relative_path") or "",
                "size": item.get("size"),
                "result": outcome,
            })
    return rows


def _chunks(values: list, size: int) -> Iterable[list]:
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


class WebdavHistoryStore:
    """rV.db 内 webdav 两表的读写入口。GUI 线程专用（批次开始/结束两个时点）。

    连接按 `conf.sv_path/rV.db` 惰性打开并缓存：sv_path 变更（换库）时自动重开——
    库跟随 Conf.sv_path，历史与 rv 数据同生命周期。
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._db_path: Path | None = None
        try:
            self._connect()
        except (sqlite3.Error, OSError):
            # 构造不开裂 UI：sv_path 尚不存在等场景下降级，后续调用按需重连。
            self._conn = None

    @property
    def db_path(self) -> Path:
        sv_path = conf.sv_path
        if not sv_path:
            raise sqlite3.OperationalError("conf.sv_path 未配置，无法定位 rV.db")
        return Path(sv_path).joinpath("rV.db")

    def _connect(self) -> sqlite3.Connection:
        path = self.db_path
        if self._conn is not None and self._db_path == path:
            return self._conn
        self.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(_BATCHES_DDL)
        cursor.execute(_UPLOADS_DDL)
        cursor.execute(_MATCH_INDEX_DDL)
        conn.commit()
        self._conn, self._db_path = conn, path
        # 打开时把上次遗留的 running 判 aborted：崩溃/强杀不谎报完成数。
        self._sweep(conn)
        return conn

    @staticmethod
    def _sweep(conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute("UPDATE webdav_batches SET state = 'aborted', finished_at = ? WHERE state = 'running'",
                         (datetime.now().isoformat(timespec="seconds"),))

    def sweep_stale_batches(self) -> None:
        """上次遗留 running → aborted（幂等）。"""
        self._sweep(self._connect())

    def close(self) -> None:
        conn, self._conn, self._db_path = self._conn, None, None
        if conn is not None:
            conn.close()

    def begin_batch(self, mode: str) -> int:
        """头表插 running 行，立刻拿号（batch_num = 自增 id，即时增序）。"""
        conn = self._connect()
        with conn:
            cursor = conn.execute("INSERT INTO webdav_batches (started_at, mode) VALUES (?, ?)",
                                  (datetime.now().isoformat(timespec="seconds"), mode))
        return int(cursor.lastrowid)

    def finish_batch(self, batch_id: int | None, *, pushed: int, skipped: int, failed: int,
                     landed: Iterable[dict] = ()) -> None:
        """单事务：episode_uid 解析 + 落地行 executemany + 头表终态 done（failed 只进计数）。"""
        if batch_id is None:
            return
        rows = list(landed)
        conn = self._connect()
        with conn:
            uids = self._resolve_episode_uids(conn, rows)
            conn.executemany(_INSERT_UPLOAD, [
                (batch_id, uid, row["book"], row["ep"], row["mode"], row["kind"],
                 row["relative_path"], row["size"], row["result"])
                for row, uid in zip(rows, uids)
            ])
            conn.execute(_FINISH_BATCH, (datetime.now().isoformat(timespec="seconds"),
                                         pushed, skipped, failed, batch_id))

    @staticmethod
    def _resolve_episode_uids(conn: sqlite3.Connection, rows: list[dict]) -> list[int | None]:
        """按 (set_author_ahead(book), ep) 查 episodes.id；表不存在 / 查不到 ⇒ NULL，不虚填。"""
        if not rows:
            return []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'episodes'").fetchone() is None:
            return [None] * len(rows)
        wanted = {(set_author_ahead(row["book"]), row["ep"] or "") for row in rows}
        found: dict[tuple[str, str], int] = {}
        for chunk in _chunks(sorted(wanted), _IN_CHUNK):
            placeholders = ",".join("(?, ?)" for _ in chunk)
            params = [value for pair in chunk for value in pair]
            for uid, book, ep in conn.execute(
                    f"SELECT id, book, ep FROM episodes WHERE (book, ep) IN ({placeholders})", params):
                found[(book, ep or "")] = uid
        return [found.get((set_author_ahead(row["book"]), row["ep"] or "")) for row in rows]

    def latest_uploads(self, mode: str, keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], UploadRecord]:
        """每键 (relative_path, mode) 取 batch_id 最大的落地记录；限定 mode + state='done'。

        后一次的落地覆盖先前的（单表取最大，无 Union、无 superseded 生命周期）。
        """
        conn = self._connect()
        paths = sorted({relative_path for relative_path, key_mode in keys if key_mode == mode})
        records: dict[tuple[str, str], UploadRecord] = {}
        for chunk in _chunks(paths, _IN_CHUNK):
            placeholders = ",".join("?" * len(chunk))
            for row in conn.execute(_LATEST_UPLOADS.format(placeholders=placeholders), (mode, *chunk)):
                record = UploadRecord(*row)
                current = records.get((record.relative_path, record.mode))
                if current is None or record.batch_id > current.batch_id:
                    records[(record.relative_path, record.mode)] = record
        return records

    def latest_done_batch(self) -> BatchHeader | None:
        """最新 done 批次头（启动反馈只消费它）；没有 ⇒ None。"""
        row = self._connect().execute(
            f"SELECT {_BATCH_HEADER_COLUMNS} FROM webdav_batches WHERE state = 'done' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return BatchHeader(*row) if row else None

    def recent_batches(self, limit: int = 50) -> list[BatchHeader]:
        """最近 limit 个批次（倒序）；flyout 限长展示，不展开失败条目。"""
        rows = self._connect().execute(
            f"SELECT {_BATCH_HEADER_COLUMNS} FROM webdav_batches ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [BatchHeader(*row) for row in rows]
