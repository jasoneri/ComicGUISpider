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

from utils.config import conf_dir
from utils.config.qc import cgs_cfg
from utils.network.doh import dns_stub_server
from utils.script.aria2.bootstrap import ensure_aira2_binary
from utils.script.aria2.conf import build_aria2_option_map, write_aria2_conf
from utils.script.aria2.rpc import Aria2RpcClient
from utils.script.aria2.settings import ensure_motrix_proxy_seed, get_proxy

ARIA2_WORK_DIR = conf_dir.joinpath("cgs-aria2")
ARIA2_CONF_NAME = "aria2.conf"
ARIA2_SESSION_NAME = "download.session"
ARIA2_PID_NAME = "engine.pid"
ENSURE_TIMEOUT_S = 12.0
PING_INTERVAL_S = 0.2


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
            work_dir = ARIA2_WORK_DIR
            work_dir.mkdir(parents=True, exist_ok=True)
            conf_path = work_dir / ARIA2_CONF_NAME
            session_path = work_dir / ARIA2_SESSION_NAME
            if not session_path.exists():
                session_path.write_text("", encoding="utf-8")

            last_error: Exception | None = None
            for _attempt in range(2):
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
                if self._wait_rpc_ready(endpoint, process):
                    self._process = process
                    self._endpoint = endpoint
                    (work_dir / ARIA2_PID_NAME).write_text(str(process.pid), encoding="utf-8")
                    logger.info(f"[CgsAria2] ensure ready port={port} pid={process.pid} binary={binary}")
                    return endpoint
                exit_code = process.poll()
                self._terminate_process(process)
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
        pid_path = ARIA2_WORK_DIR / ARIA2_PID_NAME
        if pid_path.exists():
            try:
                pid_path.unlink()
            except OSError:
                pass

    def _process_alive(self) -> bool:
        process = self._process
        if process is None:
            return False
        return process.poll() is None

    def _wait_rpc_ready(self, endpoint: RuntimeEndpoint, process: subprocess.Popen) -> bool:
        deadline = time.monotonic() + ENSURE_TIMEOUT_S
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            if self._rpc_ping_sync(endpoint):
                return True
            time.sleep(PING_INTERVAL_S)
        return False

    @staticmethod
    def _rpc_ping_sync(endpoint: RuntimeEndpoint) -> bool:
        """Sync JSON-RPC ping. Must NOT use asyncio.run (nested loop in GUI preprocess)."""
        return ping_endpoint_sync(endpoint)

    @staticmethod
    def _terminate_process(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


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
    """Resolve managed binary only via preset → temp_p/aira2 (no PATH/uv/runtime fallback)."""
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
