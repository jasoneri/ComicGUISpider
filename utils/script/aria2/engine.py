from __future__ import annotations

import atexit
import os
import pathlib as p
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace

from loguru import logger

from utils.config.qc import cgs_cfg
from utils.network.doh import dns_stub_server
from utils.script.aria2.bootstrap import ensure_aira2_binary, resolve_aria2_layout
from utils.script.aria2.conf import build_aria2_option_map, write_aria2_conf
from utils.script.aria2.lock import (
    DEFAULT_RPC_HOST,
    Aria2InstanceError,
    InstanceRecord,
    clear_instance,
    clear_heartbeat,
    ensure_secret,
    exclusive_instance_lock,
    live_other_clients,
    pid_alive,
    port_answering,
    probe_instance,
    read_instance,
    rpc_ping,
    rpc_shutdown,
    write_heartbeat,
    write_instance,
)
from utils.script.aria2.rpc import Aria2RpcClient
from utils.script.aria2.settings import get_proxy, get_rpc_port, singleton_enabled

# One layout object owns every managed path (work dir, binary, conf, session, pid).
ARIA2_LAYOUT = resolve_aria2_layout()
# Startup budget is shared across both attempts (bounds worst case below the old
# 2 x per-attempt shape) but stays at the historical per-attempt ceiling: shaving
# it turns a cold spawn (fresh file cache / AV scan of the 5MB binary) into a
# false failure. Measured steady-state start is well under 1s.
ENSURE_TIMEOUT_S = 8.0
PING_INTERVAL_S = 0.15
# Per-attempt RPC ping during startup wait; keep short so a dead port fails fast.
STARTUP_PING_TIMEOUT_S = 0.5


ROLE_OWNER = "owner"
ROLE_CLIENT = "client"
# Owner hands the endpoint to spawned children so they attach instead of spawning.
ENV_ENDPOINT = "CGS_ARIA2_ENDPOINT"
ENV_SECRET = "CGS_ARIA2_SECRET"
ENV_NO_SPAWN = "CGS_ARIA2_NO_SPAWN"


@dataclass(frozen=True, slots=True)
class RuntimeEndpoint:
    host: str
    port: int
    secret: str
    conf_path: p.Path
    binary_path: p.Path
    pid: int | None
    role: str = ROLE_OWNER

    @property
    def jsonrpc_url(self) -> str:
        return f"http://{self.host}:{self.port}/jsonrpc"


class CgsAria2Engine:
    def __init__(self):
        self._lock = threading.RLock()
        self._endpoint: RuntimeEndpoint | None = None
        self._process: subprocess.Popen | None = None

    @property
    def endpoint(self) -> RuntimeEndpoint | None:
        with self._lock:
            return self._endpoint

    def is_ready(self) -> bool:
        with self._lock:
            return self._endpoint is not None and self._endpoint_reachable(self._endpoint)

    def ensure(
        self,
        *,
        proxy: object | None = None,
        dns_server: object | None = None,
        force_restart: bool = False,
        progress_callback=None,
    ) -> RuntimeEndpoint:
        with self._lock:
            resolved_proxy = normalize_proxy_arg(proxy)
            dns = resolve_dns_server(dns_server)
            if not force_restart and self._endpoint is not None and self._endpoint_reachable(self._endpoint):
                return self._endpoint
            self._stop_locked()
            if singleton_enabled():
                attached = self._attach_existing()
                if attached is not None:
                    self._endpoint = attached
                    write_heartbeat(os.getpid())
                    return attached
            return self._spawn_owned(resolved_proxy, dns, progress_callback)

    def _endpoint_reachable(self, endpoint: RuntimeEndpoint) -> bool:
        """Clients and adopted owners hold no subprocess; liveness is the RPC ping."""
        if endpoint.role == ROLE_OWNER and self._process is not None and not self._process_alive():
            return False
        return self._rpc_ping_sync(endpoint)

    def _attach_existing(self) -> RuntimeEndpoint | None:
        from_env = self._endpoint_from_env()
        if from_env is not None:
            return from_env
        with exclusive_instance_lock():
            try:
                record = read_instance()
            except Aria2InstanceError as exc:
                logger.warning(f"[CgsAria2] discarding unusable instance record: {exc}")
                clear_instance()
                return None
            if record is None:
                return None
            if not probe_instance(record):
                logger.info(f"[CgsAria2] dropping stale instance record port={record.port} pid={record.pid}")
                clear_instance()
                return None
        # Owner gone (crash / kill): adopt the running daemon instead of leaving
        # it orphaned — this is the plan-B recovery path (design D4).
        adopted = not pid_alive(record.owner_pid)
        endpoint = RuntimeEndpoint(
            host=DEFAULT_RPC_HOST, port=record.port, secret=record.secret,
            conf_path=ARIA2_LAYOUT.conf_path, binary_path=ARIA2_LAYOUT.binary_path,
            pid=record.pid, role=ROLE_OWNER if adopted else ROLE_CLIENT,
        )
        if adopted:
            with exclusive_instance_lock():
                write_instance(replace(record, owner_pid=os.getpid()))
            logger.info(f"[CgsAria2] adopted ownerless aria2 port={endpoint.port} pid={endpoint.pid}")
        else:
            logger.info(f"[CgsAria2] attached to running aria2 port={endpoint.port} pid={endpoint.pid}")
        return endpoint

    def _endpoint_from_env(self) -> RuntimeEndpoint | None:
        """Children spawned by the owner attach through env instead of spawning."""
        raw_endpoint = os.environ.get(ENV_ENDPOINT)
        if not raw_endpoint:
            return None
        host, _, port_text = str(raw_endpoint).rpartition(":")
        if not host or not port_text.isdigit():
            raise RuntimeError(f"{ENV_ENDPOINT} must be host:port, got {raw_endpoint!r}")
        endpoint = RuntimeEndpoint(
            host=host, port=int(port_text), secret=str(os.environ.get(ENV_SECRET) or ""),
            conf_path=ARIA2_LAYOUT.conf_path, binary_path=ARIA2_LAYOUT.binary_path,
            pid=None, role=ROLE_CLIENT,
        )
        if rpc_ping(endpoint.host, endpoint.port, endpoint.secret):
            return endpoint
        if os.environ.get(ENV_NO_SPAWN):
            raise RuntimeError(f"aria2 endpoint {endpoint.jsonrpc_url} unreachable while {ENV_NO_SPAWN} is set")
        return None

    def _spawn_owned(self, proxy: str, dns: str, progress_callback) -> RuntimeEndpoint:
        binary = ensure_aira2_binary(progress_callback=progress_callback)
        startup_deadline = time.monotonic() + ENSURE_TIMEOUT_S
        _emit_engine_progress(progress_callback, "aria2 starting...")
        work_dir = ARIA2_LAYOUT.work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        conf_path = ARIA2_LAYOUT.conf_path
        session_path = ARIA2_LAYOUT.session_path
        if not session_path.exists():
            session_path.write_text("", encoding="utf-8")

        port = get_rpc_port() if singleton_enabled() else pick_free_port()
        secret = ensure_secret()
        if port_answering(DEFAULT_RPC_HOST, port) and not rpc_ping(DEFAULT_RPC_HOST, port, secret):
            raise RuntimeError(
                f"aria2 RPC port {port} is occupied by a foreign process; "
                f"stop it or set cgs_aria2.rpc_port in the script conf"
            )

        last_error: Exception | None = None
        for _attempt in range(2):
            if time.monotonic() >= startup_deadline:
                last_error = RuntimeError("aria2 startup deadline elapsed before process launch")
                break
            options = build_aria2_option_map(rpc_port=port, proxy=proxy, dns_server=dns, secret=secret, session_path=session_path)
            # input-file only when session non-empty to avoid aria2 start noise
            if session_path.stat().st_size == 0:
                options.pop("input-file", None)
            write_aria2_conf(conf_path, options)
            try:
                popen_kwargs: dict = {
                    "cwd": str(work_dir),
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                    "stdin": subprocess.DEVNULL,
                }
                if sys.platform == "win32":
                    popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                process = subprocess.Popen([str(binary), f"--conf-path={conf_path}"], **popen_kwargs)
            except OSError as exc:
                last_error = exc
                logger.warning(f"[CgsAria2] spawn failed binary={binary}: {exc}")
                continue

            endpoint = RuntimeEndpoint(
                host=DEFAULT_RPC_HOST, port=port, secret=secret, conf_path=conf_path,
                binary_path=binary, pid=process.pid, role=ROLE_OWNER,
            )
            if self._wait_rpc_ready(endpoint, process, deadline=startup_deadline):
                self._process = process
                self._endpoint = endpoint
                ARIA2_LAYOUT.pid_path.write_text(str(process.pid), encoding="utf-8")
                write_heartbeat(os.getpid())
                instance = InstanceRecord(port=port, secret=secret, pid=process.pid, owner_pid=os.getpid(), started_at=time.time())
                with exclusive_instance_lock():
                    write_instance(instance)
                _emit_engine_progress(progress_callback, "aria2 ready")
                logger.info(f"[CgsAria2] ensure ready port={port} pid={process.pid} role=owner binary={binary}")
                return endpoint
            exit_code = process.poll()
            remaining_timeout = max(0.0, startup_deadline - time.monotonic())
            self._terminate_process(process, timeout_s=remaining_timeout)
            if exit_code is not None:
                last_error = RuntimeError(f"aria2 exited before RPC ready on port {port} (exit={exit_code}); binary={binary}")
            else:
                last_error = RuntimeError(f"aria2 RPC not ready on port {port}; binary={binary}")
            logger.warning(f"[CgsAria2] {last_error}")

        message = "CGS aria2 engine failed to start"
        if last_error is not None:
            message = f"{message}: {last_error}"
        raise RuntimeError(message)

    def stop(self) -> None:
        """Owner-facing stop: graceful handoff-or-shutdown, not a bare terminate."""
        self.release_at_exit()

    def restart(self, **kwargs) -> RuntimeEndpoint:
        return self.ensure(force_restart=True, **kwargs)

    def create_rpc_client(self, *, timeout: float = 15.0) -> Aria2RpcClient:
        endpoint = self.ensure()
        return Aria2RpcClient(url=endpoint.jsonrpc_url, secret=endpoint.secret, timeout=timeout)

    def _stop_locked(self) -> None:
        endpoint = self._endpoint
        if self._process is not None:
            self._terminate_process(self._process)
            self._process = None
        self._endpoint = None
        ARIA2_LAYOUT.pid_path.unlink(missing_ok=True)
        clear_heartbeat(os.getpid())
        if endpoint is not None and endpoint.role == ROLE_OWNER:
            with exclusive_instance_lock():
                clear_instance()

    def release_at_exit(self) -> None:
        """Owner exit policy: stop the daemon unless another client still lives."""
        with self._lock:
            endpoint = self._endpoint
            clear_heartbeat(os.getpid())
            if endpoint is None or endpoint.role != ROLE_OWNER:
                return
            others = live_other_clients(os.getpid())
            if others:
                with exclusive_instance_lock():
                    record = read_instance()
                    if record is not None:
                        write_instance(replace(record, owner_pid=None))
                logger.info(f"[CgsAria2] owner exiting, engine handed to pids={others}")
                self._endpoint = None
                return
            if not rpc_shutdown(endpoint.host, endpoint.port, endpoint.secret):
                logger.warning(f"[CgsAria2] RPC shutdown failed port={endpoint.port}; terminating process")
            if self._process is not None:
                self._terminate_process(self._process)
                self._process = None
            self._endpoint = None
            ARIA2_LAYOUT.pid_path.unlink(missing_ok=True)
            with exclusive_instance_lock():
                clear_instance()
            logger.info(f"[CgsAria2] owner exit stopped aria2 port={endpoint.port}")

    def _process_alive(self) -> bool:
        process = self._process
        if process is None:
            return False
        return process.poll() is None

    def _wait_rpc_ready(self, endpoint: RuntimeEndpoint, process: subprocess.Popen, *, deadline: float | None = None) -> bool:
        startup_deadline = deadline if deadline is not None else time.monotonic() + ENSURE_TIMEOUT_S
        while time.monotonic() < startup_deadline:
            if process.poll() is not None:
                return False
            remaining_timeout = startup_deadline - time.monotonic()
            if ping_endpoint_sync(endpoint, timeout_s=min(STARTUP_PING_TIMEOUT_S, max(0.01, remaining_timeout))):
                return True
            remaining_timeout = startup_deadline - time.monotonic()
            if remaining_timeout > 0:
                time.sleep(min(PING_INTERVAL_S, remaining_timeout))
        return False

    @staticmethod
    def _rpc_ping_sync(endpoint: RuntimeEndpoint) -> bool:
        """Sync JSON-RPC ping. Must NOT use asyncio.run (nested loop in GUI preprocess)."""
        return ping_endpoint_sync(endpoint)

    @staticmethod
    def _terminate_process(process: subprocess.Popen, *, timeout_s: float = 3.0) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=max(0.0, timeout_s))
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def _emit_engine_progress(progress_callback, message: str) -> None:
    """Advance AsyncTask tooltip after binary download (download_finish freezes otherwise)."""
    if progress_callback is None:
        return
    if callable(progress_callback):
        progress_callback(message)


def normalize_proxy_arg(proxy: object | None) -> str:
    # No fallback to script httpx proxies: this field is the download engine's own proxy,
    # empty means direct.
    if proxy is None:
        return get_proxy()
    from utils.script.aria2.conf import normalize_proxy

    return normalize_proxy(proxy)


def resolve_dns_server(dns_server: object | None) -> str:
    if dns_server is not None:
        return str(dns_server or "").strip()
    return dns_stub_server(cgs_cfg.doh.get_url())


def pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def resolve_aria2_binary(*, progress_callback=None) -> p.Path:
    """Return the managed aria2c at conf_dir/cgs-aria2/bin (preset download only)."""
    return ensure_aira2_binary(progress_callback=progress_callback)


def ping_endpoint_sync(endpoint: RuntimeEndpoint, *, timeout_s: float = 2.0) -> bool:
    """Blocking aria2.getVersion over HTTP. Safe from sync and async GUI threads."""
    return rpc_ping(endpoint.host, endpoint.port, endpoint.secret, timeout_s=timeout_s)


_ENGINE = CgsAria2Engine()


def get_engine() -> CgsAria2Engine:
    return _ENGINE


def ensure_engine(**kwargs) -> RuntimeEndpoint:
    return get_engine().ensure(**kwargs)


def stop_engine() -> None:
    get_engine().stop()


def create_managed_rpc_client(*, timeout: float = 15.0) -> Aria2RpcClient:
    return get_engine().create_rpc_client(timeout=timeout)


def child_endpoint_env() -> dict[str, str]:
    """Env for spawned children so they attach to the running engine.

    Empty when no engine is up yet — the child then falls back to normal
    discovery and may become the owner itself (CLI mode).
    """
    endpoint = get_engine().endpoint
    if endpoint is None:
        return {}
    return {
        ENV_ENDPOINT: f"{endpoint.host}:{endpoint.port}",
        ENV_SECRET: endpoint.secret,
        ENV_NO_SPAWN: "1",
    }


# Normal interpreter exit stops/hands off the engine. A hard kill has no hook —
# plan B (design D4) adopts or clears the orphan on the next ensure.
atexit.register(get_engine().release_at_exit)
