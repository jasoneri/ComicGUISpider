"""cf worker `/index/{bid}` client — KV index for subscription metadata pointers.

Honors invariants I7 (cf worker stores KV only, no pkl traffic) and I11
(no silent fallback — every failure raises a typed exception).

The KV record schema is intentionally minimal:
    {
        "message_id":    str,    # discord message id hosting the pkl attachment
        "attachment_url": str,   # discord CDN URL pointing to the pkl bytes
        "updated_at":    str,    # ISO8601 timestamp
    }

Broadcaster -> POST/PUT one record per bid after every E2 publish cycle.
Subscriber  -> GET the latest record, then HTTP GET attachment_url from CDN.
"""
from __future__ import annotations

import json as _json
from dataclasses import asdict, dataclass
from typing import Optional

import httpx

from utils import get_httpx_verify
from variables import CGS_WORKER_ENDPOINT


class WorkerIndexError(RuntimeError):
    """Base error for cf worker /index/{bid} interactions."""


class WorkerIndexNotFoundError(WorkerIndexError):
    """Raised when the bid has no index record yet (HTTP 404)."""


class WorkerIndexAuthError(WorkerIndexError):
    """Raised on HTTP 401/403 — token missing/expired/unauthorized."""


class WorkerIndexBadRequestError(WorkerIndexError):
    """Raised on HTTP 4xx other than 401/403/404 — request schema invalid."""


class WorkerIndexServerError(WorkerIndexError):
    """Raised on HTTP 5xx — worker-side fault."""


@dataclass
class PublishBidRegistration:
    bid: str
    issued_at: str

    @classmethod
    def from_payload(cls, payload: dict) -> "PublishBidRegistration":
        bid = str(payload.get("bid") or "").strip()
        issued_at = str(payload.get("issued_at") or "").strip()
        if not bid:
            raise WorkerIndexError("register payload missing bid")
        if not issued_at:
            raise WorkerIndexError("register payload missing issued_at")
        return cls(bid=bid, issued_at=issued_at)


@dataclass
class IndexRecord:
    """KV value persisted by cf worker; mirrors PRD E2 step-3 POST body."""

    message_id: str
    attachment_url: str
    updated_at: str

    def to_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict) -> "IndexRecord":
        missing = [k for k in ("message_id", "attachment_url", "updated_at") if not payload.get(k)]
        if missing:
            raise WorkerIndexError(f"worker index payload missing required fields: {missing}")
        return cls(
            message_id=str(payload["message_id"]),
            attachment_url=str(payload["attachment_url"]),
            updated_at=str(payload["updated_at"]),
        )


class WorkerIndexClient:
    """Thin async client for cf worker `/index/{bid}` KV endpoint.

    Single responsibility: GET / PUT one KV record. **No pkl payload** flows
    through this client — discord CDN owns the bytes (invariant I7).
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        auth_token: str = "",
        *,
        timeout: float = 30.0,
        transport_retries: int = 2,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        resolved_endpoint = str(CGS_WORKER_ENDPOINT if endpoint is None else endpoint).strip().rstrip("/")
        if not resolved_endpoint:
            raise WorkerIndexError("CGS_WORKER_ENDPOINT is required")
        self.endpoint = resolved_endpoint
        self.auth_token = str(auth_token or "").strip()
        if not self.auth_token:
            raise WorkerIndexAuthError("conf.discord_share_user_token is required for worker index requests")
        self.timeout = float(timeout)
        self.transport_retries = int(transport_retries)
        self._injected_transport = transport  # test seam

    # ---------- public API ----------

    async def register_publish_bid(
        self,
        *,
        summary: dict,
        discord_user_id: str = "",
        client_nonce: str = "",
    ) -> PublishBidRegistration:
        if not isinstance(summary, dict):
            raise WorkerIndexError(f"summary must be a mapping, got {type(summary).__name__}")
        body = {"summary": summary}
        discord_user_id = str(discord_user_id or "").strip()
        client_nonce = str(client_nonce or "").strip()
        if discord_user_id:
            body["discord_user_id"] = discord_user_id
        if client_nonce:
            body["client_nonce"] = client_nonce
        response = await self._request(
            "POST",
            "/register",
            content=_json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_status(response)
        payload = self._parse_json(response)
        return PublishBidRegistration.from_payload(payload)

    async def get_index(self, bid: str) -> IndexRecord:
        """Fetch the latest index record for `bid`.

        Raises:
            WorkerIndexNotFoundError: bid has no record.
            WorkerIndexAuthError: token rejected.
            WorkerIndexBadRequestError / WorkerIndexServerError: per HTTP class.
            WorkerIndexError: network failure or malformed body.
        """
        bid = self._validate_bid(bid)
        response = await self._request("GET", f"/index/{bid}")
        self._raise_for_status(response)
        payload = self._parse_json(response)
        return IndexRecord.from_payload(payload)

    async def put_index(self, bid: str, record: IndexRecord) -> None:
        """Persist `record` as the latest pointer for `bid` (broadcaster-only).

        Uses POST (worker decides upsert semantics; we just push the latest).
        """
        bid = self._validate_bid(bid)
        if not isinstance(record, IndexRecord):
            raise WorkerIndexError(f"record must be IndexRecord, got {type(record).__name__}")
        body = record.to_payload()
        response = await self._request(
            "POST",
            f"/index/{bid}",
            content=_json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_status(response)

    # ---------- internals ----------

    @staticmethod
    def _validate_bid(bid: str) -> str:
        bid = str(bid or "").strip()
        if not bid:
            raise WorkerIndexError("bid is required")
        if "/" in bid or "?" in bid or "#" in bid:
            raise WorkerIndexError(f"bid contains forbidden path/query chars: {bid!r}")
        return bid

    def _transport(self) -> httpx.AsyncBaseTransport:
        if self._injected_transport is not None:
            return self._injected_transport
        return httpx.AsyncHTTPTransport(retries=self.transport_retries, verify=get_httpx_verify())

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            transport=self._transport(),
            trust_env=False,
        )

    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if extra:
            headers.update(extra)
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = self._headers(kwargs.pop("headers", None))
        try:
            async with self._client() as client:
                return await client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise WorkerIndexError(f"network error talking to worker: {exc}") from exc

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise WorkerIndexError(f"worker returned non-JSON body: {response.text[:200]!r}") from exc
        if not isinstance(payload, dict):
            raise WorkerIndexError(f"worker JSON root must be a mapping, got {type(payload).__name__}")
        return payload

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        message = cls._extract_error(response)
        if status == 404:
            raise WorkerIndexNotFoundError(message)
        if status in (401, 403):
            raise WorkerIndexAuthError(message)
        if 400 <= status < 500:
            raise WorkerIndexBadRequestError(message)
        raise WorkerIndexServerError(message)

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            msg = str(payload.get("error") or payload.get("message") or "").strip()
        else:
            msg = ""
        return msg or f"worker /index error: HTTP {response.status_code} body={response.text[:200]!r}"
