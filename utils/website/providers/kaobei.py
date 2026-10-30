from __future__ import annotations

import asyncio
import contextlib
import json
import re
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from lxml import html

from utils import conf, temp_p
from utils.website.core import Cache, Previewer, Req, Utils, build_proxy_transport
from utils.website.info import Episode, KbBookInfo


class KaobeiResponseError(Exception):
    """Provider-owned classified response failure.

    `category` is one of the stable contract categories; `__str__` is the only
    serialization point consumed by LogEvent / preview error signals, and it
    carries stage, URL, status, body length, and a bounded snippet — never
    cookies, tokens, or full response bodies.
    """

    def __init__(self, category: str, *, stage: str, url: str, status=None, body_len=None, snippet=None):
        self.category = category
        self.stage = stage
        self.url = url
        self.status = status
        self.body_len = body_len
        self.snippet = snippet
        super().__init__(self.__str__())

    def __str__(self) -> str:
        status = self.status if self.status is not None else "-"
        body_len = self.body_len if self.body_len is not None else "-"
        snippet = self.snippet if self.snippet else "<empty>"
        return (
            f"kaobei {self.stage} response {self.category}: "
            f"status={status} url={self.url} body_len={body_len} body={snippet}"
        )


class KaobeiEmptyContentKeyError(ValueError):
    """Chapter page rendered the site's degraded shell (empty contentKey).

    The site serves this shell per-request with a jittering TTL (observed:
    chapter 1 of a run succeeded while chapter 2 hit the shell seconds later),
    so the failure is retryable at the transport level. Kept as a ValueError
    because existing parser consumers classify it that way.
    """



_COPYMANGA_APP_BAN_CODE = 210
# Verbatim marker from the code:210 body. Kept as a substring test so the
# category survives minor wording drift around this sentence, but it MUST stay
# the distinctive clause — a generic "請下載" would misclassify real migration
# notices. The ban is a ~1 hour account/exit penalty (see the message itself),
# so it is NOT a transient backoff case: retrying inside a run cannot clear it.
_COPYMANGA_APP_BAN_MARKER = "破解版本"
_COPYMANGA_ALERT_CODES = {_COPYMANGA_APP_BAN_CODE}


def _detect_alert_envelope(body: "str | dict") -> tuple[int | None, str]:
    """Return (alert_code, message) when a JSON body is a CopyManga alert envelope.

    CopyManga reports risk/limit conditions as HTTP 200 with a `code` field
    instead of a payload. `code:210` is the app-integrity ban:

        {"code":210,"message":"請到官網更新最新APP(...), 您或您身邊的人曾經下載過
         破解版本的拷貝漫畫,請下載安裝正版之後等待1小時,限制會自動解除。"}

    Treating this as a payload is what produced a false success: the body is
    valid JSON, so the shape check passes, `results` just lacks the expected key,
    and callers degrade to "no results". Only envelopes whose code is known (or
    that carry the ban marker) are reported, so an ordinary payload that happens
    to include a `code` field is not misread. Accepts raw text or an already
    parsed dict so both the body-classification seam and the JSON seam reuse it.
    """
    if isinstance(body, dict):
        payload = body
    elif isinstance(body, str) and body.startswith("{"):
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            return None, ""
    else:
        return None, ""
    if not isinstance(payload, dict):
        return None, ""
    code = payload.get("code")
    message = str(payload.get("message") or "")
    is_alert_code = isinstance(code, int) and code in _COPYMANGA_ALERT_CODES
    if is_alert_code or _COPYMANGA_APP_BAN_MARKER in message:
        return (code if isinstance(code, int) else None), message
    return None, ""


def _classify_body_text(stage: str, url: str, text: str, *, status=None, expect_json: bool = False) -> str:
    """Classify a transport-succeeded body; raise KaobeiResponseError on failure categories.

    JSON stages must start with an object/array (otherwise non_json_or_html);
    HTML/page stages apply the tested 16-byte minimum. A JSON error envelope such
    as `{"code":210,...}` is structurally valid JSON but is NOT a payload, so the
    alert-code check runs BEFORE the JSON shape check — otherwise the risk body
    passes through, `results` simply lacks the expected key, and callers degrade
    into "no results" instead of surfacing the ban.
    """
    raw_text = str(text or "")
    normalized = " ".join(raw_text.split())
    snippet = normalized[:160] if normalized else "<empty>"
    if not raw_text:
        raise KaobeiResponseError("empty_body", stage=stage, url=url, status=status, body_len=0, snippet=snippet)
    if normalized.casefold() == "error":
        raise KaobeiResponseError("literal_error", stage=stage, url=url, status=status, body_len=len(raw_text), snippet=snippet)
    alert_code, alert_message = _detect_alert_envelope(normalized)
    if alert_code is not None:
        raise KaobeiResponseError(
            "app_ban_alert", stage=stage, url=url, status=status, body_len=len(raw_text),
            snippet=f"code={alert_code} {alert_message}",
        )
    if expect_json:
        if not normalized.startswith(("{", "[")):
            raise KaobeiResponseError("non_json_or_html", stage=stage, url=url, status=status, body_len=len(raw_text), snippet=snippet)
        return normalized
    if len(normalized) < 16:
        raise KaobeiResponseError("short_body", stage=stage, url=url, status=status, body_len=len(raw_text), snippet=snippet)
    return normalized


class _KaobeiContract:
    name = "manga_copy"
    proxy_policy = "proxy"
    preview_batch_limits = {"episodes": 1, "pages": 1}
    preview_transport_retries = 2
    _JSON_PREVIEW_STAGES = frozenset({"preview_search", "preview_fetch_episodes", "preview_fetch_pages"})
    uuid_regex = re.compile(r"(\d+)$")
    pc_domain = "www.2026copy.com"
    api_domain = "api.2026copy.com"
    domain = pc_domain
    cache_file = "kaobei_aeskey.txt"
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Dnts": "3",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }
    ua_mapi = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Origin": f"https://{pc_domain}",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip, compress",
        "platform": "1",
        "version": "2026.02.02",
        "webp": "1",
        "region": "0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    book_hea = headers
    _search_mappings = {"更新": "byRefresh", "排名": "byRank"}
    turn_page_info = (r"offset=\d+", None, 30)


class KaobeiParser(_KaobeiContract):
    def __init__(self, reqer: "KaobeiReqer"):
        self.reqer = reqer

    @classmethod
    def parse_search_targets(cls, targets, frame):
        rendering_map = frame.rendering_map()
        render_keys = frame.print_head[1:]
        books = []
        for idx, target in enumerate(targets, start=1):
            book = cls.parse_book_item(target, rendering_map, render_keys, idx)
            book.img_preview = frame.extract_cover(target)
            books.append(book)
        return books

    @classmethod
    def parse_book_item(cls, target, rendering_map, render_keys, idx):
        rendered = {
            attr_name: ",".join(map(lambda value: str(value.value), path.find(target)))
            for attr_name, path in rendering_map.items()
        }
        book_path = rendered.pop("book_path")
        book = KbBookInfo(
            idx=idx, render_keys=render_keys, url=f"https://{cls.pc_domain}/comicdetail/{book_path}/chapters",
            preview_url=f"https://{cls.pc_domain}/comic/{book_path}",
        )
        for key in render_keys:
            setattr(book, key, rendered.get(key))
        return book

    @classmethod
    def parse_ep_item(cls, chapter_datum, comic_path_word, book, idx):
        return Episode(
            from_book=book, id=chapter_datum["id"], idx=idx,
            url=f"https://{cls.pc_domain}/comic/{comic_path_word}/chapter/{chapter_datum['id']}", name=chapter_datum["name"],
        )

    def parse_episodes(self, json_results, book, *, url, show_dhb=False):
        resp_data = self.decrypt_chapter_data(json_results, url=url)
        build = resp_data.get("build")
        if not isinstance(build, dict):
            raise ValueError(f"kaobei chapters payload missing build block: url={url}")
        comic_path_word = build.get("path_word")
        if not comic_path_word:
            raise ValueError(f"kaobei chapters payload missing path_word: url={url}")
        groups = build.get("groups")
        if not isinstance(groups, dict):
            groups = resp_data.get("groups")
        if not isinstance(groups, dict):
            raise ValueError(f"kaobei chapters payload missing groups: url={url}")
        default_group = groups.get("default")
        if not isinstance(default_group, dict):
            raise ValueError(f"kaobei chapters payload missing default group: url={url}")
        chapters_data = list(default_group.get("chapters") or [])
        if show_dhb:
            for group_name in ("tankobon", "other_group"):
                group = groups.get(group_name)
                if isinstance(group, dict):
                    chapters_data.extend(group.get("chapters") or [])
        if not chapters_data:
            raise KaobeiResponseError(
                "empty_chapter_data", stage="preview_fetch_episodes", url=url,
                snippet=f"path_word={comic_path_word} group_keys={list(groups)}",
            )
        return [
            self.parse_ep_item(chapter_datum, comic_path_word, book, idx + 1)
            for idx, chapter_datum in enumerate(chapters_data)
        ]

    @staticmethod
    def _decrypt(cipher_hex: str, *, aes_key: str, iv: str) -> dict:
        cipher_bytes = bytes.fromhex(cipher_hex)
        key_bytes = aes_key.encode("utf-8")
        iv_bytes = iv.encode("utf-8")
        cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(cipher_bytes) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return json.loads(decrypted.decode("utf-8"))

    def decrypt_chapter_data(self, ret: str, **meta_info):
        aes_key = self.reqer.get_aes_key()
        stage = str(meta_info.get("stage") or "decrypt_chapter_data")
        url = str(meta_info.get("url") or "-")
        if not isinstance(ret, str):
            raise TypeError(f"kaobei encrypted payload must be str: got {type(ret).__name__} {meta_info=}")
        if len(ret) <= 16:
            raise KaobeiResponseError(
                "invalid_encrypted_payload", stage=stage, url=url,
                body_len=len(ret), snippet="<encrypted payload too short>",
            )
        try:
            return self._decrypt(ret[16:], aes_key=aes_key, iv=ret[:16])
        except Exception as exc:
            self.reqer.clear_aes_key()
            raise KaobeiResponseError(
                "invalid_encrypted_payload", stage=stage, url=url,
                body_len=len(ret), snippet="<decrypt failed, aes_key cache cleared>",
            ) from exc

    @staticmethod
    def extract_page_content_key(html_text: str, *, url: str) -> str:
        doc = html.fromstring(html_text)
        scripts = doc.xpath('//script[contains(text(), "var contentKey =")]/text()')
        content_key_script = next(iter(scripts), None)
        if not content_key_script:
            raise ValueError("拷贝更改了contentKey xpath")
        content_key_match = re.search(r"""var contentKey = ["']([^']*)["']""", content_key_script)
        if not content_key_match:
            raise ValueError("拷贝更改了contentKey 格式")
        content_key = content_key_match.group(1)
        if not content_key:
            raise KaobeiEmptyContentKeyError(f"kaobei chapter page returned empty contentKey: url={url}")
        return content_key

    def parse_page_urls_from_html(self, html_text: str, *, url: str) -> list[dict]:
        content_key = self.extract_page_content_key(html_text, url=url)
        return self.decrypt_chapter_data(content_key, url=url)

    def parse_page_urls_from_chapter_json(self, payload: dict, *, url: str) -> list[dict]:
        """Image list from the api v3 `chapter` route (plain JSON, no contentKey).

        The route returns the same list the web chapter page's contentKey
        decrypts to (46/46 match measured 2026-09-15), so an empty `contents`
        here is the degraded-shell equivalent and carries the same category.
        """
        chapter = (payload.get("results") or {}).get("chapter") or {}
        contents = chapter.get("contents")
        if not isinstance(contents, list) or not contents:
            raise KaobeiResponseError(
                "empty_chapter_data", stage="preview_fetch_pages", url=url,
                snippet=f"chapter_keys={sorted(chapter)} size={chapter.get('size')}",
            )
        return contents


class KaobeiReqer(_KaobeiContract, Req):
    parser_cls = KaobeiParser

    def __init__(self, _conf=None, *, owner=None, build_sync_client=True):
        self.conf = _conf or conf
        self.owner = owner
        self.preview_client = None
        self._owned_preview_client = None
        self._aes_key = None
        self._aes_cache_path = temp_p.joinpath(self.cache_file)
        self._aes_cache = Cache(self.cache_file)
        self.parser = self.parser_cls(self)
        if build_sync_client:
            self.cli = self.get_cli(self.conf)

    @classmethod
    def build_search_spec(cls, keyword: str, domain: str = None) -> tuple:
        from utils.website.schema import KbFrameBook

        domain = domain or cls.api_domain
        frame = KbFrameBook(domain)
        url = frame.url + keyword

        if matched := re.search(r".*?(排名|更新)", keyword):
            getattr(frame, cls._search_mappings[matched[1]])()
            url = frame.url
        if "轻小说" in keyword:
            frame.byQingXiaoShuo()
        if "排名" in keyword:
            params = {"type": 1}
            time_search = re.search(r".*?([日周月总])", keyword)
            kind_search = re.search(r".*?(轻小说|男|女)", keyword)
            params |= frame.expand_map[kind_search[1]] if kind_search else frame.expand_map["男"]
            params |= frame.expand_map[time_search[1]] if time_search else frame.expand_map["日"]
            url = f"{frame.url}&{urlencode(params)}"
        return url, frame

    def _read_cached_key(self):
        if self._aes_key:
            return self._aes_key
        cached = self._aes_cache.run(lambda: None, "daily")
        if cached:
            self._aes_key = cached
        return cached

    def _write_cached_key(self, key: str):
        self._aes_cache_path.write_text(key, encoding="utf-8")
        self._aes_cache.flag = "new"
        self._aes_cache.val = key
        self._aes_key = key
        return key

    def clear_aes_key(self):
        self._aes_key = None
        self._aes_cache.flag = "new"
        self._aes_cache.val = None
        self._aes_cache_path.unlink(missing_ok=True)

    def aes_cache_hit(self) -> bool:
        if self._aes_cache.flag is None:
            self._read_cached_key()
        return self._aes_cache.flag != "new"

    @staticmethod
    def extract_aes_key(html_text: str) -> str:
        html_doc = html.fromstring(html_text)
        script_texts = [text.strip().replace(" ", "") for text in html_doc.xpath("//script/text()")]
        real_script = next(filter(lambda text: text.startswith("var"), script_texts), None)
        if not real_script:
            raise ValueError("kaobei aes key script not found")
        matched = re.search(r"""=['"](.*?)['"]""", real_script.split("\n")[0])
        if not matched:
            raise ValueError("kaobei aes key value not found")
        return matched.group(1)

    def _active_preview_client(self) -> httpx.AsyncClient:
        if self.preview_client is not None:
            return self.preview_client
        if self._owned_preview_client is not None:
            return self._owned_preview_client
        raise RuntimeError("kaobei preview client is required for preview requests")

    @classmethod
    def _stage_expects_json(cls, stage: str) -> bool:
        return stage in cls._JSON_PREVIEW_STAGES

    @classmethod
    def _parse_preview_json(cls, resp, *, stage: str, request_url: str) -> dict:
        status = getattr(resp, "status_code", None)
        text = str(getattr(resp, "text", "") or "")
        _classify_body_text(stage, request_url, text, status=status, expect_json=cls._stage_expects_json(stage))
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            snippet = " ".join(text.split())
            snippet = snippet[:160] if snippet else "<empty>"
            raise KaobeiResponseError(
                "non_json_or_html", stage=stage, url=request_url, status=status,
                body_len=len(text), snippet=snippet,
            ) from exc
        if not isinstance(payload, dict):
            snippet = " ".join(text.split())[:160] if text else "<empty>"
            raise KaobeiResponseError(
                "non_json_or_html", stage=stage, url=request_url, status=status,
                body_len=len(text), snippet=f"payload_type={type(payload).__name__} {snippet}",
            )
        # Envelope guard at the seam most callers read raw: `results` may be
        # absent under a code:210 alert even though the body is valid JSON.
        # Without this, callers that pull `results` themselves would see an
        # empty dict and degrade to "no results" (the original false success).
        alert_code, alert_message = _detect_alert_envelope(payload)
        if alert_code is not None or "results" not in payload:
            raise KaobeiResponseError(
                "app_ban_alert" if alert_code is not None else "missing_results",
                stage=stage, url=request_url, status=status, body_len=len(text),
                snippet=f"code={alert_code} keys={sorted(payload)} {alert_message}",
            )
        return payload

    async def _preview_get(self, url: str, *, stage: str, headers: dict | None = None, **kwargs):
        last_exc = None
        for attempt in range(self.preview_transport_retries + 1):
            try:
                resp = await self._active_preview_client().get(url, headers=headers, **kwargs)
                resp.raise_for_status()
                status = getattr(resp, "status_code", None)
                text = str(getattr(resp, "text", "") or "")
                _classify_body_text(stage, url, text, status=status, expect_json=self._stage_expects_json(stage))
                return resp
            except (httpx.HTTPError, KaobeiResponseError) as exc:
                last_exc = exc
                category = getattr(exc, "category", None)
                # `app_ban_alert` is deliberately NOT retryable: the ban message
                # states a ~1 hour wait, so a sub-minute backoff loop cannot
                # clear it and only burns the remaining account headroom.
                retryable = isinstance(exc, httpx.HTTPError) or category in {"empty_body", "short_body", "literal_error"}
                if attempt >= self.preview_transport_retries or not retryable:
                    raise
                await asyncio.sleep(0.4)
        raise RuntimeError(f"kaobei {stage} preview request exhausted retries without result: url={url}") from last_exc

    async def _fetch_aes_key(self) -> str:
        resp = await self._preview_get(
            f"https://{self.pc_domain}/comic/yiquanchaoren", headers=self.headers, stage="aes_key", follow_redirects=True, timeout=12,
        )
        return self._write_cached_key(self.extract_aes_key(resp.text))

    @contextlib.asynccontextmanager
    async def _preview_client_scope(self):
        """Yield a usable preview client, owning one only when none is attached."""
        if self.preview_client is not None or self._owned_preview_client is not None:
            yield self._active_preview_client()
            return
        transport, trust_env = build_proxy_transport(self.proxy_policy, self.conf.proxies)
        async with httpx.AsyncClient(headers=self.headers, transport=transport, trust_env=trust_env) as cli:
            self._owned_preview_client = cli
            try:
                yield cli
            finally:
                self._owned_preview_client = None

    async def ensure_preview_aes_key(self) -> str:
        if cached := self._read_cached_key():
            return cached
        async with self._preview_client_scope():
            return await self._fetch_aes_key()

    async def probe_access(self) -> tuple[bool, str]:
        try:
            async with self._preview_client_scope():
                await self._fetch_aes_key()
        except KaobeiResponseError as exc:
            return False, str(exc)
        except httpx.HTTPError as exc:
            # httpx stringifies to its message only; the class name is the part
            # that tells a connect timeout apart from a proxy refusal.
            return False, f"kaobei access probe transport {type(exc).__name__}: {exc}"
        except ValueError as exc:
            return False, f"kaobei access probe aes key unusable: {exc}"
        return True, ""

    def get_aes_key(self) -> str:
        if cached := self._read_cached_key():
            return cached
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ensure_preview_aes_key())
        raise RuntimeError("kaobei get_aes_key cannot run inside a running event loop; await ensure_preview_aes_key()")

    async def preview_search(self, keyword: str, *, page: int = 1):
        url, frame = self.build_search_spec(keyword)
        url = Previewer.build_page_url(url, page, self.turn_page_info)
        resp = await self._preview_get(url, headers=self.ua_mapi, stage="preview_search", follow_redirects=True, timeout=12)
        payload = self._parse_preview_json(resp, stage="preview_search", request_url=url)
        targets = payload.get("results", {}).get("list", [])
        return await asyncio.to_thread(self.parser.parse_search_targets, targets, frame)

    async def preview_fetch_episodes(self, book, *, show_dhb=None):
        self._active_preview_client()
        path_word = book.url.rstrip("/").split("/")[-2]
        headers = {**self.ua, "Referer": f"https://{self.pc_domain}/comic/{path_word}"}
        parser_show_dhb = conf.kbShowDhb if show_dhb is None else show_dhb
        # The soft-ban is IP-level and decays over minutes, so mirror the page fetcher's
        # 60s x 12 risk-control window instead of a sub-minute backoff (09-04).
        risk_retries = max(self.preview_transport_retries, 12)
        risk_backoff_sec = 60
        last_exc = None
        for attempt in range(risk_retries + 1):
            await self.ensure_preview_aes_key()
            resp = await self._preview_get(book.url, headers=headers, stage="preview_fetch_episodes", follow_redirects=True, timeout=12)
            payload = self._parse_preview_json(resp, stage="preview_fetch_episodes", request_url=book.url)
            try:
                return await asyncio.to_thread(
                    self.parser.parse_episodes, payload["results"], book, url=book.url, show_dhb=parser_show_dhb,
                )
            except KaobeiResponseError as exc:
                last_exc = exc
                if exc.category != "empty_chapter_data":
                    raise
                if attempt >= risk_retries:
                    raise
                self.clear_aes_key()
                await asyncio.sleep(risk_backoff_sec)
        raise RuntimeError(f"kaobei preview_fetch_episodes exhausted retries without chapters: url={book.url}") from last_exc

    async def preview_fetch_pages(self, episode) -> list[str]:
        self._active_preview_client()
        # The api v3 `chapter` route returns the same image list the web chapter
        # page's contentKey decrypts to (46/46 measured against the decrypted
        # web list, 2026-09-15), as plain JSON on the un-walled api resource
        # family — the web chapter page is the risk-marked family (empty
        # contentKey shell), so this route is the stable path and needs no
        # contentKey/AES round trip. Evidence: test/__temp/kaobei_chapter_api_shape.py
        path_word = episode.url.rstrip("/").split("/")[-3]
        api_url = f"https://{self.api_domain}/api/v3/comic/{path_word}/chapter/{episode.id}?platform=1"
        resp = await self._preview_get(
            api_url, headers=self.ua_mapi, stage="preview_fetch_pages", follow_redirects=True, timeout=12,
        )
        payload = self._parse_preview_json(resp, stage="preview_fetch_pages", request_url=api_url)
        contents = await asyncio.to_thread(
            self.parser.parse_page_urls_from_chapter_json, payload, url=str(resp.url),
        )
        episode.pages = len(contents)
        return [item["url"] for item in contents]


class KaobeiUtils(_KaobeiContract, Utils, Previewer):
    parser = KaobeiParser
    reqer_cls = KaobeiReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf, owner=self)
        self.parser = self.reqer.parser

    @classmethod
    def display_meta(cls, *args, **kw) -> dict:
        return {
            "extra": " →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选，想多选请多开<br>"
            "拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算",
        }

    @classmethod
    def preview_client_config(cls, **context):
        return {
            "headers": cls.ua_mapi,
        }

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"retries": cls.preview_transport_retries}
