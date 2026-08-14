from __future__ import annotations

import pathlib as p
from typing import Optional

import httpx

from utils import get_httpx_verify
from utils.script import conf
from utils.website.core import build_proxy_transport

HTTPX_USER_AGENT = "ComicGUISpider/1.0"


def create_aria2_http_client(*, timeout: float = 15.0) -> httpx.AsyncClient:
    transport, trust_env = build_proxy_transport(
        "direct",
        getattr(conf, "proxies", None) or [],
        is_async=True,
        retries=0,
        verify=get_httpx_verify(),
    )
    return httpx.AsyncClient(timeout=timeout, transport=transport, trust_env=trust_env)


class Aria2RpcClient:
    def __init__(
        self,
        *,
        url: str,
        secret: str = "",
        timeout: float = 15.0,
        session: Optional[httpx.AsyncClient] = None,
    ):
        self.url = str(url).rstrip("/")
        self.secret = str(secret or "").strip()
        self.session = session or create_aria2_http_client(timeout=timeout)
        self.sess = self.session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    def format_data(self, params: list, method: str = "aria2.addUri", _id: Optional[str] = None) -> dict:
        payload_params = list(params)
        if self.secret:
            payload_params = [f"token:{self.secret}", *payload_params]
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": payload_params,
            "id": _id,
        }

    async def request(self, method: str, *, json: Optional[dict] = None, **kwargs) -> httpx.Response:
        return await self.session.request(
            method,
            self.url,
            headers={"Content-Type": "application/json"},
            json=json,
            **kwargs,
        )

    async def aclose(self):
        await self.session.aclose()

    @staticmethod
    def _normalize_header_option(raw_headers) -> list[str]:
        if raw_headers is None:
            normalized = []
        elif isinstance(raw_headers, (list, tuple, set)):
            normalized = [str(item).strip() for item in raw_headers if str(item).strip()]
        else:
            text = str(raw_headers).strip()
            normalized = [text] if text else []
        if not any(
            header.split(":", 1)[0].strip().casefold() == "user-agent"
            for header in normalized
            if ":" in header
        ):
            normalized.append(f"User-Agent: {HTTPX_USER_AGENT}")
        return normalized

    async def add_uri(
        self,
        url: str,
        *,
        target_dir: p.Path,
        out: Optional[str] = None,
        task_id: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> str:
        payload_options = dict(options or {})
        payload_options.setdefault("dir", str(target_dir))
        if out:
            payload_options.setdefault("out", out)
        payload_options["header"] = self._normalize_header_option(payload_options.get("header"))
        response = await self.request(
            "POST",
            json=self.format_data(
                [[url], payload_options],
                _id=task_id,
            ),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            message = payload["error"].get("message") or str(payload["error"])
            raise RuntimeError(message)
        gid = payload.get("result")
        if not gid:
            raise RuntimeError(f"invalid aria2 response: {payload}")
        return gid

    async def tell_status(self, gid: str, keys: Optional[list[str]] = None) -> dict:
        response = await self.request(
            "POST",
            json=self.format_data(
                [gid, keys or ["status", "errorCode", "errorMessage"]],
                method="aria2.tellStatus",
                _id=f"tell-{gid}",
            ),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            message = payload["error"].get("message") or str(payload["error"])
            raise RuntimeError(message)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"invalid aria2 status response: {payload}")
        return result

    async def get_version(self) -> dict:
        response = await self.request(
            "POST",
            json=self.format_data([], method="aria2.getVersion", _id="version"),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            message = payload["error"].get("message") or str(payload["error"])
            raise RuntimeError(message)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"invalid aria2 version response: {payload}")
        return result

    async def check_gid_status(self, gid: str):
        try:
            result = await self.request(
                "POST",
                json=self.format_data([gid], method="aria2.tellStatus"),
            )
            return gid, result.json()
        except Exception as exc:
            return gid, {"error": str(exc)}


# Backward-compatible alias used by existing call sites.
MotrixRPC = Aria2RpcClient
