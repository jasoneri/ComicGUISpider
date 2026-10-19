"""Cross-process instance discovery and secret persistence for the CGS aria2 engine.

One aria2c serves every CGS process: the owner spawns it and records the
endpoint here; every other process attaches by reading the record.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.request

if sys.platform != "win32":
    import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import psutil
from loguru import logger

from utils.script.aria2.bootstrap import resolve_aria2_layout

INSTANCE_SCHEMA_VERSION = 1
DEFAULT_RPC_PORT = 26800
# rpc-listen-all stays false, so the endpoint host is a contract, not instance state.
DEFAULT_RPC_HOST = "127.0.0.1"
RPC_PATH = "/jsonrpc"
# Client heartbeat older than this counts as gone (owner exit quorum).
CLIENT_HEARTBEAT_TTL_S = 30.0

ARIA2_LAYOUT = resolve_aria2_layout()


class Aria2InstanceError(RuntimeError):
    """Instance record exists but is unusable or belongs to another schema."""


@dataclass(frozen=True, slots=True)
class InstanceRecord:
    port: int
    secret: str
    pid: int
    owner_pid: int | None
    started_at: float
    schema_version: int = INSTANCE_SCHEMA_VERSION

    @property
    def jsonrpc_url(self) -> str:
        return f"http://{DEFAULT_RPC_HOST}:{self.port}{RPC_PATH}"

    def to_json(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "port": self.port,
            "secret": self.secret,
            "pid": self.pid,
            "owner_pid": self.owner_pid,
            "started_at": self.started_at,
        }

    @classmethod
    def from_json(cls, payload: dict) -> "InstanceRecord":
        if not isinstance(payload, dict):
            raise Aria2InstanceError(f"instance record must be an object, got {type(payload).__name__}")
        version = payload.get("schema_version")
        if version != INSTANCE_SCHEMA_VERSION:
            raise Aria2InstanceError(f"unsupported instance schema_version={version!r}")
        try:
            port = int(payload["port"])
            pid = int(payload["pid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Aria2InstanceError(f"instance record missing/invalid port or pid: {payload!r}") from exc
        resolved_owner = None if payload.get("owner_pid") is None else int(payload["owner_pid"])
        secret = str(payload.get("secret") or "")
        started_at = float(payload.get("started_at") or 0.0)
        return cls(port=port, secret=secret, pid=pid, owner_pid=resolved_owner, started_at=started_at)


@contextmanager
def exclusive_instance_lock(*, timeout_s: float = 10.0) -> Iterator[None]:
    """Serialise instance discovery/spawn across processes (TOCTOU guard)."""
    if sys.platform == "win32":
        with _windows_mutex_lock(timeout_s):
            yield
        return
    with _posix_flock_lock(timeout_s):
        yield


@contextmanager
def _windows_mutex_lock(timeout_s: float) -> Iterator[None]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    handle_value = kernel32.CreateMutexW(None, False, "Local\\CGS-aria2-instance")
    if not handle_value:
        raise OSError(f"CreateMutexW failed: {ctypes.get_last_error()}")
    handle = ctypes.c_void_p(handle_value)
    try:
        wait_result = kernel32.WaitForSingleObject(handle, int(timeout_s * 1000))
        if wait_result != 0:
            raise TimeoutError(f"aria2 instance lock not acquired within {timeout_s}s (wait={wait_result})")
        yield
    finally:
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


@contextmanager
def _posix_flock_lock(timeout_s: float) -> Iterator[None]:
    ARIA2_LAYOUT.work_dir.mkdir(parents=True, exist_ok=True)
    with ARIA2_LAYOUT.lock_path.open("a+", encoding="utf-8") as lock_file:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno != errno.EWOULDBLOCK or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def rpc_call(host: str, port: int, secret: str, method: str, *, timeout_s: float = 2.0) -> dict | None:
    """One JSON-RPC call; None when the endpoint is silent or rejects us."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": [f"token:{secret}"] if secret else [],
        "id": f"cgs-aria2-{method}",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "ComicGUISpider-cgs-aria2"}
    request = urllib.request.Request(f"http://{host}:{port}{RPC_PATH}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("error"):
        return None
    return body


def rpc_ping(host: str, port: int, secret: str, *, timeout_s: float = 0.5) -> bool:
    """aria2.getVersion over HTTP; false means "not ours / not answering"."""
    body = rpc_call(host, port, secret, "aria2.getVersion", timeout_s=timeout_s)
    if body is None:
        return False
    return isinstance(body.get("result"), dict) and bool(body.get("result"))


def rpc_shutdown(host: str, port: int, secret: str, *, timeout_s: float = 2.0) -> bool:
    """Graceful owner exit: persist the session, then stop the daemon.

    The owner may hold no subprocess handle (adopted instance), so shutdown
    goes over RPC rather than terminate().
    """
    rpc_call(host, port, secret, "aria2.saveSession", timeout_s=timeout_s)
    return rpc_call(host, port, secret, "aria2.shutdown", timeout_s=timeout_s) is not None


def pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    return psutil.pid_exists(pid)


def pid_runs_aria2(pid: int) -> bool:
    if pid <= 0 or not psutil.pid_exists(pid):
        return False
    try:
        name = psutil.Process(pid).name().lower()
    except psutil.NoSuchProcess:
        return False
    return "aria2" in name


def port_answering(host: str, port: int, *, timeout_s: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def probe_instance(record: InstanceRecord, *, timeout_s: float = 0.5) -> bool:
    """Triple liveness check: pid alive -> port open -> authenticated RPC."""
    if not pid_runs_aria2(record.pid):
        return False
    if not port_answering(DEFAULT_RPC_HOST, record.port, timeout_s=timeout_s):
        return False
    return rpc_ping(DEFAULT_RPC_HOST, record.port, record.secret, timeout_s=timeout_s)


def read_instance() -> InstanceRecord | None:
    path = ARIA2_LAYOUT.instance_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        raise Aria2InstanceError(f"unreadable instance record {path}: {exc}") from exc
    return InstanceRecord.from_json(payload)


def write_instance(record: InstanceRecord) -> None:
    path = ARIA2_LAYOUT.instance_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_json(), indent=2), encoding="utf-8")


def clear_instance() -> None:
    ARIA2_LAYOUT.instance_path.unlink(missing_ok=True)


def ensure_secret() -> str:
    """Persistent RPC token: shared by the owner and every attached client."""
    path = ARIA2_LAYOUT.secret_path
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(32)
    path.write_text(generated, encoding="utf-8")
    if os.name == "posix":
        # Windows inherits the per-user ACL of conf_dir; POSIX needs an explicit mode.
        os.chmod(path, 0o600)
    return generated


def write_heartbeat(pid: int) -> None:
    clients_dir = ARIA2_LAYOUT.clients_dir
    clients_dir.mkdir(parents=True, exist_ok=True)
    clients_dir.joinpath(f"{pid}.json").write_text(json.dumps({"pid": pid, "ts": time.time()}), encoding="utf-8")


def clear_heartbeat(pid: int) -> None:
    ARIA2_LAYOUT.clients_dir.joinpath(f"{pid}.json").unlink(missing_ok=True)


def live_other_clients(exclude_pid: int) -> tuple[int, ...]:
    """Pids with a fresh heartbeat other than `exclude_pid`."""
    clients_dir = ARIA2_LAYOUT.clients_dir
    if not clients_dir.exists():
        return ()
    now = time.time()
    live: list[int] = []
    for entry in clients_dir.glob("*.json"):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
            ts = float(payload["ts"])
        except (json.JSONDecodeError, ValueError, KeyError, TypeError, OSError) as exc:
            logger.warning(f"[CgsAria2] dropping unreadable heartbeat {entry}: {exc}")
            entry.unlink(missing_ok=True)
            continue
        if pid == exclude_pid:
            continue
        if now - ts > CLIENT_HEARTBEAT_TTL_S or not psutil.pid_exists(pid):
            entry.unlink(missing_ok=True)
            continue
        live.append(pid)
    return tuple(sorted(live))
