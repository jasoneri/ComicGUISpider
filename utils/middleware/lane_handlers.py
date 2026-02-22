# -*- coding: utf-8 -*-
from __future__ import annotations

from utils.middleware.executor import Action
from utils.middleware.timeline import LaneStage
from utils.middleware.lane_router import BaseLaneHandler


class SiteLaneHandler(BaseLaneHandler):
    lane = LaneStage.SITE
    supported_kinds = {"send_input_state", "site_select"}

    def _resolve_site_index(self, action: Action) -> int:
        st = self._get_input_state(action)
        raw = self._coalesce(action.payload.get("site_index"), getattr(st, "bookSelected", None))
        return self._require_int(raw, "site_index", min_value=0)

    def handle(self, action: Action, ops) -> None:
        ops.select_site(self._resolve_site_index(action))


class SearchLaneHandler(BaseLaneHandler):
    lane = LaneStage.SEARCH
    supported_kinds = {"send_input_state", "search_submit"}

    def _resolve_submit_args(self, action: Action) -> tuple[str, int]:
        st = self._get_input_state(action)
        raw_keyword = self._coalesce(action.payload.get("keyword"), getattr(st, "keyword", None))
        keyword = self._require_str(raw_keyword, "keyword")
        raw_site = self._coalesce(action.payload.get("site_index"), getattr(st, "bookSelected", None))
        site_index = self._require_int(raw_site, "site_index", min_value=0)
        return keyword, site_index

    def handle(self, action: Action, ops) -> None:
        keyword, site_index = self._resolve_submit_args(action)
        ops.submit_search(keyword, site_index)


class BookLaneHandler(BaseLaneHandler):
    lane = LaneStage.BOOK
    supported_kinds = {"send_input_state", "book_select"}

    def _resolve_decision(self, action: Action):
        st = self._get_input_state(action)
        raw_indexes = self._coalesce(action.payload.get("indexes"), getattr(st, "indexes", None))
        indexes = self._ensure_book_list(raw_indexes)
        page_turn = self._coalesce(action.payload.get("page_turn"), getattr(st, "pageTurn", ""))
        if page_turn is None:
            page_turn = ""
        return indexes, page_turn

    def handle(self, action: Action, ops) -> None:
        indexes, page_turn = self._resolve_decision(action)
        ops.select_books(indexes, page_turn)


class EpLaneHandler(BaseLaneHandler):
    lane = LaneStage.EP
    supported_kinds = {"send_input_state", "ep_select"}

    @staticmethod
    def _book_episodes(item):
        episodes = getattr(item, "episodes", None)
        if not episodes:
            return None
        return list(episodes)

    @classmethod
    def _flatten_book_episodes(cls, items) -> list:
        flattened = []
        for item in items:
            episodes = cls._book_episodes(item)
            if not episodes:
                continue
            flattened.extend(episodes)
        return flattened

    def _resolve_eps(self, indexes):
        if self._is_episode_like(indexes):
            return [indexes]
        if episodes := self._book_episodes(indexes):
            return episodes
        if not isinstance(indexes, list) or not indexes:
            return None
        if all(self._is_episode_like(item) for item in indexes):
            return indexes
        if flattened := self._flatten_book_episodes(indexes):
            return flattened
        return indexes

    def _resolve_decision(self, action: Action):
        st = self._get_input_state(action)
        raw_indexes = self._coalesce(action.payload.get("indexes"), getattr(st, "indexes", None))
        eps = self._resolve_eps(raw_indexes)
        return self._ensure_episode_list(eps)

    def handle(self, action: Action, ops) -> None:
        ops.select_eps(self._resolve_decision(action))


class PostprocessingHandler(BaseLaneHandler):
    lane = LaneStage.POSTPROCESSING
    supported_kinds = {"postprocess_cbz"}

    def handle(self, action: Action, ops) -> None:
        ops.run_postprocess(**action.payload)


DEFAULT_LANE_HANDLERS = [
    SiteLaneHandler,
    SearchLaneHandler,
    BookLaneHandler,
    EpLaneHandler,
    PostprocessingHandler,
]
