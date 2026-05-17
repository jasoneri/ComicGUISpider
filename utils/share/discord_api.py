from __future__ import annotations

import json as _json

import httpx

from utils import get_httpx_verify


class DiscordShareApiError(RuntimeError):
    pass


class DiscordShareCooldownError(DiscordShareApiError):
    def __init__(self, hours_left: int):
        self.hours_left = int(hours_left)
        super().__init__(f"冷却中，还需 {self.hours_left} 小时")


class DiscordSharePayloadTooLargeError(DiscordShareApiError):
    def __init__(self, size_bytes: int, *, limit_bytes: int):
        self.size_bytes = int(size_bytes)
        self.limit_bytes = int(limit_bytes)
        size_mb = self.size_bytes / (1024 * 1024)
        limit_mb = self.limit_bytes / (1024 * 1024)
        super().__init__(f"文件过大（{size_mb:.2f}MB > {limit_mb:.0f}MB）")


class DiscordShareAPI:
    def __init__(self, api_url: str, user_token: str, *, timeout: float = 60.0, transport_retries: int = 2):
        self.api_url = str(api_url or "").rstrip("/")
        self.user_token = str(user_token or "").strip()
        self.timeout = timeout
        self.transport_retries = int(transport_retries)

    def _transport(self) -> httpx.AsyncHTTPTransport:
        return httpx.AsyncHTTPTransport(retries=self.transport_retries, verify=get_httpx_verify())

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport(), trust_env=False)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.user_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            async with self._client() as client:
                return await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise DiscordShareApiError(f"网络错误，请稍后重试: {exc}") from exc

    async def upload_share(self, *, payload_bytes: bytes, covers: list[tuple[str, bytes]], site: str, book_names: list[str]) -> str:
        files = [("pkl_file", ("share.pkl", payload_bytes, "application/octet-stream"))]
        for idx, (_name, cover_bytes) in enumerate(covers):
            files.append((f"cover_{idx}", (f"cover_{idx}.jpg", cover_bytes, "image/jpeg")))
        data = {
            "site": site,
            "book_count": str(len(covers)),
            "book_names": _json.dumps(list(book_names), ensure_ascii=False),
        }
        response = await self._request(
            "POST", f"{self.api_url}/api/upload", headers=self._headers(), files=files, data=data,
        )
        return self._parse_upload_response(response)

    async def download_share(self, share_id: str) -> bytes:
        response = await self._request(
            "GET", f"{self.api_url}/api/download/{share_id}", headers=self._headers(), follow_redirects=True, timeout=30.0,
        )
        if response.status_code == 404:
            raise DiscordShareApiError("分享不存在或已删除")
        if response.status_code >= 400:
            raise DiscordShareApiError(self._extract_error(response))
        return response.content

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = str(payload.get("error") or payload.get("message") or "").strip()
        if response.status_code == 401:
            return message or "user_token 无效，请重新在 Discord 获取"
        if response.status_code == 413:
            return message or "文件过大"
        if response.status_code == 429:
            hours_left = int(payload.get("hours_left") or 0)
            return f"冷却中，还需 {hours_left} 小时" if hours_left > 0 else "冷却中"
        return message or f"Discord share API error: HTTP {response.status_code}"

    def _parse_upload_response(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code == 429:
            raise DiscordShareCooldownError(int(payload.get("hours_left") or 0))
        if response.status_code >= 400:
            raise DiscordShareApiError(self._extract_error(response))
        share_id = str(payload.get("share_id") or payload.get("message_id") or "").strip()
        if not share_id:
            raise DiscordShareApiError("share API 缺少 share_id")
        return share_id
