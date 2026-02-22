# -*- coding: utf-8 -*-
from __future__ import annotations

from utils.middleware.executor import Action
from utils.middleware.timeline import LaneStage


class LanePayloadError(ValueError):
    pass


class BaseLaneHandler:
    lane: LaneStage
    supported_kinds: set[str] = set()

    def can_handle(self, action: Action) -> bool:
        return action.lane == self.lane.value and action.kind in self.supported_kinds

    def handle(self, action: Action, ops) -> None:
        raise NotImplementedError

    @staticmethod
    def _get_input_state(action: Action):
        return action.payload.get("input_state")

    @staticmethod
    def _raise_payload_error(message: str):
        raise LanePayloadError(message)

    @staticmethod
    def _coalesce(*values):
        for value in values:
            if value is not None:
                return value
        return None

    @classmethod
    def _require_int(cls, value, field: str, *, min_value: int = 0) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            cls._raise_payload_error(f"{field} must be int, got {type(value).__name__}")
        if parsed < min_value:
            cls._raise_payload_error(f"{field} must be >= {min_value}, got {parsed}")
        return parsed

    @classmethod
    def _require_str(cls, value, field: str, *, allow_empty: bool = False) -> str:
        if not isinstance(value, str):
            cls._raise_payload_error(f"{field} must be str, got {type(value).__name__}")
        text = value.strip()
        if not allow_empty and not text:
            cls._raise_payload_error(f"{field} must not be empty")
        return text

    @staticmethod
    def _is_episode_like(item) -> bool:
        from_book = getattr(item, "from_book", None)
        return from_book is not None

    @classmethod
    def _normalize_list(cls, value, field: str) -> list:
        if value is None:
            cls._raise_payload_error(f"{field} is required")
        if isinstance(value, list):
            items = value
        else:
            items = [value]
        if not items:
            cls._raise_payload_error(f"{field} must be a non-empty list")
        return items

    @classmethod
    def _ensure_typed_list(cls, items, field: str, validator, err_template: str):
        items = cls._normalize_list(items, field)
        invalid = [item for item in items if not validator(item)]
        if invalid:
            got = ", ".join(type(item).__name__ for item in invalid[:3])
            cls._raise_payload_error(err_template.format(got=got))
        return items

    def _ensure_episode_list(self, episodes, field: str = "indexes"):
        return self._ensure_typed_list(
            episodes,
            field,
            self._is_episode_like,
            "EP lane payload type invalid: expected Episode-like items with from_book, got {got}",
        )

    def _ensure_book_list(self, books, field: str = "indexes"):
        return self._ensure_typed_list(
            books,
            field,
            lambda item: not self._is_episode_like(item),
            "BOOK lane payload type invalid: expected Book-like items, got {got}",
        )


class LaneActionRouter:
    def __init__(self):
        self._handlers: dict[str, BaseLaneHandler] = {}

    def register(self, handler: BaseLaneHandler):
        self._handlers[handler.lane.value] = handler

    def dispatch(self, action: Action, ops) -> bool:
        handler = self._handlers.get(action.lane)
        if not handler or not handler.can_handle(action):
            return False
        handler.handle(action, ops)
        return True
