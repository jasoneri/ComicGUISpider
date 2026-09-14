from __future__ import annotations

import json
import pathlib as p
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from loguru import logger

from utils.config.qc import cgs_cfg
from utils.network.doh import dns_stub_server
from utils.script.aria2.bootstrap import ensure_aira2_binary, resolve_aria2_layout
from utils.script.aria2.conf import build_aria2_option_map, write_aria2_conf
from utils.script.aria2.rpc import Aria2RpcClient
from utils.script.aria2.settings import ensure_motrix_proxy_seed, get_proxy

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


@dataclass(frozen=True, slots=True)
class RuntimeEndpoint:
    host: str
    port: int
    secret: str
    conf_path: p.Path
    binary_path: p.Path
    pid: int | None

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
            return self._endpoint is not None and self._process_alive() and self._rpc_ping_sync(self._endpoint)

    def ensure(
        self,
        *,
        proxy: object | None = None,
        dns_server: object | None = None,
        force_restart: bool = False,
        progress_callback=None,
    ) -> RuntimeEndpoint:
        with self._lock:
            ensure_motrix_proxy_seed()
            resolved_proxy = normalize_proxy_arg(proxy)
            dns = resolve_dns_server(dns_server)
            if not force_restart and self._endpoint is not None and self._process_alive() and self._rpc_ping_sync(self._endpoint):
                return self._endpoint
            self._stop_locked()
            binary = ensure_aira2_binary(progress_callback=progress_callback)
            startup_deadline = time.monotonic() + ENSURE_TIMEOUT_S
            _emit_engine_progress(progress_callback, "aria2 starting...")
            work_dir = ARIA2_LAYOUT.work_dir
            work_dir.mkdir(parents=True, exist_ok=True)
            conf_path = ARIA2_LAYOUT.conf_path
            session_path = ARIA2_LAYOUT.session_path
            if not session_path.exists():
                session_path.write_text("", encoding="utf-8")

            last_error: Exception | None = None
            for _attempt in range(2):
                if time.monotonic() >= startup_deadline:
                    last_error = RuntimeError("aria2 startup deadline elapsed before process launch")
                    break
                port = pick_free_port()
                options = build_aria2_option_map(
                    rpc_port=port,
                    proxy=resolved_proxy,
                    dns_server=dns,
                    session_path=session_path,
                )
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
                    process = subprocess.Popen(
                        [str(binary), f"--conf-path={conf_path}"],
                        **popen_kwargs,
                    )
                except OSError as exc:
                    last_error = exc
                    logger.warning(f"[CgsAria2] spawn failed binary={binary}: {exc}")
                    continue

                endpoint = RuntimeEndpoint(
                    host="127.0.0.1",
                    port=port,
                    secret="",
                    conf_path=conf_path,
                    binary_path=binary,
                    pid=process.pid,
                )
                if self._wait_rpc_ready(endpoint, process, deadline=startup_deadline):
                    self._process = process
                    self._endpoint = endpoint
                    ARIA2_LAYOUT.pid_path.write_text(str(process.pid), encoding="utf-8")
                    _emit_engine_progress(progress_callback, "aria2 ready")
                    logger.info(f"[CgsAria2] ensure ready port={port} pid={process.pid} binary={binary}")
                    return endpoint
                exit_code = process.poll()
                remaining_timeout = max(0.0, startup_deadline - time.monotonic())
                self._terminate_process(process, timeout_s=remaining_timeout)
                if exit_code is not None:
                    last_error = RuntimeError(
                        f"aria2 exited before RPC ready on port {port} (exit={exit_code}); "
                        f"conf={conf_path} binary={binary}"
                    )
                else:
                    last_error = RuntimeError(
                        f"aria2 RPC not ready on port {port}; conf={conf_path} binary={binary}"
                    )
                logger.warning(f"[CgsAria2] {last_error}")

            message = "CGS aria2 engine failed to start"
            if last_error is not None:
                message = f"{message}: {last_error}"
            raise RuntimeError(message)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def restart(self, **kwargs) -> RuntimeEndpoint:
        return self.ensure(force_restart=True, **kwargs)

    def create_rpc_client(self, *, timeout: float = 15.0) -> Aria2RpcClient:
        endpoint = self.ensure()
        return Aria2RpcClient(url=endpoint.jsonrpc_url, secret=endpoint.secret, timeout=timeout)

    def _stop_locked(self) -> None:
        if self._process is not None:
            self._terminate_process(self._process)
            self._process = None
        self._endpoint = None
        pid_path = ARIA2_LAYOUT.pid_path
        pid_path.unlink(missing_ok=True)

    def _process_alive(self) -> bool:
        process = self._process
        if process is None:
            return False
        return process.poll() is None

    def _wait_rpc_ready(
        self,
        endpoint: RuntimeEndpoint,
        process: subprocess.Popen,
        *,
        deadline: float | None = None,
    ) -> bool:
        startup_deadline = deadline if deadline is not None else time.monotonic() + ENSURE_TIMEOUT_S
        while time.monotonic() < startup_deadline:
            if process.poll() is not None:
                return False
            remaining_timeout = startup_deadline - time.monotonic()
            if ping_endpoint_sync(
                endpoint,
                timeout_s=min(STARTUP_PING_TIMEOUT_S, max(0.01, remaining_timeout)),
            ):
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
    payload = {
        "jsonrpc": "2.0",
        "method": "aria2.getVersion",
        "params": [],
        "id": "cgs-aria2-ping",
    }
    if endpoint.secret:
        payload["params"] = [f"token:{endpoint.secret}"]
    request = urllib.request.Request(
        endpoint.jsonrpc_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ComicGUISpider-cgs-aria2",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            return False
        if body.get("error"):
            return False
        result = body.get("result")
        return isinstance(result, dict) and bool(result)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return False


_ENGINE = CgsAria2Engine()


def get_engine() -> CgsAria2Engine:
    return _ENGINE


def ensure_engine(**kwargs) -> RuntimeEndpoint:
    return get_engine().ensure(**kwargs)


def stop_engine() -> None:
    get_engine().stop()


def create_managed_rpc_client(*, timeout: float = 15.0) -> Aria2RpcClient:
    return get_engine().create_rpc_client(timeout=timeout)
