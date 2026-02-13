import pickle
import contextlib
import time
import typing as t
import pathlib as p


class AvatarCache:

    def __init__(self, cache_path: p.Path, ttl_days: int = 30):
        self.cache_path = cache_path
        self.ttl_seconds = ttl_days * 86400
        self._data: t.Dict[str, t.Dict[str, t.Any]] = {}
        self._dirty = False

    def load(self):
        if not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "rb") as f:
                loaded = pickle.load(f)
            if isinstance(loaded, dict):
                self._data = loaded
                self._cleanup_expired()
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
        with contextlib.suppress():
            with open(self.cache_path, "wb") as f:
                pickle.dump(self._data, f, protocol=pickle.HIGHEST_PROTOCOL)
            self._dirty = False

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
