"""Per-job TagExport / Comfy submit snapshots in conf_dir/record.db.

Single system of record for:
- attach/COPY (prompt + unet + denoise + wd14 + tag groups)
- ComfyJobsDialog card list (status + preview + dismissed)

Survives CGS restart, PC reboot, and ComfyUI restart. Card rows must NOT
depend on Comfy /api/jobs history still being present.

Call sites that touch many jobs MUST use get_snapshots / list_local_job_cards
(one connection) and SHOULD run I/O off the Qt UI thread when possible —
see ComfyJobsDialog hydrate / restore path.

CGS007: tag_groups_json stores TagPrompt-shaped groups at submit time so Comfy
attach can rebuild Character/Artist/... without guessing from flat editor_prompt.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import typing as t
from pathlib import Path

from utils import conf_dir

_TABLE = "comfy_job_snapshots"
_KEEP_LAST = 500
_UNET_VALUES = frozenset({"turbo", "base", "aesthetic"})
_STATUS_VALUES = frozenset({"pending", "in_progress", "completed", "failed"})
_IN_CLAUSE_CHUNK = 200

_table_ready_path: str | None = None
_table_ready_lock = threading.Lock()


def _record_db_path():
    return conf_dir.joinpath("record.db")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_record_db_path(), timeout=5.0)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _ensure_table(connection: sqlite3.Connection) -> None:
    """CREATE IF NOT EXISTS + migrate card-index columns once per DB path."""
    global _table_ready_path
    path_key = str(_record_db_path().resolve())
    if _table_ready_path == path_key:
        return
    with _table_ready_lock:
        if _table_ready_path == path_key:
            return
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS `{_TABLE}` (
                job_id TEXT PRIMARY KEY,
                editor_prompt TEXT NOT NULL,
                unet TEXT NOT NULL,
                denoise INTEGER NOT NULL,
                wd14 INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                tag_groups_json TEXT,
                status TEXT NOT NULL DEFAULT 'completed',
                preview_json TEXT,
                dismissed INTEGER NOT NULL DEFAULT 0,
                updated_at REAL
            );
            """
        )
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info(`{_TABLE}`)").fetchall()
        }
        if "tag_groups_json" not in columns:
            connection.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN tag_groups_json TEXT;"
            )
        # Pre-card-index rows: treat as completed + visible so Comfy restart can restore.
        if "status" not in columns:
            connection.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN status TEXT NOT NULL DEFAULT 'completed';"
            )
        if "preview_json" not in columns:
            connection.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN preview_json TEXT;"
            )
        if "dismissed" not in columns:
            connection.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0;"
            )
        if "updated_at" not in columns:
            connection.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN updated_at REAL;"
            )
        # Indexes after column migrate — existing DBs lack dismissed until ALTER runs.
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_comfy_job_snapshots_created
            ON `{_TABLE}`(created_at);
            """
        )
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_comfy_job_snapshots_card
            ON `{_TABLE}`(dismissed, created_at DESC);
            """
        )
        connection.commit()
        _table_ready_path = path_key


def _normalize_unet(unet: object) -> str:
    value = str(unet or "").strip() or "turbo"
    if value not in _UNET_VALUES:
        return "turbo"
    return value


def _normalize_denoise(denoise: object) -> int:
    try:
        value = int(denoise)
    except (TypeError, ValueError):
        value = 100
    return max(10, min(100, value))


def _normalize_status(status: object, *, default: str = "completed") -> str:
    text = str(status or "").strip().casefold()
    aliases = {
        "pending": "pending",
        "queued": "pending",
        "queue": "pending",
        "in_progress": "in_progress",
        "running": "in_progress",
        "executing": "in_progress",
        "processing": "in_progress",
        "completed": "completed",
        "success": "completed",
        "successful": "completed",
        "failed": "failed",
        "error": "failed",
        "cancelled": "failed",
        "canceled": "failed",
        "interrupted": "failed",
    }
    normalized = aliases.get(text)
    if normalized in _STATUS_VALUES:
        return normalized
    return default if default in _STATUS_VALUES else "completed"


def encode_tag_groups(groups: object) -> str | None:
    """Serialize TagPrompt.groups-like structure to JSON text for SQLite."""
    if not groups:
        return None
    payload: list[list[t.Any]] = []
    for entry in groups:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        label = str(entry[0] or "").strip()
        tags_raw = entry[1]
        if not label or not isinstance(tags_raw, (list, tuple)):
            continue
        tags = [str(tag).strip() for tag in tags_raw if str(tag or "").strip()]
        if not tags:
            continue
        payload.append([label, tags])
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_tag_groups(raw: object) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Deserialize tag_groups_json → TagPrompt.groups shape."""
    text = str(raw or "").strip()
    if not text:
        return ()
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    groups: list[tuple[str, tuple[str, ...]]] = []
    for entry in payload:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        label = str(entry[0] or "").strip()
        tags_raw = entry[1]
        if not label or not isinstance(tags_raw, (list, tuple)):
            continue
        tags = tuple(str(tag).strip() for tag in tags_raw if str(tag or "").strip())
        if tags:
            groups.append((label, tags))
    return tuple(groups)


def encode_preview_output(preview: object) -> str | None:
    """Serialize preview for SQLite.

    Stores Comfy logical refs (filename/subfolder/type) **and** optional
    ``local_path`` (absolute filesystem path). Card restore after Comfy/PC
    restart must not depend on a live Comfy process to find the PNG.
    Either filename or local_path is enough to keep a row.
    """
    if not isinstance(preview, dict):
        return None
    filename_raw = preview.get("filename")
    filename = (
        filename_raw.strip()
        if isinstance(filename_raw, str) and filename_raw.strip()
        else ""
    )
    local_path_raw = preview.get("local_path")
    local_path = ""
    if isinstance(local_path_raw, str) and local_path_raw.strip():
        local_path = str(Path(local_path_raw.strip()).expanduser())
    elif local_path_raw is not None:
        try:
            local_path = str(Path(local_path_raw).expanduser())
        except (TypeError, ValueError, OSError):
            local_path = ""
    if not filename and not local_path:
        return None
    if not filename and local_path:
        filename = Path(local_path).name
    payload: dict[str, str] = {
        "filename": filename,
        "subfolder": str(preview.get("subfolder", "") or ""),
        "type": str(preview.get("type", "output") or "output"),
    }
    if local_path:
        payload["local_path"] = local_path
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_preview_output(raw: object) -> dict[str, str] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    filename_raw = payload.get("filename")
    filename = (
        filename_raw.strip()
        if isinstance(filename_raw, str) and filename_raw.strip()
        else ""
    )
    local_path_raw = payload.get("local_path")
    local_path = ""
    if isinstance(local_path_raw, str) and local_path_raw.strip():
        local_path = str(Path(local_path_raw.strip()).expanduser())
    if not filename and local_path:
        filename = Path(local_path).name
    if not filename and not local_path:
        return None
    result: dict[str, str] = {
        "filename": filename,
        "subfolder": str(payload.get("subfolder", "") or ""),
        "type": str(payload.get("type", "output") or "output"),
    }
    if local_path:
        result["local_path"] = local_path
    return result


def _row_to_snapshot(row: tuple) -> dict[str, t.Any]:
    """Map SELECT row → snapshot dict (prompt + optional card-index fields)."""
    # Historical widths: 6 (prompt-only), 7 (+tag_groups), 11 (+card index).
    tag_groups_json = row[6] if len(row) > 6 else None
    status = row[7] if len(row) > 7 else "completed"
    preview_json = row[8] if len(row) > 8 else None
    dismissed = row[9] if len(row) > 9 else 0
    updated_at = row[10] if len(row) > 10 else None
    preview_output = decode_preview_output(preview_json)
    return {
        "job_id": str(row[0]),
        "editor_prompt": str(row[1] or ""),
        "unet": _normalize_unet(row[2]),
        "denoise": _normalize_denoise(row[3]),
        "wd14": bool(int(row[4] or 0)),
        "created_at": float(row[5] or 0.0),
        "tag_groups_json": str(tag_groups_json) if tag_groups_json is not None else None,
        "tag_groups": decode_tag_groups(tag_groups_json),
        "status": _normalize_status(status, default="completed"),
        "preview_json": str(preview_json) if preview_json is not None else None,
        "preview_output": preview_output,
        "dismissed": bool(int(dismissed or 0)),
        "updated_at": float(updated_at) if updated_at is not None else None,
    }


def snapshot_to_job_record(snapshot: dict[str, t.Any]) -> dict[str, t.Any]:
    """Build a ComfyJobsDialog in-memory job dict from one SQLite snapshot row."""
    job_id = str(snapshot.get("job_id") or "").strip()
    unet = _normalize_unet(snapshot.get("unet"))
    status = _normalize_status(snapshot.get("status"), default="completed")
    job: dict[str, t.Any] = {
        "id": job_id,
        "status": status,
        "preset": unet,
        "editor_prompt": str(snapshot.get("editor_prompt") or ""),
        "tag_groups": snapshot.get("tag_groups") or (),
        "snapshot_unet": unet,
        "snapshot_denoise": snapshot.get("denoise"),
        "snapshot_wd14": snapshot.get("wd14"),
        "local_created_at": float(snapshot.get("created_at") or 0.0),
    }
    preview = snapshot.get("preview_output")
    if isinstance(preview, dict):
        job["preview_output"] = preview
    return job


def _normalized_job_ids(job_ids: t.Iterable[object]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in job_ids:
        job_id = str(raw or "").strip()
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        ordered.append(job_id)
    return ordered


def _prune_old_rows(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        DELETE FROM `{_TABLE}`
        WHERE job_id NOT IN (
            SELECT job_id FROM `{_TABLE}`
            ORDER BY created_at DESC
            LIMIT ?
        );
        """,
        (_KEEP_LAST,),
    )


def upsert_snapshot(
    job_id: str,
    *,
    editor_prompt: str,
    unet: str,
    denoise: int,
    wd14: bool,
    tag_groups: object = None,
    tag_groups_json: str | None = None,
    status: object = "pending",
    preview_output: object = None,
    dismissed: bool = False,
) -> dict[str, t.Any]:
    """Insert or replace one job snapshot; prune to keep last N rows.

    Safe to call from a worker thread. Caller owns any in-memory cache update.
    Prefer ``tag_groups`` (TagPrompt.groups shape); ``tag_groups_json`` is optional raw.

    Card-index fields (status / preview / dismissed) are written so ComfyJobsDialog
    can restore the row after ComfyUI or PC restart without /api/jobs history.
    """
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        raise ValueError("comfy job snapshot requires non-empty job_id")
    prompt_text = str(editor_prompt or "")
    unet_key = _normalize_unet(unet)
    denoise_percent = _normalize_denoise(denoise)
    wd14_flag = 1 if wd14 else 0
    now = time.time()
    status_key = _normalize_status(status, default="pending")
    preview_json = encode_preview_output(preview_output)
    dismissed_flag = 1 if dismissed else 0
    groups_json = (
        str(tag_groups_json).strip()
        if tag_groups_json is not None and str(tag_groups_json).strip()
        else encode_tag_groups(tag_groups)
    )
    row = {
        "job_id": normalized_job_id,
        "editor_prompt": prompt_text,
        "unet": unet_key,
        "denoise": denoise_percent,
        "wd14": bool(wd14_flag),
        "created_at": now,
        "tag_groups_json": groups_json,
        "tag_groups": decode_tag_groups(groups_json),
        "status": status_key,
        "preview_json": preview_json,
        "preview_output": decode_preview_output(preview_json),
        "dismissed": bool(dismissed_flag),
        "updated_at": now,
    }
    connection = _connect()
    try:
        _ensure_table(connection)
        connection.execute(
            f"""
            INSERT INTO `{_TABLE}`
                (job_id, editor_prompt, unet, denoise, wd14, created_at, tag_groups_json,
                 status, preview_json, dismissed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                editor_prompt = excluded.editor_prompt,
                unet = excluded.unet,
                denoise = excluded.denoise,
                wd14 = excluded.wd14,
                created_at = excluded.created_at,
                tag_groups_json = excluded.tag_groups_json,
                status = excluded.status,
                preview_json = COALESCE(excluded.preview_json, `{_TABLE}`.preview_json),
                dismissed = excluded.dismissed,
                updated_at = excluded.updated_at;
            """,
            (
                normalized_job_id,
                prompt_text,
                unet_key,
                denoise_percent,
                wd14_flag,
                now,
                groups_json,
                status_key,
                preview_json,
                dismissed_flag,
                now,
            ),
        )
        _prune_old_rows(connection)
        connection.commit()
    finally:
        connection.close()
    return row


def update_job_runtime(
    job_id: str,
    *,
    status: object = None,
    preview_output: object = None,
) -> dict[str, t.Any] | None:
    """Patch status/preview on an existing row without rewriting prompt fields.

    Returns updated snapshot dict, or None when the job_id is unknown.
    Safe from worker threads.
    """
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    status_key = (
        _normalize_status(status, default="completed") if status is not None else None
    )
    preview_json = (
        encode_preview_output(preview_output) if preview_output is not None else None
    )
    if status_key is None and preview_json is None:
        return get_snapshot(normalized_job_id)
    now = time.time()
    connection = _connect()
    try:
        _ensure_table(connection)
        existing = connection.execute(
            f"SELECT 1 FROM `{_TABLE}` WHERE job_id = ? LIMIT 1;",
            (normalized_job_id,),
        ).fetchone()
        if existing is None:
            return None
        assignments: list[str] = ["updated_at = ?"]
        values: list[object] = [now]
        if status_key is not None:
            assignments.append("status = ?")
            values.append(status_key)
        if preview_json is not None:
            assignments.append("preview_json = ?")
            values.append(preview_json)
        values.append(normalized_job_id)
        connection.execute(
            f"UPDATE `{_TABLE}` SET {', '.join(assignments)} WHERE job_id = ?;",
            values,
        )
        connection.commit()
    finally:
        connection.close()
    return get_snapshot(normalized_job_id)


def dismiss_job(job_id: str) -> bool:
    """Soft-delete a card so refresh will not restore it. Returns True if a row was updated."""
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    now = time.time()
    connection = _connect()
    try:
        _ensure_table(connection)
        cursor = connection.execute(
            f"""
            UPDATE `{_TABLE}`
            SET dismissed = 1, updated_at = ?
            WHERE job_id = ? AND dismissed = 0;
            """,
            (now, normalized_job_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def list_local_job_cards(
    *,
    limit: int = 100,
    include_dismissed: bool = False,
) -> list[dict[str, t.Any]]:
    """Recent snapshot rows for ComfyJobsDialog restore (newest first).

    One connection. Prefer calling from a worker when the UI is already painted;
    a single LIMIT query is also acceptable on dialog open.
    """
    try:
        row_limit = max(1, min(int(limit), _KEEP_LAST))
    except (TypeError, ValueError):
        row_limit = 100
    connection = _connect()
    try:
        _ensure_table(connection)
        if include_dismissed:
            cursor = connection.execute(
                f"""
                SELECT job_id, editor_prompt, unet, denoise, wd14, created_at,
                       tag_groups_json, status, preview_json, dismissed, updated_at
                FROM `{_TABLE}`
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (row_limit,),
            )
        else:
            cursor = connection.execute(
                f"""
                SELECT job_id, editor_prompt, unet, denoise, wd14, created_at,
                       tag_groups_json, status, preview_json, dismissed, updated_at
                FROM `{_TABLE}`
                WHERE dismissed = 0
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (row_limit,),
            )
        return [_row_to_snapshot(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def get_snapshots(job_ids: t.Iterable[object]) -> dict[str, dict[str, t.Any]]:
    """Batch load snapshots in one connection. Prefer this over N× get_snapshot on UI paths."""
    normalized_ids = _normalized_job_ids(job_ids)
    if not normalized_ids:
        return {}
    result: dict[str, dict[str, t.Any]] = {}
    connection = _connect()
    try:
        _ensure_table(connection)
        for offset in range(0, len(normalized_ids), _IN_CLAUSE_CHUNK):
            chunk = normalized_ids[offset : offset + _IN_CLAUSE_CHUNK]
            placeholders = ", ".join("?" for _ in chunk)
            cursor = connection.execute(
                f"""
                SELECT job_id, editor_prompt, unet, denoise, wd14, created_at,
                       tag_groups_json, status, preview_json, dismissed, updated_at
                FROM `{_TABLE}`
                WHERE job_id IN ({placeholders});
                """,
                chunk,
            )
            for row in cursor.fetchall():
                snapshot = _row_to_snapshot(row)
                result[snapshot["job_id"]] = snapshot
    finally:
        connection.close()
    return result


def get_snapshot(job_id: str) -> dict[str, t.Any] | None:
    """Return one snapshot or None. Prefer get_snapshots when loading many ids."""
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    return get_snapshots((normalized_job_id,)).get(normalized_job_id)


__all__ = [
    "decode_preview_output",
    "decode_tag_groups",
    "dismiss_job",
    "encode_preview_output",
    "encode_tag_groups",
    "get_snapshot",
    "get_snapshots",
    "list_local_job_cards",
    "snapshot_to_job_record",
    "update_job_runtime",
    "upsert_snapshot",
]
