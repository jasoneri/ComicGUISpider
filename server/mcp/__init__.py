from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from starlette.applications import Starlette

from server.mcp.call_log import McpCallLog
from server.subscription import (
    add_book,
    add_follow,
    load_subscription_config,
    publish_subscription_share_card,
    remove_book,
    remove_follow,
    save_subscription_config,
    update_book,
    update_follow,
)
from server.surfaces import ServerSurface
from utils.subscription import SubscriptionStore


JSONDict = dict[str, Any]
_LOGGER = logging.getLogger(__name__)
_ARG_SUMMARY_VALUE_LIMIT = 96
_ARG_SUMMARY_LIST_LIMIT = 5
_RESPONSE_SUMMARY_KEY_LIMIT = 12
_RESPONSE_SUMMARY_VALUE_LIMIT = 512
_SENSITIVE_KEY_PARTS = ("token", "authorization", "password", "secret")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[^,\s\"'}]+")
_TOKEN_ASSIGNMENT_RE = re.compile(r"(?i)\btoken\b\s*[:=]\s*[^,\s\"'}]+")
_TOKEN_WORD_RE = re.compile(r"(?i)token")


class EpisodeSelectParam(BaseModel):
    mode: Literal["latest", "first", "all"] = Field(
        default="first",
        description=(
            "Episode selection mode for manga books. "
            "'latest' selects the newest num episodes, 'first' preserves legacy first-episode order, "
            "and 'all' selects every available episode. Ignored for non-manga sites."
        ),
    )
    num: int = Field(default=1, ge=1, description="Number of episodes for 'latest' or 'first'; clamped to available episodes.")


class EpisodeSelectionParam(BaseModel):
    book_key: str = Field(min_length=1, description="Book key returned by cgs_search_books.")
    episode_keys: list[str] = Field(min_length=1, description="Episode keys returned by cgs_list_book_episodes.")


class CgsMcpBackend(Protocol):
    async def health(self) -> JSONDict: ...
    async def list_sites(self) -> JSONDict: ...
    async def search_books(self, site: int, keyword: str, page: int = 1) -> JSONDict: ...
    async def list_book_episodes(self, session_id: str, book_key: str) -> JSONDict: ...
    async def submit_books(
            self,
            session_id: str,
            book_keys: list[str] | None = None,
            episode_select: EpisodeSelectParam | Mapping[str, Any] | None = None,
            episode_selections: list[EpisodeSelectionParam] | list[Mapping[str, Any]] | None = None,
    ) -> JSONDict: ...
    async def status(self) -> JSONDict: ...
    async def events(self) -> JSONDict: ...
    async def reset_work_state(self) -> JSONDict: ...
    async def subscription_config(self, customname: str = "default") -> JSONDict: ...
    async def update_subscription_config(self, config: Mapping[str, Any]) -> JSONDict: ...
    async def add_subscription_book(
            self,
            site: str,
            url: str,
            title: str,
            enabled: bool = True,
            customname: str = "default",
    ) -> JSONDict: ...
    async def update_subscription_book(
            self, index: int, patch: Mapping[str, Any], customname: str = "default"
    ) -> JSONDict: ...
    async def remove_subscription_book(self, index: int, customname: str = "default") -> JSONDict: ...
    async def publish_subscription_share_card(self, customname: str = "default") -> JSONDict: ...
    async def add_subscription_follow(self, bid: str, alias: str = "", customname: str = "default") -> JSONDict: ...
    async def update_subscription_follow(
            self, index: int, patch: Mapping[str, Any], customname: str = "default"
    ) -> JSONDict: ...
    async def remove_subscription_follow(self, index: int, customname: str = "default") -> JSONDict: ...


@dataclass(slots=True)
class CgsMcpBackendError(Exception):
    code: str
    message: str

    def to_tool_message(self) -> str:
        return f"{self.code}: {self.message}"


class HttpCgsMcpBackend:
    def __init__(
            self,
            base_url: str,
            *,
            timeout: float = 30.0,
            headers: Mapping[str, str] | None = None,
            transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.headers = dict(headers or {})
        self.transport = transport

    async def health(self) -> JSONDict:
        return await self._request("GET", "/health")

    async def list_sites(self) -> JSONDict:
        return await self._request("GET", "/sites")

    async def search_books(self, site: int, keyword: str, page: int = 1) -> JSONDict:
        return await self._request("POST", "/search", json={"site": site, "keyword": keyword, "page": page})

    async def list_book_episodes(self, session_id: str, book_key: str) -> JSONDict:
        return await self._request("POST", "/book-episodes", json={"session_id": session_id, "book_key": book_key})

    async def submit_books(
            self,
            session_id: str,
            book_keys: list[str] | None = None,
            episode_select: EpisodeSelectParam | Mapping[str, Any] | None = None,
            episode_selections: list[EpisodeSelectionParam] | list[Mapping[str, Any]] | None = None,
    ) -> JSONDict:
        payload: JSONDict = {"session_id": session_id, "book_keys": book_keys or []}
        if episode_select is not None:
            payload["episode_select"] = self._model_payload(episode_select)
        if episode_selections is not None:
            payload["episode_selections"] = [self._episode_selection_payload(item) for item in episode_selections]
        return await self._request("POST", "/submit-books", json=payload)

    async def status(self) -> JSONDict:
        return await self._request("GET", "/status")

    async def events(self) -> JSONDict:
        return await self._request("GET", "/events")

    async def reset_work_state(self) -> JSONDict:
        return await self._request("POST", "/work/reset")

    async def subscription_config(self, customname: str = "default") -> JSONDict:
        return await self._request("GET", "/subscription/config", params={"customname": customname})

    async def update_subscription_config(self, config: Mapping[str, Any]) -> JSONDict:
        return await self._request("PUT", "/subscription/config", json=dict(config))

    async def add_subscription_book(
            self,
            site: str,
            url: str,
            title: str,
            enabled: bool = True,
            customname: str = "default",
    ) -> JSONDict:
        payload: JSONDict = {"customname": customname, "site": site, "url": url, "title": title, "enabled": enabled}
        return await self._request("POST", "/subscription/books", json=payload)

    async def update_subscription_book(
            self, index: int, patch: Mapping[str, Any], customname: str = "default"
    ) -> JSONDict:
        return await self._request(
            "PATCH",
            f"/subscription/books/{int(index)}",
            params={"customname": customname},
            json=dict(patch),
        )

    async def remove_subscription_book(self, index: int, customname: str = "default") -> JSONDict:
        return await self._request(
            "DELETE", f"/subscription/books/{int(index)}", params={"customname": customname}
        )

    async def publish_subscription_share_card(self, customname: str = "default") -> JSONDict:
        return await self._request("POST", "/subscription/share-card", params={"customname": customname})

    async def add_subscription_follow(self, bid: str, alias: str = "", customname: str = "default") -> JSONDict:
        return await self._request(
            "POST",
            "/subscription/follows",
            json={"customname": customname, "bid": bid, "alias": alias},
        )

    async def update_subscription_follow(
            self, index: int, patch: Mapping[str, Any], customname: str = "default"
    ) -> JSONDict:
        return await self._request(
            "PATCH",
            f"/subscription/follows/{int(index)}",
            params={"customname": customname},
            json=dict(patch),
        )

    async def remove_subscription_follow(self, index: int, customname: str = "default") -> JSONDict:
        return await self._request(
            "DELETE", f"/subscription/follows/{int(index)}", params={"customname": customname}
        )

    async def _request(self, method: str, path: str, **kwargs) -> JSONDict:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self.transport) as client:
                response = await client.request(method, path, headers=self.headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise CgsMcpBackendError("server_timeout", f"CGS Server timed out at {self.base_url}") from exc
        except httpx.HTTPError as exc:
            raise CgsMcpBackendError("server_unavailable", f"CGS Server unavailable at {self.base_url}: {exc}") from exc
        return self._decode_response(response)

    def _decode_response(self, response: httpx.Response) -> JSONDict:
        if response.status_code >= 400:
            raise self._error_from_response(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise CgsMcpBackendError("invalid_response", f"CGS Server returned non-JSON response from {response.url}") from exc
        if not isinstance(payload, dict):
            raise CgsMcpBackendError("invalid_response", f"CGS Server returned non-object response from {response.url}")
        return payload

    def _error_from_response(self, response: httpx.Response) -> CgsMcpBackendError:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, dict):
            return CgsMcpBackendError(
                str(detail.get("code") or f"http_{response.status_code}"),
                str(detail.get("message") or response.reason_phrase),
            )
        if isinstance(payload, dict) and "code" in payload:
            return CgsMcpBackendError(str(payload.get("code")), str(payload.get("message") or response.reason_phrase))
        body = response.text.strip() or response.reason_phrase
        return CgsMcpBackendError(f"http_{response.status_code}", body)

    def _model_payload(self, value: BaseModel | Mapping[str, Any]) -> JSONDict:
        payload = value.model_dump(exclude_none=True) if hasattr(value, "model_dump") else dict(value)
        return {str(key): item for key, item in payload.items()}

    def _episode_selection_payload(self, value: EpisodeSelectionParam | Mapping[str, Any]) -> JSONDict:
        payload = self._model_payload(value)
        return {
            "book_key": str(payload.get("book_key") or ""),
            "episode_keys": [str(item) for item in payload.get("episode_keys") or []],
        }


class RuntimeCgsMcpBackend:
    def __init__(self, owner: Any):
        self.owner = owner

    async def health(self) -> JSONDict:
        return self.owner.health()

    async def list_sites(self) -> JSONDict:
        return {"sites": self.owner.list_supported_sites()}

    async def search_books(self, site: int, keyword: str, page: int = 1) -> JSONDict:
        return await self.owner.search(site, keyword, page)

    async def list_book_episodes(self, session_id: str, book_key: str) -> JSONDict:
        return await self.owner.book_episodes(session_id, book_key)

    async def submit_books(
            self,
            session_id: str,
            book_keys: list[str] | None = None,
            episode_select: EpisodeSelectParam | Mapping[str, Any] | None = None,
            episode_selections: list[EpisodeSelectionParam] | list[Mapping[str, Any]] | None = None,
    ) -> JSONDict:
        return self.owner.submit(session_id, book_keys or [], episode_select=episode_select, episode_selections=episode_selections)

    async def status(self) -> JSONDict:
        return self.owner.status()

    async def events(self) -> JSONDict:
        return self.owner.events()

    async def reset_work_state(self) -> JSONDict:
        return self.owner.reset_work_state(origin="mcp")

    async def subscription_config(self, customname: str = "default") -> JSONDict:
        return load_subscription_config(SubscriptionStore(customname))

    async def update_subscription_config(self, config: Mapping[str, Any]) -> JSONDict:
        payload = dict(config)
        return save_subscription_config(SubscriptionStore(str(payload.get("customname") or "default")), payload)

    async def add_subscription_book(
            self,
            site: str,
            url: str,
            title: str,
            enabled: bool = True,
            customname: str = "default",
    ) -> JSONDict:
        return add_book(
            SubscriptionStore(customname),
            {"site": site, "url": url, "title": title, "enabled": enabled},
        )

    async def update_subscription_book(
            self, index: int, patch: Mapping[str, Any], customname: str = "default"
    ) -> JSONDict:
        return update_book(SubscriptionStore(customname), index, dict(patch))

    async def remove_subscription_book(self, index: int, customname: str = "default") -> JSONDict:
        return remove_book(SubscriptionStore(customname), index)

    async def publish_subscription_share_card(self, customname: str = "default") -> JSONDict:
        return await publish_subscription_share_card(SubscriptionStore(customname))

    async def add_subscription_follow(self, bid: str, alias: str = "", customname: str = "default") -> JSONDict:
        return add_follow(SubscriptionStore(customname), {"bid": bid, "alias": alias})

    async def update_subscription_follow(
            self, index: int, patch: Mapping[str, Any], customname: str = "default"
    ) -> JSONDict:
        return update_follow(SubscriptionStore(customname), index, dict(patch))

    async def remove_subscription_follow(self, index: int, customname: str = "default") -> JSONDict:
        return remove_follow(SubscriptionStore(customname), index)


class CgsMcpSurface:
    def __init__(
            self,
            server: FastMCP,
            backend: CgsMcpBackend,
            *,
            call_log: McpCallLog | None = None,
            error_recorder: Callable[..., None] | None = None,
    ) -> None:
        self.server = server
        self.backend = backend
        self.call_log = call_log or McpCallLog()
        self.error_recorder = error_recorder

    def register(self) -> McpCallLog:
        server = self.server
        backend = self.backend
        server.cgs_call_log = self.call_log

        @server.tool(name="cgs_health", title="CGS Server health")
        async def cgs_health() -> JSONDict:
            """Return cgs-server health and foreground ownership state."""
            return await self._call(
                backend.health, tool_name="cgs_health", args_summary=self._args_summary(),
            )

        @server.tool(name="cgs_list_sites", title="List CGS sites")
        async def cgs_list_sites() -> JSONDict:
            """List CGS sites that support direct preview/search/download flow."""
            return await self._call(
                backend.list_sites, tool_name="cgs_list_sites", args_summary=self._args_summary(),
            )

        @server.tool(name="cgs_search_books", title="Search CGS books")
        async def cgs_search_books(site: int, keyword: str, page: int = 1) -> JSONDict:
            """Search books through the CGS Server and return a session plus BookInfo DTO list."""
            return await self._call(
                lambda: backend.search_books(site, keyword, page),
                tool_name="cgs_search_books", args_summary=self._args_summary(site=site, keyword=keyword, page=page),
            )

        @server.tool(name="cgs_list_book_episodes", title="List CGS book episodes")
        async def cgs_list_book_episodes(session_id: str, book_key: str) -> JSONDict:
            """List precise selectable episode keys for a manga BookInfo from a previous search session."""
            return await self._call(
                lambda: backend.list_book_episodes(session_id, book_key),
                tool_name="cgs_list_book_episodes", args_summary=self._args_summary(session_id=session_id, book_key=book_key),
            )

        @server.tool(name="cgs_submit_books", title="Submit CGS books")
        async def cgs_submit_books(
                session_id: str,
                book_keys: list[str] | None = None,
                episode_select: EpisodeSelectParam | None = None,
                episode_selections: list[EpisodeSelectionParam] | None = None,
        ) -> JSONDict:
            """Submit selected books from a previous CGS search session for download.

            Optional episode_select is {"mode": "latest"|"first"|"all", "num": int}.
            Omit it for backwards-compatible {"mode": "first", "num": 1}.
            For manga sites, latest selects the newest num episodes and clamps num to available episodes;
            all selects every episode. Non-manga sites ignore episode_select.
            For exact chapter choices, call cgs_list_book_episodes first, then pass episode_selections.
            """
            return await self._call(
                lambda: backend.submit_books(session_id, book_keys, episode_select, episode_selections),
                tool_name="cgs_submit_books",
                args_summary=self._args_summary(
                    session_id=session_id, book_keys=book_keys or [],
                    episode_select=episode_select, episode_selections=episode_selections or [],
                ),
            )

        @server.tool(name="cgs_get_status", title="Get CGS Server status")
        async def cgs_get_status() -> JSONDict:
            """Return current CGS Server availability and active job status."""
            return await self._call(
                backend.status, tool_name="cgs_get_status", args_summary=self._args_summary(),
            )

        @server.tool(name="cgs_get_events", title="Get CGS Server events")
        async def cgs_get_events() -> JSONDict:
            """Return recent CGS Server events and logs for the active or last job."""
            return await self._call(
                backend.events, tool_name="cgs_get_events", args_summary=self._args_summary(),
            )

        @server.tool(name="cgs_reset_work_state", title="Reset CGS work state")
        async def cgs_reset_work_state() -> JSONDict:
            """Clear completed/failed/idle CGS work state before a new search flow.

            A running submit/download job is not canceled by this tool and returns job_running.
            """
            return await self._call(
                backend.reset_work_state, tool_name="cgs_reset_work_state", args_summary=self._args_summary(),
            )

        @server.tool(name="cgs_get_subscription_config", title="Get CGS subscription config")
        async def cgs_get_subscription_config(customname: str = "default") -> JSONDict:
            """Return the flat single-form subscription config (books/features/follows/check/publish)."""
            return await self._call(
                lambda: backend.subscription_config(customname),
                tool_name="cgs_get_subscription_config",
                args_summary=self._args_summary(customname=customname),
            )

        @server.tool(name="cgs_update_subscription_config", title="Update CGS subscription config")
        async def cgs_update_subscription_config(config: dict[str, Any]) -> JSONDict:
            """Persist the flat subscription config; publish section is optional and marks a published config."""
            return await self._call(
                lambda: backend.update_subscription_config(config),
                tool_name="cgs_update_subscription_config",
                args_summary=self._args_summary(config=config),
            )

        @server.tool(name="cgs_add_subscription_book", title="Add subscription book")
        async def cgs_add_subscription_book(
                site: str,
                url: str,
                title: str,
                enabled: bool = True,
                customname: str = "default",
        ) -> JSONDict:
            """Add a CGS BookInfo-derived book to the subscription book list.
            """
            return await self._call(
                lambda: backend.add_subscription_book(site, url, title, enabled, customname),
                tool_name="cgs_add_subscription_book",
                args_summary=self._args_summary(
                    site=site, url=url, title=title, enabled=enabled,
                    customname=customname,
                ),
            )

        @server.tool(name="cgs_update_subscription_book", title="Update subscription book")
        async def cgs_update_subscription_book(
                index: int,
                site: str | None = None,
                url: str | None = None,
                title: str | None = None,
                enabled: bool | None = None,
                customname: str = "default",
        ) -> JSONDict:
            """Update a subscription book by zero-based index."""
            patch = {
                key: value
                for key, value in {
                    "site": site, "url": url, "title": title, "enabled": enabled,
                }.items()
                if value is not None
            }
            return await self._call(
                lambda: backend.update_subscription_book(index, patch, customname),
                tool_name="cgs_update_subscription_book",
                args_summary=self._args_summary(index=index, patch=patch, customname=customname),
            )

        @server.tool(name="cgs_remove_subscription_book", title="Remove subscription book")
        async def cgs_remove_subscription_book(index: int, customname: str = "default") -> JSONDict:
            """Remove a subscription book by zero-based index."""
            return await self._call(
                lambda: backend.remove_subscription_book(index, customname),
                tool_name="cgs_remove_subscription_book",
                args_summary=self._args_summary(index=index, customname=customname),
            )

        @server.tool(name="cgs_publish_subscription_share_card", title="Publish subscription share card")
        async def cgs_publish_subscription_share_card(customname: str = "default") -> JSONDict:
            """Publish the subscription share card and register publish bid through CGS."""
            return await self._call(
                lambda: backend.publish_subscription_share_card(customname),
                tool_name="cgs_publish_subscription_share_card",
                args_summary=self._args_summary(customname=customname),
            )

        @server.tool(name="cgs_add_subscription_follow", title="Add subscription follow")
        async def cgs_add_subscription_follow(
                bid: str,
                alias: str = "",
                customname: str = "default",
        ) -> JSONDict:
            """Add a follow bid to the subscription config."""
            return await self._call(
                lambda: backend.add_subscription_follow(bid, alias, customname),
                tool_name="cgs_add_subscription_follow",
                args_summary=self._args_summary(bid=bid, alias=alias, customname=customname),
            )

        @server.tool(name="cgs_update_subscription_follow", title="Update subscription follow")
        async def cgs_update_subscription_follow(
                index: int,
                bid: str | None = None,
                alias: str | None = None,
                customname: str = "default",
        ) -> JSONDict:
            """Update a subscription follow by zero-based index."""
            patch = {key: value for key, value in {"bid": bid, "alias": alias}.items() if value is not None}
            return await self._call(
                lambda: backend.update_subscription_follow(index, patch, customname),
                tool_name="cgs_update_subscription_follow",
                args_summary=self._args_summary(index=index, patch=patch, customname=customname),
            )

        @server.tool(name="cgs_remove_subscription_follow", title="Remove subscription follow")
        async def cgs_remove_subscription_follow(index: int, customname: str = "default") -> JSONDict:
            """Remove a subscription follow by zero-based index."""
            return await self._call(
                lambda: backend.remove_subscription_follow(index, customname),
                tool_name="cgs_remove_subscription_follow",
                args_summary=self._args_summary(index=index, customname=customname),
            )

        @server.resource("cgs://health", name="cgs-health", title="CGS Server health", mime_type="application/json")
        async def cgs_health_resource() -> str:
            return _json(await self._call(backend.health))

        @server.resource("cgs://sites", name="cgs-sites", title="CGS supported sites", mime_type="application/json")
        async def cgs_sites_resource() -> str:
            return _json(await self._call(backend.list_sites))

        @server.resource("cgs://status", name="cgs-status", title="CGS Server status", mime_type="application/json")
        async def cgs_status_resource() -> str:
            return _json(await self._call(backend.status))

        @server.resource("cgs://events", name="cgs-events", title="CGS Server events", mime_type="application/json")
        async def cgs_events_resource() -> str:
            return _json(await self._call(backend.events))

        @server.resource(
            "cgs://subscription/config",
            name="cgs-subscription-config",
            title="CGS subscription config",
            mime_type="application/json",
        )
        async def cgs_subscription_config_resource() -> str:
            return _json(await self._call(lambda: backend.subscription_config("default")))

        return self.call_log

    async def _call(self, operation, *, tool_name: str | None = None, args_summary: str = "{}") -> JSONDict:
        started = time.perf_counter()
        try:
            result = await operation()
        except CgsMcpBackendError as exc:
            tool_message = exc.to_tool_message()
            self._record_call(tool_name, args_summary, exc.code, started, tool_message, None)
            self._record_error(tool_name, exc.code, tool_message, exc)
            raise ToolError(tool_message) from exc
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None)
            if code and message:
                tool_message = CgsMcpBackendError(str(code), str(message)).to_tool_message()
                self._record_call(tool_name, args_summary, str(code), started, tool_message, None)
                self._record_error(tool_name, str(code), tool_message, exc)
                raise ToolError(tool_message) from exc
            tool_message = f"{type(exc).__name__}: {exc}"
            self._record_call(tool_name, args_summary, None, started, tool_message, None)
            self._record_error(tool_name, None, tool_message, exc)
            raise
        self._record_call(tool_name, args_summary, self._result_code(result), started, None, self._response_summary(result))
        return result

    def _record_call(
            self,
            tool_name: str | None,
            args_summary: str,
            code: str | None,
            started: float,
            error: str | None,
            response_summary: str | None,
    ) -> None:
        if tool_name is None:
            return
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        try:
            self.call_log.record(tool_name, args_summary, code, elapsed_ms, error, response_summary=response_summary)
        except Exception:
            _LOGGER.exception("failed to record MCP call")

    def _record_error(self, tool_name: str | None, code: str | None, message: str, exc: BaseException) -> None:
        if self.error_recorder is None or tool_name is None:
            return
        try:
            self.error_recorder(
                f"MCP {tool_name} failed", message, source="mcp", code=code, method="MCP", path=tool_name, status_code=None, exc=exc,
            )
        except Exception:
            _LOGGER.exception("failed to record MCP error")

    def _args_summary(self, **kwargs) -> str:
        return json.dumps(self._sanitize_mapping(kwargs), ensure_ascii=False, sort_keys=True)

    def _response_summary(self, payload: JSONDict) -> str:
        compact: JSONDict = {
            "keys": [self._redact_text(str(key)) for key in list(payload.keys())[:_RESPONSE_SUMMARY_KEY_LIMIT]],
            "bytes": len(json.dumps(self._sanitize_value("response", payload), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")),
        }
        if len(payload) > _RESPONSE_SUMMARY_KEY_LIMIT:
            compact["keys"].append("...")
        for key in ("code", "status", "available", "session_id", "page", "submitted", "reset"):
            if key in payload:
                compact[key] = self._sanitize_value(key, payload[key])
        for key in ("books", "events", "sites", "book_keys", "episodes", "episode_selections"):
            value = payload.get(key)
            if isinstance(value, list | tuple):
                compact[f"{key}_count"] = len(value)
        text = json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)
        return f"{text[:_RESPONSE_SUMMARY_VALUE_LIMIT]}..." if len(text) > _RESPONSE_SUMMARY_VALUE_LIMIT else text

    def _result_code(self, payload: JSONDict) -> str | None:
        code = payload.get("code")
        return None if code is None else str(code)

    def _sanitize_mapping(self, values: Mapping[str, Any]) -> JSONDict:
        summary: JSONDict = {}
        for key, value in values.items():
            key_text = str(key)
            if self._is_sensitive_key(key_text):
                summary["secret"] = "<redacted>"
            else:
                summary[self._redact_text(key_text)] = self._sanitize_value(key_text, value)
        return summary

    def _sanitize_value(self, key: str, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return self._sanitize_mapping(value.model_dump(exclude_none=True))
        if isinstance(value, Mapping):
            return self._sanitize_mapping(value)
        if isinstance(value, list | tuple):
            items = [self._sanitize_value(key, item) for item in value[:_ARG_SUMMARY_LIST_LIMIT]]
            return [*items, "..."] if len(value) > _ARG_SUMMARY_LIST_LIMIT else items
        if value is None or isinstance(value, bool | int | float):
            return value
        text = self._redact_text(str(value))
        return f"{text[:_ARG_SUMMARY_VALUE_LIMIT]}..." if len(text) > _ARG_SUMMARY_VALUE_LIMIT else text

    def _is_sensitive_key(self, key: str) -> bool:
        return any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)

    def _redact_text(self, text: str) -> str:
        if _TOKEN_WORD_RE.search(text) or self._is_sensitive_key(text):
            return "<redacted>"
        text = _BEARER_RE.sub("Bearer <redacted>", text)
        return _TOKEN_ASSIGNMENT_RE.sub("secret=<redacted>", text)


def create_cgs_mcp_server(
        backend: CgsMcpBackend,
        *,
        name: str = "ComicGUISpider",
        streamable_http_path: str = "/",
        call_log: McpCallLog | None = None,
        error_recorder: Callable[..., None] | None = None,
) -> FastMCP:
    server = FastMCP(
        name,
        instructions="Control a local ComicGUISpider Server instance.", json_response=True, stateless_http=True,
        streamable_http_path=streamable_http_path, transport_security=token_authenticated_transport_security(),
    )
    CgsMcpSurface(server, backend, call_log=call_log, error_recorder=error_recorder).register()
    return server


def create_runtime_mcp_server(owner: Any = None, *, call_log: McpCallLog | None = None):
    if owner is None:
        from server.runtime import runtime as resolved_owner
    else:
        resolved_owner = owner
    return create_cgs_mcp_server(
        RuntimeCgsMcpBackend(resolved_owner),
        streamable_http_path="/", call_log=call_log, error_recorder=resolved_owner.record_server_error,
    )


def create_runtime_mcp_surface(owner: Any = None, *, mount_path: str = "/mcp", call_log: McpCallLog | None = None) -> ServerSurface:
    server = create_runtime_mcp_server(owner, call_log=call_log)
    return ServerSurface(
        name="mcp", mount_path=mount_path, app=server.streamable_http_app(),
        lifespan_factory=server.session_manager.run, call_log=server.cgs_call_log,
    )


def create_runtime_mcp_app(owner: Any = None) -> Starlette:
    return create_runtime_mcp_surface(owner).app


def token_authenticated_transport_security() -> TransportSecuritySettings:
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def _json(payload: JSONDict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)

