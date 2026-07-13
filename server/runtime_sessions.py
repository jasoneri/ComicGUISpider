from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping
from uuid import uuid4

from utils.middleware.presets.auto_select_inverse import AutoSelectLatest
from server.errors import ServerRuntimeError
from variables import SPIDERS, Spider


@dataclass(slots=True)
class SearchSession:
    site_index: int
    created_at: float
    books: dict[str, object] = field(default_factory=dict)
    episodes: dict[str, list[object]] = field(default_factory=dict)
    episode_keys: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EpisodeSelect:
    mode: str = "first"
    num: int = 1


@dataclass(frozen=True, slots=True)
class EpisodeSelection:
    book_key: str
    episode_keys: tuple[str, ...]


class ServerSessionCatalog:
    def __init__(self, *, ttl_seconds: int = 900, clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = int(ttl_seconds)
        self.clock = clock
        self._sessions: dict[str, SearchSession] = {}

    def __len__(self) -> int:
        return len(self._sessions)

    def clear(self) -> None:
        self._sessions.clear()

    def supported_sites_payload(self) -> list[dict]:
        return [
            {"site_index": int(site), "spider_name": SPIDERS[int(site)]}
            for site in sorted(self.supported_direct_sites(), key=int)
            if int(site) in SPIDERS
        ]

    def create_search_session(self, site_index: int, books: list) -> tuple[str, SearchSession, list[tuple[object, str]]]:
        session_id = uuid4().hex
        session = SearchSession(site_index=site_index, created_at=self.clock())
        book_rows = []
        for fallback_idx, book in enumerate(books, start=1):
            if getattr(book, "idx", None) is None:
                book.idx = fallback_idx
            book_key = self.book_key(book, fallback_idx)
            session.books[book_key] = book
            book_rows.append((book, book_key))
        return session_id, session, book_rows

    def store(self, session_id: str, session: SearchSession) -> None:
        self._sessions[session_id] = session
        self.cleanup()

    def get(self, session_id: str) -> SearchSession:
        self.cleanup()
        session = self._sessions.get(str(session_id or ""))
        if session is None:
            raise ServerRuntimeError("missing_session", f"missing session: {session_id}")
        return session

    def cleanup(self) -> None:
        if self.ttl_seconds <= 0:
            return
        deadline = self.clock() - self.ttl_seconds
        for sid in [sid for sid, session in self._sessions.items() if session.created_at < deadline]:
            self._sessions.pop(sid, None)

    def supported_direct_sites(self):
        return Spider.specials() | Spider.mangas()

    def require_direct_site(self, site_index: int) -> int:
        try:
            normalized = int(site_index)
        except (TypeError, ValueError) as exc:
            raise ServerRuntimeError("unsupported_site", f"unsupported site: {site_index}") from exc
        if normalized not in SPIDERS or Spider(normalized) not in self.supported_direct_sites():
            raise ServerRuntimeError("unsupported_site", f"unsupported site: {site_index}")
        return normalized

    def is_episode_card(self, book) -> bool:
        source = getattr(book, "source", None)
        if not source:
            return bool(getattr(book, "episodes", None) or "青年漫" in (getattr(book, "btype", None) or ""))
        manga_sources = {spider.spider_name for spider in Spider.mangas()}
        if source in manga_sources:
            return True
        if source == "jm":
            return bool(getattr(book, "episodes", None) or "青年漫" in (getattr(book, "btype", None) or ""))
        return False

    def is_episode_item(self, item) -> bool:
        return hasattr(item, "from_book")

    def book_select_mode(self, book) -> str:
        return "chapters" if self.is_episode_card(book) else "book"

    def cache_episodes(self, session: SearchSession, book_key: str, book, episodes: list) -> None:
        episode_list = list(episodes)
        session.episodes[book_key] = episode_list
        key_map = {}
        for order_index, episode in enumerate(episode_list, start=1):
            if getattr(episode, "from_book", None) is None:
                episode.from_book = book
            key_map[self.episode_key(book_key, episode, order_index)] = episode
        session.episode_keys[book_key] = key_map

    def episode_key(self, book_key: str, episode, fallback_idx: int) -> str:
        seed = "|".join(
            str(part or "")
            for part in (
                f"book:{book_key}",
                f"row:{fallback_idx}",
                getattr(episode, "id", None),
                getattr(episode, "idx", None) or fallback_idx,
                getattr(episode, "url", None),
                getattr(episode, "name", None),
            )
        )
        return hashlib.md5(seed.encode("utf-8")).hexdigest()

    def episode_dto(self, episode, episode_key: str) -> dict:
        return {
            "episode_key": str(episode_key),
            "idx": self.json_value(getattr(episode, "idx", None)),
            "name": self.json_value(getattr(episode, "name", None)) or "",
            "downloaded": bool(getattr(episode, "downloaded", False)),
        }

    def normalize_episode_selections(self, value) -> list[EpisodeSelection]:
        if value is None:
            return []
        if hasattr(value, "model_dump"):
            value = value.model_dump(exclude_none=True)
        if not isinstance(value, list):
            raise ServerRuntimeError("invalid_episode_selection", "episode_selections must be a list")
        selections = []
        for item in value:
            if hasattr(item, "model_dump"):
                item = item.model_dump(exclude_none=True)
            if not isinstance(item, Mapping):
                raise ServerRuntimeError("invalid_episode_selection", "episode selection must be an object")
            book_key = str(item.get("book_key") or "").strip()
            episode_keys = item.get("episode_keys")
            if not book_key:
                raise ServerRuntimeError("invalid_episode_selection", "episode selection book_key is required")
            if not isinstance(episode_keys, list) or not episode_keys:
                raise ServerRuntimeError("invalid_episode_selection", "episode selection episode_keys must not be empty")
            selections.append(EpisodeSelection(book_key=book_key, episode_keys=tuple(str(key) for key in episode_keys if str(key or ""))))
        if any(not selection.episode_keys for selection in selections):
            raise ServerRuntimeError("invalid_episode_selection", "episode selection episode_keys must not be empty")
        return selections

    def selected_episodes(self, session: SearchSession, episode_selections) -> list:
        selected = []
        seen: set[str] = set()
        for selection in self.normalize_episode_selections(episode_selections):
            if selection.book_key not in session.books:
                raise ServerRuntimeError("invalid_book_key", f"invalid book key: {selection.book_key}")
            if selection.book_key not in session.episode_keys:
                raise ServerRuntimeError("episodes_not_loaded", f"episodes are not loaded for book: {selection.book_key}")
            episode_map = session.episode_keys[selection.book_key]
            for episode_key in selection.episode_keys:
                if episode_key not in episode_map:
                    raise ServerRuntimeError("invalid_episode_key", f"invalid episode key: {episode_key}")
                if episode_key in seen:
                    continue
                seen.add(episode_key)
                selected.append(episode_map[episode_key])
        return selected

    def normalize_episode_select(self, value) -> EpisodeSelect:
        if value is None:
            return EpisodeSelect()
        if isinstance(value, EpisodeSelect):
            return value
        if hasattr(value, "model_dump"):
            value = value.model_dump(exclude_none=True)
        if not isinstance(value, Mapping):
            raise ServerRuntimeError("invalid_episode_select", "episode_select must be an object")
        mode = str(value.get("mode") or "first").strip().lower()
        if mode not in {"latest", "first", "all"}:
            raise ServerRuntimeError("invalid_episode_select", "episode_select.mode must be one of: latest, first, all")
        return EpisodeSelect(mode=mode, num=AutoSelectLatest._to_num(value.get("num", 1)))

    def select_manga_episodes(self, episodes: list, episode_select: EpisodeSelect) -> list:
        source = list(episodes)
        if episode_select.mode == "all":
            return source
        if episode_select.mode == "latest":
            return AutoSelectLatest.select_episodes(source, episode_select.num)
        return source[:episode_select.num]

    def json_value(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def json_list(self, value):
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [self.json_value(item) for item in value]
        return [self.json_value(value)]

    def book_dto(self, book, book_key: str) -> dict:
        select_mode = self.book_select_mode(book)
        return {
            "book_key": str(book_key),
            "select_mode": select_mode,
            "idx": self.json_value(getattr(book, "idx", None)),
            "source": self.json_value(getattr(book, "source", None)),
            "name": self.json_value(getattr(book, "name", None)),
            "artist": self.json_value(getattr(book, "artist", None)),
            "public_date": self.json_value(getattr(book, "public_date", None)),
            "pages": self.json_value(getattr(book, "pages", None)),
            "btype": self.json_value(getattr(book, "btype", None)),
            "tags": self.json_list(getattr(book, "tags", None)),
            "url": self.json_value(getattr(book, "url", None)),
            "preview_url": self.json_value(getattr(book, "preview_url", None)),
            "img_preview": self.json_value(getattr(book, "img_preview", None)),
            "cover_static_url": self.json_value(getattr(book, "cover_static_url", None)),
            "cover_url": self.json_value(getattr(book, "cover_static_url", None)),
            "cover_error": self.json_value(getattr(book, "cover_error", None)),
            "supported": True,
            "unsupported_reason": None,
        }

    def book_key(self, book, fallback_idx: int) -> str:
        seed = "|".join(
            str(part or "")
            for part in (
                f"row:{fallback_idx}",
                getattr(book, "source", None),
                getattr(book, "id", None),
                getattr(book, "idx", None) or fallback_idx,
                getattr(book, "url", None),
                getattr(book, "preview_url", None),
                getattr(book, "name", None),
            )
        )
        return hashlib.md5(seed.encode("utf-8")).hexdigest()
