from __future__ import annotations

import json
import re
import typing as t

import httpx
from loguru import logger

from .provider import AiProvider


def chat_completions_url(base_url: str) -> str:
    root = str(base_url or "").rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def extract_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty llm content")
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        payload = json.loads(fence.group(1).strip())
        if isinstance(payload, dict):
            return payload
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(raw[start : end + 1])
        if isinstance(payload, dict):
            return payload
    raise ValueError("llm content is not json object")


class OpenAiCompatClient:
    """Kernel transport: OpenAI-compatible chat.completions only. No domain prompts."""

    def __init__(self, provider: AiProvider, *, proxies: object = None, timeout: float = 90.0):
        if not provider.is_configured():
            raise ValueError("AI provider is not configured")
        self.provider = provider
        self.proxies = proxies
        self.timeout = timeout

    def _proxy_url(self) -> str | None:
        values = self.proxies if isinstance(self.proxies, (list, tuple)) else []
        for raw in values:
            text = str(raw or "").strip()
            if not text:
                continue
            return text if "://" in text else f"http://{text}"
        return None

    def chat_content(self, messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
        url = chat_completions_url(self.provider.url or "")
        headers = {
            "Authorization": f"Bearer {self.provider.key}",
            "Content-Type": "application/json",
        }
        body: dict[str, t.Any] = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": temperature,
            "reasoning_effort": "high",
        }
        client_kwargs: dict[str, t.Any] = {
            "timeout": self.timeout,
            "headers": headers,
        }
        proxy_url = self._proxy_url()
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        def request(payload: dict) -> httpx.Response:
            with httpx.Client(**client_kwargs) as client:
                return client.post(url, json=payload)

        response = request(body)
        if response.status_code >= 400:
            detail = (response.text or "").lower()
            if "reasoning_effort" in detail or "unknown" in detail or "unsupported" in detail:
                logger.warning("[AI][llm] retry without reasoning_effort")
                body.pop("reasoning_effort", None)
                response = request(body)
        response.raise_for_status()
        data = response.json()
        content = (
            (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
            if isinstance(data, dict)
            else None
        )
        return str(content or "")

    def chat_json(self, messages: list[dict[str, str]], *, temperature: float = 0.2) -> dict:
        return extract_json_object(self.chat_content(messages, temperature=temperature))
