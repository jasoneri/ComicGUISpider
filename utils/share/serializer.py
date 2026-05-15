from __future__ import annotations

import io
import pickle
from copy import deepcopy

from utils.website.info import (
    BookInfo,
    Ero,
    Episode,
    HComicBookInfo,
    HitomiBookInfo,
    InfoMinix,
    JmBookInfo,
    JestfulBookInfo,
    KbBookInfo,
    MangabzBookInfo,
    ManhuaguiBookInfo,
    NhentaiBookInfo,
    WnacgBookInfo,
    EhBookInfo,
)

_ALLOWED_CLASSES = {
    "builtins": {"list", "dict", "str", "int", "float", "bool", "NoneType", "set", "tuple"},
    "utils.website.info": {
        "BookInfo",
        "Ero",
        "Episode",
        "InfoMinix",
        "JmBookInfo",
        "EhBookInfo",
        "HitomiBookInfo",
        "MangabzBookInfo",
        "KbBookInfo",
        "WnacgBookInfo",
        "HComicBookInfo",
        "NhentaiBookInfo",
        "JestfulBookInfo",
        "ManhuaguiBookInfo",
    },
}
_ALLOWED_BOOK_TYPES = (
    BookInfo,
    Ero,
    JmBookInfo,
    EhBookInfo,
    HitomiBookInfo,
    MangabzBookInfo,
    KbBookInfo,
    WnacgBookInfo,
    HComicBookInfo,
    NhentaiBookInfo,
    JestfulBookInfo,
    ManhuaguiBookInfo,
)
_PAYLOAD_PREFIX = b"CGS_SHARE_V1\n"


class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module in _ALLOWED_CLASSES and name in _ALLOWED_CLASSES[module]:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Forbidden class: {module}.{name}")


def _normalize_books(books: list) -> list:
    normalized = []
    for idx, book in enumerate(list(books or []), start=1):
        if not isinstance(book, _ALLOWED_BOOK_TYPES):
            raise TypeError(f"share books must be BookInfo-compatible, got {type(book).__name__}")
        cloned = deepcopy(book)
        cloned.idx = idx
        episodes = list(getattr(cloned, "episodes", None) or [])
        for ep_idx, episode in enumerate(episodes, start=1):
            if not isinstance(episode, Episode):
                raise TypeError(f"share episodes must be Episode, got {type(episode).__name__}")
            episode.idx = ep_idx
            episode.from_book = cloned
        cloned.episodes = episodes or None
        normalized.append(cloned)
    return normalized


def serialize_books(books: list) -> bytes:
    payload_books = _normalize_books(books)
    body = pickle.dumps(payload_books, protocol=pickle.HIGHEST_PROTOCOL)
    return _PAYLOAD_PREFIX + body


def deserialize_books(payload: bytes) -> list:
    raw = bytes(payload)
    if not raw.startswith(_PAYLOAD_PREFIX):
        raise pickle.UnpicklingError("Unsupported share payload prefix")
    body = raw[len(_PAYLOAD_PREFIX):]
    result = SafeUnpickler(io.BytesIO(body)).load()
    if not isinstance(result, list):
        raise pickle.UnpicklingError(f"share payload must unpack to list, got {type(result).__name__}")
    return _normalize_books(result)
