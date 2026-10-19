from __future__ import annotations

import threading
import time
import pickle
import contextlib
import typing as t
import pathlib as p


import httpx

from assets import res
from utils import get_httpx_verify
from utils.script import conf as script_conf
from utils.website.core import build_proxy_transport
from utils.website.pawchive import domain, headers


class AvatarCache:
    def __init__(self, cache_path: p.Path, ttl_days: int = 30, *, accept=None):
        self.cache_path = cache_path
        self.ttl_seconds = ttl_days * 86400
        self._data: t.Dict[str, t.Dict[str, t.Any]] = {}
        self._dirty = False
        # Format gate: old entries written by a previous encoder are dropped on load
        # instead of living next to the current format forever.
        self._accept = accept

    def load(self):
        if not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "rb") as f:
                loaded = pickle.load(f)
            if isinstance(loaded, dict):
                self._data = loaded
                self._cleanup_expired()
                self._drop_rejected()
        except Exception:
            self._data = {}

    def get(self, key: str) -> t.Optional[bytes]:
        item = self._data.get(key)
        if not isinstance(item, dict):
            return None
        ts = item.get("ts")
        payload = item.get("bytes")
        if not isinstance(ts, (int, float)) or not isinstance(payload, (bytes, bytearray)):
            return None
        if self.ttl_seconds > 0 and (int(time.time()) - ts > self.ttl_seconds):
            self._data.pop(key, None)
            self._dirty = True
            return None
        return bytes(payload)

    def set(self, key: str, payload: bytes):
        if not payload:
            return
        self._data[key] = {"bytes": bytes(payload), "ts": int(time.time())}
        self._dirty = True

    def save(self):
        if not self._dirty:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            with open(self.cache_path, "wb") as f:
                pickle.dump(self._data, f, protocol=pickle.HIGHEST_PROTOCOL)
            self._dirty = False

    def _drop_rejected(self):
        if self._accept is None or not self._data:
            return
        rejected = [
            k for k, v in self._data.items()
            if not isinstance(v, dict) or not self._accept(bytes(v.get("bytes") or b""))
        ]
        for k in rejected:
            self._data.pop(k, None)
        if rejected:
            self._dirty = True

    def _cleanup_expired(self):
        if self.ttl_seconds <= 0 or not self._data:
            return
        now = int(time.time())
        expired = [
            k for k, v in self._data.items()
            if not isinstance(v, dict)
            or not isinstance(v.get("ts"), (int, float))
            or now - int(v.get("ts", 0)) > self.ttl_seconds
        ]
        for k in expired:
            self._data.pop(k, None)
        if expired:
            self._dirty = True


AVATAR_SIZE = 32
_JPEG_SOI = b"\xff\xd8\xff"


def is_jpeg(data: object) -> bool:
    payload = bytes(data or b"")
    return payload[:3] == _JPEG_SOI


def to_avatar_jpeg(raw: bytes, size: int = AVATAR_SIZE) -> bytes:
    """非图片 / 编码失败一律返回空 bytes，由调用方按失败处理，不留空白占位。"""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QPixmap
    pixmap = QPixmap()
    if not raw or not pixmap.loadFromData(raw):
        return b""
    scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    payload = QByteArray()
    buf = QBuffer(payload)
    if not buf.open(QIODevice.WriteOnly):
        return b""
    written = scaled.save(buf, "JPG")
    buf.close()
    return bytes(payload) if written else b""


MAX_CONNECTIONS = 12
TIMEOUT = 15
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
MAX_AVATAR_BYTES = 2 * 1024 * 1024
# 429/5xx 值得重试；其余 4xx（如头像不存在的 404）重试也不会成功
_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_client_lock = threading.Lock()
_client: httpx.Client | None = None


def avatar_headers() -> dict[str, str]:
    return {
        **headers,
        "accept": "application/json",
        "accept-language": res.Vars.ua_accept_language,
        "referer": f"https://{domain}",
    }


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                transport, trust_env = build_proxy_transport(
                    "proxy",
                    getattr(script_conf, "proxies", None) or [],
                    is_async=False,
                    retries=2,
                    verify=get_httpx_verify(),
                    http2=True,
                )
                _client = httpx.Client(
                    transport=transport,
                    trust_env=trust_env,
                    headers=avatar_headers(),
                    follow_redirects=True,
                    timeout=TIMEOUT,
                    limits=httpx.Limits(
                        max_connections=MAX_CONNECTIONS,
                        max_keepalive_connections=MAX_CONNECTIONS,
                    ),
                )
    return _client


def fetch_avatar_bytes(url: str) -> bytes:
    """下载头像原始字节；瞬时网络错误按退避重试，非瞬时错误（4xx 等）立即抛出。"""
    last_error: Exception = RuntimeError("avatar download did not run")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt - 1))
        try:
            resp = get_client().get(url)
            if resp.status_code in _TRANSIENT_STATUS_CODES:
                last_error = httpx.HTTPStatusError(
                    message=f"transient status {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                continue
            resp.raise_for_status()
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > MAX_AVATAR_BYTES:
                raise ValueError("invalid_avatar_response")
            data = resp.content
            if not data or len(data) > MAX_AVATAR_BYTES:
                raise ValueError("invalid_avatar_response")
            return data
        except httpx.TransportError as exc:  # ConnectError(10054)/超时等瞬时错误
            last_error = exc
    raise last_error


def close_client() -> None:
    global _client
    with _client_lock:
        if _client is None:
            return
        _client.close()
        _client = None
