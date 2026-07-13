from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from utils.config import conf_dir

SERVER_DISCOVERY_SCHEMA = 1
SERVER_DISCOVERY_NAME = "ComicGUISpider"
SERVER_DISCOVERY_FILE_PREFIX = "cgs-server-"
SERVER_DISCOVERY_FILE_SUFFIX = ".json"
SERVER_AUTH_HEADER = "Authorization"
SERVER_AUTH_SCHEME = "Bearer"
DEFAULT_SERVER_BIND_HOST = "0.0.0.0"
DEFAULT_SERVER_MCP_PATH = "/mcp"
TRAY_SERVER_SURFACE = "tray"
TRAY_HOSTED_SERVER_REQUIRED_SURFACES = (TRAY_SERVER_SURFACE,)
SERVER_DISCOVERY_HEALTH_GRACE_SECONDS = 5.0
DEFAULT_SERVER_LAUNCH_TIMEOUT = 30.0
_LOG_TAIL_CHARS = 4000
SERVER_LAUNCH_LOG_ROTATION = "5 MB"
SERVER_LAUNCH_LOG_RETENTION = "1 day"
_WIN32_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WIN32_STILL_ACTIVE = 259
_WIN32_ERROR_ACCESS_DENIED = 5
_server_launch_log_configured = False
_server_launch_log_sink_id: int | None = None


class ServerDiscoveryError(RuntimeError):
    pass


class NoServerDiscoveryError(ServerDiscoveryError):
    pass


class MultipleServerDiscoveryError(ServerDiscoveryError):
    pass


class IncompatibleServerDiscoveryError(ServerDiscoveryError):
    pass


class InvalidServerDiscoveryError(ServerDiscoveryError):
    pass


class UnhealthyServerDiscoveryError(ServerDiscoveryError):
    pass


class ServerLaunchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ServerEndpoint:
    connect_url: str
    token: str

    @property
    def auth_header(self) -> str:
        return f"{SERVER_AUTH_SCHEME} {self.token}"


@dataclass(frozen=True, slots=True)
class ServerDiscoveryRecord:
    schema: int
    server: str
    instance_id: str
    pid: int
    version: str
    created_at: str
    bind_host: str
    connect_url: str
    port: int
    health_url: str
    token: str
    surfaces: tuple[str, ...]

    @property
    def endpoint(self) -> ServerEndpoint:
        return ServerEndpoint(connect_url=self.connect_url.rstrip("/"), token=self.token)

    def redacted(self) -> dict:
        payload = asdict(self)
        payload["token"] = "<redacted>"
        return payload


def discovery_dir() -> Path:
    path = conf_dir.joinpath("runtime")
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_server_record(*, bind_host: str, port: int, surfaces: tuple[str, ...], version: str = "") -> ServerDiscoveryRecord:
    connect_url = f"http://{_connect_host(bind_host)}:{int(port)}"
    return ServerDiscoveryRecord(
        schema=SERVER_DISCOVERY_SCHEMA, server=SERVER_DISCOVERY_NAME, instance_id=uuid4().hex, pid=os.getpid(),
        version=str(version or ""), created_at=datetime.now(timezone.utc).isoformat(), bind_host=str(bind_host),
        connect_url=connect_url, port=int(port), health_url=f"{connect_url}/health",
        token=secrets.token_urlsafe(32), surfaces=tuple(str(surface) for surface in surfaces),
    )


def write_server_record(record: ServerDiscoveryRecord) -> Path:
    target = record_path(record.instance_id)
    payload = asdict(record)
    payload["surfaces"] = list(record.surfaces)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=discovery_dir(), delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.write("\n")
        temp_path = Path(tmp.name)
    if os.name != "nt":
        os.chmod(temp_path, 0o600)
    temp_path.replace(target)
    return target


def remove_server_record(record: ServerDiscoveryRecord) -> None:
    with suppress(OSError):
        record_path(record.instance_id).unlink()


def remove_server_records_for_pid(pid: int) -> None:
    pid = int(pid)
    for path in _iter_record_paths():
        record = _read_record(path)
        if record is not None and record.pid == pid:
            _remove_path(path)


def record_path(instance_id: str) -> Path:
    return discovery_dir().joinpath(f"{SERVER_DISCOVERY_FILE_PREFIX}{instance_id}{SERVER_DISCOVERY_FILE_SUFFIX}")


def resolve_server_endpoint(
        *,
        timeout: float = 0.25,
        expected_version: str | None = None,
        required_surfaces: tuple[str, ...] = (),
        allowed_starting_pids: tuple[int, ...] = (),
) -> ServerEndpoint:
    required_surfaces = _normalize_surfaces(required_surfaces)
    allowed_starting_pids = tuple(int(pid) for pid in allowed_starting_pids)
    matches = []
    incompatible = []
    unhealthy = []
    for path in _iter_record_paths():
        record = _read_record(path)
        if record is None:
            continue
        if not _pid_exists(record.pid):
            _remove_path(path)
            continue
        if _health_matches(record, timeout=timeout):
            if _record_is_incompatible(record, expected_version=expected_version, required_surfaces=required_surfaces):
                incompatible.append(record)
                continue
            matches.append(record)
        elif record.pid in allowed_starting_pids:
            continue
        elif not _within_health_grace(record):
            unhealthy.append(record)
    if incompatible:
        raise IncompatibleServerDiscoveryError(f"incompatible CGS Server discovery record found: {_record_summaries(incompatible)}")
    if unhealthy:
        raise UnhealthyServerDiscoveryError(
            f"CGS Server discovery record has a live PID but failed health validation: {_record_summaries(unhealthy)}"
        )
    if not matches:
        raise NoServerDiscoveryError("no compatible CGS Server discovery record found")
    if len(matches) > 1:
        raise MultipleServerDiscoveryError(f"multiple compatible CGS Server discovery records found: {_record_summaries(matches)}")
    matches.sort(key=lambda item: item.created_at, reverse=True)
    return matches[0].endpoint


def starting_server_record_summaries(
        *,
        expected_version: str | None = None,
        required_surfaces: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    required_surfaces = _normalize_surfaces(required_surfaces)
    starting = []
    incompatible = []
    for path in _iter_record_paths():
        record = _read_record(path)
        if record is None:
            continue
        if not _pid_exists(record.pid):
            _remove_path(path)
            continue
        if not _within_health_grace(record):
            continue
        if _record_is_incompatible(record, expected_version=expected_version, required_surfaces=required_surfaces):
            incompatible.append(record)
            continue
        starting.append(record)
    if incompatible:
        raise IncompatibleServerDiscoveryError(f"incompatible CGS Server discovery record found: {_record_summaries(incompatible)}")
    return _record_summaries(starting)


def auth_headers(endpoint: ServerEndpoint) -> dict[str, str]:
    return {SERVER_AUTH_HEADER: endpoint.auth_header}


def is_authorized_header(value: str | None, token: str) -> bool:
    if not value:
        return False
    scheme, separator, supplied = value.partition(" ")
    return bool(separator) and scheme.lower() == SERVER_AUTH_SCHEME.lower() and secrets.compare_digest(supplied.strip(), token)


def redact_endpoint(endpoint: ServerEndpoint) -> dict:
    return {"connect_url": endpoint.connect_url, "token": "<redacted>"}


def bind_tcp_socket(host: str = DEFAULT_SERVER_BIND_HOST, port: int = 0) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, int(port)))
    sock.listen(128)
    return sock


def socket_port(sock: socket.socket) -> int:
    return int(sock.getsockname()[1])


def wait_for_server(endpoint: ServerEndpoint, *, timeout: float = 10.0, interval: float = 0.1) -> None:
    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        request = urllib.request.Request(f"{endpoint.connect_url}/health", headers=auth_headers(endpoint))
        try:
            with urllib.request.urlopen(request, timeout=interval) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("server") == SERVER_DISCOVERY_NAME
                and payload.get("authenticated") is True
                and payload.get("authorized") is True
            ):
                return
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(interval)
    raise ServerDiscoveryError(f"CGS Server did not become ready at {endpoint.connect_url}")


class ServerLauncher:
    def __init__(self, *, timeout: float = DEFAULT_SERVER_LAUNCH_TIMEOUT) -> None:
        self.timeout = float(timeout)
        self.command = _server_command()
        self.log_path = server_launch_log_path()
        self.boot_log_path = server_launch_boot_log_path()
        self.process = None
        self.spawned_pid: int | None = None

    def launch_or_resolve(self) -> ServerEndpoint:
        endpoint = self.resolve_existing()
        if endpoint is not None:
            sync_redviewer_server_endpoint(endpoint)
            return endpoint
        return self._launch_and_wait()

    def resolve_existing(self) -> ServerEndpoint | None:
        from variables import VER

        deadline = time.monotonic() + self.timeout
        while True:
            try:
                return resolve_server_endpoint(timeout=0.5, expected_version=VER, required_surfaces=TRAY_HOSTED_SERVER_REQUIRED_SURFACES)
            except NoServerDiscoveryError:
                starting = starting_server_record_summaries(expected_version=VER, required_surfaces=TRAY_HOSTED_SERVER_REQUIRED_SURFACES)
                if not starting:
                    return None
                if time.monotonic() >= deadline:
                    raise ServerLaunchError(f"cgs-server is still starting: {starting}")
                time.sleep(0.1)

    def _launch_and_wait(self) -> ServerEndpoint:
        from utils.config import env, exc_p
        from variables import VER

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.boot_log_path, "wb") as log_file:
                self.process = subprocess.Popen(
                    self.command, cwd=str(exc_p), env=env, stdout=log_file, stderr=subprocess.STDOUT, **_popen_kwargs()
                )
        except OSError as exc:
            raise ServerLaunchError(self._failure_message("cgs-server launch failed")) from exc

        self.spawned_pid = _process_pid(self.process)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ServerLaunchError(
                    self._failure_message(f"cgs-server exited with code {self.process.returncode}", timeout=self.timeout)
                )
            try:
                endpoint = resolve_server_endpoint(
                    timeout=0.5,
                    expected_version=VER,
                    required_surfaces=TRAY_HOSTED_SERVER_REQUIRED_SURFACES,
                    allowed_starting_pids=_starting_process_pids(self.spawned_pid),
                )
            except NoServerDiscoveryError:
                time.sleep(0.1)
                continue
            except ServerDiscoveryError:
                self._stop_and_cleanup()
                raise
            except Exception as exc:
                self._stop_and_cleanup()
                raise ServerLaunchError(self._failure_message("cgs-server discovery failed", timeout=self.timeout, cause=exc)) from exc
            try:
                sync_redviewer_server_endpoint(endpoint)
            except Exception as exc:
                self._stop_and_cleanup()
                raise ServerLaunchError(
                    self._failure_message("cgs-server redViewer sync failed", timeout=self.timeout, cause=exc)
                ) from exc
            return endpoint

        diagnostics = self._failure_message("cgs-server did not become ready", timeout=self.timeout)
        self._stop_and_cleanup()
        raise ServerLaunchError(diagnostics)

    def _stop_and_cleanup(self) -> None:
        spawned_pids = _starting_process_pids(self.spawned_pid)
        if self.process is not None:
            _stop_launched_process(self.process)
        _remove_spawned_discovery_records(spawned_pids)

    def _failure_message(self, reason: str, *, timeout: float | None = None, cause: BaseException | None = None) -> str:
        return _launch_failure_message(
            reason,
            command=self.command,
            log_path=self.log_path,
            boot_log_path=self.boot_log_path,
            process=self.process,
            timeout=timeout,
            cause=cause,
        )


def server_launch_log_path() -> Path:
    return conf_dir.joinpath("runtime", "cgs-server-launch.log")


def server_launch_boot_log_path() -> Path:
    return conf_dir.joinpath("runtime", "cgs-server-launch.boot.log")


def configure_server_launch_logging() -> int:
    global _server_launch_log_configured, _server_launch_log_sink_id
    if _server_launch_log_configured and _server_launch_log_sink_id is not None:
        return _server_launch_log_sink_id

    from loguru import logger

    log_path = server_launch_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # The launcher keeps a small boot log for pre-loguru crashes; the long-lived
    # runtime log itself is owned by loguru and rotates independently.
    logger.remove()
    _server_launch_log_sink_id = logger.add(
        log_path,
        rotation=SERVER_LAUNCH_LOG_ROTATION,
        retention=SERVER_LAUNCH_LOG_RETENTION,
        encoding="utf-8",
        level="DEBUG",
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {process} | {thread.name} | {name}:{function}:{line} - {message}",
    )
    sys.stdout = _LoguruStream("INFO")
    sys.stderr = _LoguruStream("ERROR")
    _redirect_stdio_file_descriptors_to_devnull()
    _server_launch_log_configured = True
    return _server_launch_log_sink_id


def _redirect_stdio_file_descriptors_to_devnull() -> None:
    with open(os.devnull, "wb", buffering=0) as devnull:
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)


class _LoguruStream:
    def __init__(self, level: str) -> None:
        self.level = level
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += str(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            line = self._buffer
            self._buffer = ""
            self._emit(line)

    def isatty(self) -> bool:
        return False

    def _emit(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        from loguru import logger

        logger.opt(depth=2).log(self.level, line)


def sync_redviewer_server_endpoint(endpoint: ServerEndpoint) -> None:
    from utils import conf
    from utils.config import yaml_update

    rv_script = conf.rv_script
    if not rv_script or str(rv_script) == ".":
        return
    rv_conf = rv_script.parent.joinpath(r"redViewer/backend/conf.yml")
    if rv_conf.exists():
        yaml_update(
            rv_conf,
            {
                "cgs_server_base_url": endpoint.connect_url,
                "cgs_server_token": endpoint.token,
                "cgs_server_runtime_dir": str(discovery_dir()),
            },
        )


def notify_server_foreground(path: str, *, endpoint: ServerEndpoint | None = None, timeout: float = 0.25) -> ServerEndpoint | None:
    from variables import VER

    endpoint_was_provided = endpoint is not None
    if endpoint is None:
        try:
            endpoint = resolve_server_endpoint(
                timeout=timeout, expected_version=VER, required_surfaces=TRAY_HOSTED_SERVER_REQUIRED_SURFACES
            )
        except NoServerDiscoveryError:
            return None
    request = urllib.request.Request(
        f"{endpoint.connect_url}{path}", data=b"{}", method="POST",
        headers={"Content-Type": "application/json", **auth_headers(endpoint)},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return endpoint
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CGS Server foreground request failed: {exc.code} {body}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout) as exc:
        if endpoint_was_provided:
            raise RuntimeError(f"CGS Server foreground request failed: {endpoint.connect_url}{path}: {exc}") from exc
        return None


def _server_command() -> list[str]:
    return [str(_server_python()), "-m", "server.main"]


def _server_python() -> Path:
    from utils.config import code_env, exc_p

    if code_env == "git":
        executable = "python.exe" if sys.platform == "win32" else "python"
        venv_python = exc_p.joinpath(".venv", "Scripts" if sys.platform == "win32" else "bin", executable)
        if venv_python.exists():
            return venv_python
    return Path(sys.executable)


def _popen_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _stop_launched_process(process) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _process_pid(process) -> int | None:
    pid = getattr(process, "pid", None)
    if pid is None:
        return None
    return int(pid)


def _starting_process_pids(pid: int | None) -> tuple[int, ...]:
    if pid is None:
        return ()
    root_pid = int(pid)
    pids = {root_pid}
    try:
        import psutil
    except ImportError:
        return tuple(sorted(pids))
    try:
        process = psutil.Process(root_pid)
        children = process.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return tuple(sorted(pids))
    for child in children:
        pids.add(int(child.pid))
    return tuple(sorted(pids))


def _remove_spawned_discovery_records(pids: tuple[int, ...]) -> None:
    for pid in pids:
        remove_server_records_for_pid(pid)


def _launch_failure_message(
        reason: str,
        *,
        command: list[str],
        log_path: Path,
        boot_log_path: Path,
        process=None,
        timeout: float | None = None,
        cause: BaseException | None = None,
) -> str:
    from utils.config import exc_p

    lines = [f"{reason}; log: {log_path}"]
    lines.append(f"boot_log: {boot_log_path}")
    lines.append(f"command: {_format_command(command)}")
    lines.append(f"cwd: {exc_p}")
    if timeout is not None:
        lines.append(f"timeout: {float(timeout):.1f}s")
    if process is not None:
        pid = getattr(process, "pid", None)
        if pid is not None:
            lines.append(f"pid: {pid}")
        returncode = process.poll()
        lines.append(f"process_returncode: {returncode!r}")
    if cause is not None:
        lines.append(f"cause: {type(cause).__name__}: {cause}")
    lines.append(f"discovery: {_current_discovery_state()}")
    log_tail = _read_log_tail(log_path)
    if log_tail:
        lines.append("log_tail:")
        lines.append(log_tail)
    else:
        lines.append("log_tail: <empty>")
    boot_log_tail = _read_log_tail(boot_log_path)
    if boot_log_tail:
        lines.append("boot_log_tail:")
        lines.append(boot_log_tail)
    return "\n".join(lines)


def _format_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def _current_discovery_state() -> str:
    try:
        from variables import VER

        starting = starting_server_record_summaries(expected_version=VER, required_surfaces=TRAY_HOSTED_SERVER_REQUIRED_SURFACES)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    if starting:
        return f"starting tray-hosted records: {starting}"
    return "no tray-hosted discovery record published"


def _read_log_tail(path: Path, *, limit: int = _LOG_TAIL_CHARS) -> str:
    try:
        with open(path, "rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - int(limit)))
            text = log_file.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return _redact_sensitive_text(text.strip())


def _redact_sensitive_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(?i)(Authorization:\s*Bearer\s+)[^\s\"']+", r"\1<redacted>", text)
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+\-/=]{16,}", r"\1<redacted>", text)
    text = re.sub(r'(?i)("token"\s*:\s*")[^"]+(")', r"\1<redacted>\2", text)
    text = re.sub(r"(?i)('token'\s*:\s*')[^']+(')", r"\1<redacted>\2", text)
    return text


def _record_summaries(records: list[ServerDiscoveryRecord]) -> list[dict[str, object]]:
    return [
        {
            "instance_id": record.instance_id,
            "pid": record.pid,
            "version": record.version,
            "connect_url": record.connect_url,
            "surfaces": record.surfaces,
        }
        for record in records
    ]


def _normalize_surfaces(surfaces: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(surface) for surface in surfaces)


def _record_is_incompatible(
        record: ServerDiscoveryRecord,
        *,
        expected_version: str | None,
        required_surfaces: tuple[str, ...],
) -> bool:
    if expected_version is not None and record.version != str(expected_version):
        return True
    if not set(required_surfaces).issubset(record.surfaces):
        return True
    return False


def _iter_record_paths():
    return discovery_dir().glob(f"{SERVER_DISCOVERY_FILE_PREFIX}*{SERVER_DISCOVERY_FILE_SUFFIX}")


def _read_record(path: Path) -> ServerDiscoveryRecord | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise InvalidServerDiscoveryError(f"invalid CGS Server discovery JSON: {path}") from exc
    except OSError as exc:
        raise InvalidServerDiscoveryError(f"cannot read CGS Server discovery record: {path}") from exc
    if not isinstance(payload, dict):
        raise InvalidServerDiscoveryError(f"invalid CGS Server discovery payload: {path}")
    if payload.get("schema") != SERVER_DISCOVERY_SCHEMA or payload.get("server") != SERVER_DISCOVERY_NAME:
        raise IncompatibleServerDiscoveryError(f"incompatible CGS Server discovery identity: {path}")
    surfaces = payload.get("surfaces") or ()
    if not isinstance(surfaces, (list, tuple)):
        raise InvalidServerDiscoveryError(f"invalid CGS Server discovery surfaces: {path}")
    try:
        return ServerDiscoveryRecord(
            schema=int(payload["schema"]), server=str(payload["server"]), instance_id=str(payload["instance_id"]), pid=int(payload["pid"]),
            version=str(payload.get("version") or ""), created_at=str(payload["created_at"]), bind_host=str(payload["bind_host"]),
            connect_url=str(payload["connect_url"]).rstrip("/"), port=int(payload["port"]), health_url=str(payload["health_url"]),
            token=str(payload["token"]), surfaces=tuple(str(surface) for surface in surfaces),
        )
    except (KeyError, TypeError, ValueError):
        raise InvalidServerDiscoveryError(f"incomplete CGS Server discovery record: {path}")


def _health_matches(record: ServerDiscoveryRecord, *, timeout: float) -> bool:
    request = urllib.request.Request(record.health_url, headers=auth_headers(record.endpoint))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("server") == SERVER_DISCOVERY_NAME
        and payload.get("authenticated") is True
        and payload.get("authorized") is True
    )


def _within_health_grace(record: ServerDiscoveryRecord) -> bool:
    try:
        created_at = datetime.fromisoformat(record.created_at)
    except ValueError:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)).total_seconds()
    return age < SERVER_DISCOVERY_HEALTH_GRACE_SECONDS


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    if os.name == "nt":
        return _pid_exists_windows(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_exists_windows(pid: int) -> bool:
    windll = getattr(ctypes, "windll", None)
    kernel32 = getattr(windll, "kernel32", None)
    if kernel32 is None:
        return True
    handle = kernel32.OpenProcess(_WIN32_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return _windows_last_error(kernel32) == _WIN32_ERROR_ACCESS_DENIED
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == _WIN32_STILL_ACTIVE
    finally:
        close_handle = getattr(kernel32, "CloseHandle", None)
        if close_handle is not None:
            with suppress(OSError):
                close_handle(handle)


def _windows_last_error(kernel32) -> int | None:
    getter = getattr(kernel32, "GetLastError", None)
    if getter is None:
        return None
    try:
        return int(getter())
    except (TypeError, ValueError):
        return None


def _connect_host(bind_host: str) -> str:
    if bind_host in {"", "0.0.0.0"}:
        return "127.0.0.1"
    if bind_host == "::":
        return "[::1]"
    if ":" in bind_host and not bind_host.startswith("["):
        return f"[{bind_host}]"
    return bind_host


def _remove_path(path: Path) -> None:
    with suppress(OSError):
        path.unlink()
