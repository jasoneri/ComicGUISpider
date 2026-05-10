import re
import os
import functools
import typing as t
import pickle
import copy
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

import httpx
import asyncio
import aiofiles
from curl_cffi import requests as curl_requests

from assets import res
from utils.network.doh import build_http_transport
from utils import temp_p, get_loop, ori_path, conf
from utils.website.contracts import BrowserCookiePayload
from utils.website.runtime_context import PreviewTransportConfig


def build_proxy_transport(proxy_policy, proxies, is_async=True, **transport_kw):
    """根据站点 proxy_policy 构建 httpx transport。

    Args:
        proxy_policy: "direct" | "proxy"
        proxies: conf.proxies 列表
        is_async: True→AsyncHTTPTransport, False→HTTPTransport
        **transport_kw: 透传给 transport 构造（如 http2=True）

    Returns:
        (transport, trust_env) 元组
    """
    cls = httpx.AsyncHTTPTransport if is_async else httpx.HTTPTransport
    retries = transport_kw.pop("retries", 0)
    if proxy_policy == "direct" or not proxies:
        return cls(retries=retries, **transport_kw), False
    return cls(proxy=f"http://{proxies[0]}", retries=retries + 1, **transport_kw), False

class Cache:
    def __init__(self, cache_f):
        self.cache_f = cache_f
        self.flag = None
        self.val = None
        self.state = None

    @staticmethod
    def _is_expired(cache_path, expiry_time: t.Union[int, datetime, str, callable]) -> bool:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        match expiry_time:
            case int():
                return now - file_time > timedelta(hours=expiry_time)
            case datetime():
                return now > expiry_time
            case str() if expiry_time == "daily":
                return file_time < today_start
            case _ if callable(expiry_time):
                dynamic_expiry = expiry_time()
                return now > dynamic_expiry
        return True

    def with_expiry(self, expiry_time: t.Union[int, datetime, str, callable]=168, write_in=False):
        """缓存有效期装饰器

        Args:
            expiry_time: 过期时间设置
                - int: 小时数，如48表示48小时后过期
                - datetime: 具体的过期时间点
                - str: 预定义策略，如"daily"表示每日23:59:59过期
                - callable: 返回datetime的函数，用于动态计算过期时间
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if cache_exists_flag and not expiry_flag:
                    if cache_path.suffix == '.pkl':
                        with open(cache_path, 'rb') as f:
                            cached_data = pickle.load(f)
                    elif cache_path.suffix in {'.db', '.sqlite', '.sqlite3'}:
                        cached_data = cache_path
                    else:
                        with open(cache_path, 'r', encoding='utf-8') as f:
                            cached_data = f.read().strip()

                    if cached_data:
                        self.flag = "validate"
                        self.val = cached_data
                        self.state = "validate"
                        return cached_data
                    else:
                        os.remove(cache_path)

                result = func(*args, **kwargs)
                self.state = "expired" if cache_exists_flag else "missing"
                if result is not None and write_in:
                    if cache_path.exists():
                        os.remove(cache_path)  # remark: 解决相同内容写入却不更新最后访问时间导致的缓存失效恶性循环
                    if cache_path.suffix == '.pkl':
                        with open(cache_path, 'wb') as f:
                            pickle.dump(result, f)
                    else:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            f.write(str(result))
                    self.flag = "new"
                    self.state = "new"
                else:
                    self.flag = "new"
                self.val = result
                return result
            return wrapper

        cache_path = temp_p.joinpath(self.cache_f)
        cache_exists_flag = cache_path.exists()
        expiry_flag = True
        if not cache_exists_flag:
            return decorator

        expiry_flag = self._is_expired(cache_path, expiry_time)
        return decorator

    def run(self, func, expiry_time=168, write_in=False):
        """动态应用缓存装饰器并执行函数
        每次调用都会重新检查缓存状态，适用于多进程场景
        """
        return self.with_expiry(expiry_time, write_in)(func)()

    def with_error_cleanup(self):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if cache_path.exists():
                        os.remove(cache_path)
                    raise RuntimeError(f"{cache_path.stem} 失效，已删除<br>出错时优先看下方日志(若有)，次之可试重启 CGS 以更新缓存")
            return wrapper
        cache_path = temp_p.joinpath(self.cache_f)
        return decorator


class Cookies:
    cookies_field = set()

    @staticmethod
    def to_str_(cookie):
        return '; '.join([f"{k}={v}" for k, v in cookie.items()])


class Req:
    book_hea = {}
    book_url_regex = ""
    proxy_policy= None
    _TRANSPORT_PARAMS = frozenset(('http2', 'verify', 'cert', 'limits'))

    def __init__(self, _conf):
        ...

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        client_class = httpx.AsyncClient if is_async else httpx.Client
        transport_kw = {k: kwargs.pop(k) for k in cls._TRANSPORT_PARAMS if k in kwargs}
        transport, trust_env = build_http_transport(
            cls.proxy_policy, _conf.proxies,
            doh_url=getattr(_conf, "doh_url", ""), is_async=is_async, **transport_kw,
        )
        base_kwargs = {
            'headers': cls.book_hea,
            'transport': transport,
            'trust_env': trust_env,
        }
        base_kwargs.update(kwargs)
        return client_class(**base_kwargs)

    def bind_preview_runtime(self, *, owner, site_config, preview_client: httpx.AsyncClient | None = None):
        self.owner = owner
        self.site_config = site_config
        self.transport = site_config.transport
        if site_config.domain:
            self.domain = site_config.domain
        if site_config.cookies:
            self.cookies = copy.deepcopy(site_config.cookies)
        if site_config.custom_map:
            self.custom_map = copy.deepcopy(site_config.custom_map)
        if preview_client is not None:
            self.preview_client = preview_client
        return self

    def _require_preview_owner(self):
        owner = getattr(self, "owner", None)
        if owner is None:
            raise RuntimeError(f"{type(self).__name__} preview flow requires provider owner")
        if not isinstance(owner, Previewer):
            raise TypeError(f"{type(self).__name__} preview owner must implement Previewer")
        return owner

    def _require_preview_site_config(self):
        site_config = getattr(self, "site_config", None)
        if site_config is None:
            raise RuntimeError(f"{type(self).__name__} preview flow requires bound site_config")
        return site_config

    def preview_site_kwargs(self) -> dict[str, t.Any]:
        return self._require_preview_site_config().as_provider_kwargs()

    def set_preview_client(self, preview_client: httpx.AsyncClient | None):
        self.preview_client = preview_client
        return preview_client

    def create_preview_client(self) -> httpx.AsyncClient:
        owner = self._require_preview_owner()
        site_config = self._require_preview_site_config()
        site_kw = self.preview_site_kwargs()
        client_kw = dict(type(owner).preview_client_config(**site_kw) or {})
        transport_kw = dict(type(owner).preview_transport_config() or {})
        transport, trust_env = build_http_transport(
            getattr(type(owner), "proxy_policy", "proxy"),
            list(site_config.transport.proxies),
            doh_url=site_config.transport.doh_url,
            is_async=True,
            **transport_kw,
        )
        base_kwargs = {
            "transport": transport,
            "follow_redirects": True,
            "trust_env": trust_env,
            "headers": None,
        }
        base_kwargs.update(client_kw)
        return httpx.AsyncClient(**base_kwargs)

    def ensure_preview_client(self) -> httpx.AsyncClient:
        preview_client = getattr(self, "preview_client", None)
        if preview_client is None:
            preview_client = self.set_preview_client(self.create_preview_client())
        return preview_client

    async def aclose_preview_client(self):
        preview_client = getattr(self, "preview_client", None)
        self.preview_client = None
        if preview_client is not None:
            await preview_client.aclose()

    def _raise_preview_runtime_contract_error(self, method_name: str) -> t.NoReturn:
        raise RuntimeError(f"{type(self).__name__} reqer.{method_name}() is required for the preview runtime owner contract")

    async def preview_search(self, keyword: str, *, page: int = 1):
        self._raise_preview_runtime_contract_error("preview_search")

    async def preview_fetch_episodes(self, book):
        self._raise_preview_runtime_contract_error("preview_fetch_episodes")

    async def preview_fetch_pages(self, episode):
        self._raise_preview_runtime_contract_error("preview_fetch_pages")

    def parse_search(self, resp_text):
        """parse search_page
        由于 domain 关系，需要带状态
        """

    @classmethod
    def parse_book(cls, resp_text):
        """parse book-page"""

    async def download_cover_bytes(self, tasks_obj, *, browser_headers: dict[str, str] | None = None) -> bytes:
        cover_request_timeout = 15
        browser_image_accept = "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5"

        def _require_preview_client() -> httpx.AsyncClient:
            return self.ensure_preview_client()
        def _require_cover_request_owner():
            owner = getattr(self, "owner", None)
            if owner is None:
                raise RuntimeError(f"{type(self).__name__} cover preload requires provider owner")
            return owner
        def _normalize_cover_headers(headers: httpx.Headers) -> dict[str, str]:
            normalized = dict(headers.items())
            return {k: v for k, v in normalized.items() if k.casefold() != "host"}
        def _cover_request_referer(tasks_obj) -> str | None:
            return Previewer.build_referer_url(
                getattr(tasks_obj, "title_url", None),
                request_url=getattr(tasks_obj, "cover_url", None),
            )
        def build_cover_headers() -> httpx.Headers:
            preview_client = _require_preview_client()
            owner = _require_cover_request_owner()
            preview_client_config = getattr(type(owner), "preview_client_config", None)
            if not callable(preview_client_config):
                raise RuntimeError(f"{type(self).__name__} cover preload requires provider owner.preview_client_config()")
            site_config = getattr(self, "site_config", None)
            site_kw = site_config.as_provider_kwargs() if site_config is not None else {}
            owner_headers = dict((preview_client_config(**site_kw) or {}).get("headers", {}) or {})
            headers = httpx.Headers(preview_client.headers)
            headers.update(owner_headers)
            headers.update(dict(browser_headers or {}))
            if "accept" not in headers or "image/" not in headers.get("accept", ""):
                headers["Accept"] = browser_image_accept
            referer_url = _cover_request_referer(tasks_obj)
            if referer_url and "referer" not in headers:
                headers["Referer"] = referer_url
            return headers
        def _cover_request_transport() -> str:
            return str(getattr(type(_require_cover_request_owner()), "cover_preload_transport", "httpx") or "httpx")
        def _cover_request_timeout() -> float:
            return float(getattr(type(_require_cover_request_owner()), "cover_preload_timeout", cover_request_timeout) or cover_request_timeout)
        def _cover_request_via_curl(headers: dict[str, str], timeout: float) -> bytes:
            owner_cls = type(_require_cover_request_owner())
            request_headers = dict(headers)
            referer = request_headers.pop("Referer", None) or request_headers.pop("referer", None)
            request_kw = {
                "headers": request_headers or None, "referer": referer, "timeout": timeout,
                "verify": dict(owner_cls.preview_transport_config() or {}).get("verify", True),
            }
            impersonate = getattr(owner_cls, "cover_preload_impersonate", None)
            if impersonate:
                request_kw["impersonate"] = impersonate
            proxy_policy = getattr(owner_cls, "cover_preload_proxy_policy", getattr(owner_cls, "proxy_policy", "proxy"))
            proxies = list(getattr(getattr(self, "site_config", None), "transport", PreviewTransportConfig()).proxies or ())
            if proxy_policy == "proxy":
                if not proxies:
                    raise RuntimeError(f"{owner_cls.__name__} cover preload requires proxies when proxy mode is enabled")
                request_kw["proxy"] = f"http://{proxies[0]}"
            resp = curl_requests.get(tasks_obj.cover_url, allow_redirects=True, **request_kw)
            resp.raise_for_status()
            return resp.content

        cover_headers = build_cover_headers()
        normalized_headers = _normalize_cover_headers(cover_headers)
        timeout = _cover_request_timeout()
        if _cover_request_transport() == "curl_cffi":
            return await asyncio.to_thread(_cover_request_via_curl, normalized_headers, timeout)
        preview_client = _require_preview_client()
        resp = await preview_client.get(tasks_obj.cover_url, headers=normalized_headers, follow_redirects=True, timeout=timeout)
        resp.raise_for_status()
        return resp.content


class Utils:
    name = ""
    headers = {}
    proxy_policy = "proxy"

    @classmethod
    def get_uuid(cls, info):
        return f"{cls.name}-{info}"

    @classmethod
    def display_meta(cls, *args, **kw) -> dict:
        return {}


@dataclass(slots=True)
class PreviewRequestSpec:
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    data: t.Optional[dict[str, t.Any]] = None
    state: dict[str, t.Any] = field(default_factory=dict)
    timeout: float = 12.0

class Previewer:
    """Preview 能力 Mixin - 需要支持 normal preview 的站点继承此类"""
    # cover_preload_via_http = False
    browser_referer_mode: str | None = None
    browser_cookie_set_enabled = False
    cover_preload_transport: str = "httpx"
    cover_preload_timeout: float = 15.0
    cover_preload_proxy_policy: str | None = None
    cover_preload_impersonate: str | None = None

    @classmethod
    def preview_client_config(cls, **context) -> dict:
        return {}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {}

    @classmethod
    def build_browser_referer_url(cls, *, domain: str | None = None) -> str | None:
        mode = getattr(cls, "browser_referer_mode", None)
        if not mode:
            return None
        if mode == "domain_origin":
            origin = cls.preview_origin(domain)
            if origin is None:
                raise ValueError(f"{cls.__name__} browser referer requires domain")
            return origin
        if mode == "domain_origin_slash":
            origin = cls.preview_origin(domain)
            if origin is None:
                raise ValueError(f"{cls.__name__} browser referer requires domain")
            return f"{origin}/"
        if mode == "provider_index":
            referer_url = str(getattr(cls, "index", "") or "").strip()
            if not referer_url:
                raise ValueError(f"{cls.__name__} browser referer requires provider index")
            return referer_url
        raise ValueError(f"{cls.__name__} unsupported browser referer mode: {mode!r}")

    @classmethod
    def build_browser_cookie_sets(
        cls,
        *,
        cookies: dict[str, str],
        domain: str | None = None,
        referer_url: str | None = None,
    ) -> tuple[BrowserCookiePayload, ...]:
        if not getattr(cls, "browser_cookie_set_enabled", False) or not cookies:
            return ()
        normalized_domain = str(domain or "").strip()
        if not normalized_domain:
            raise ValueError(f"{cls.__name__} browser cookie set requires domain")
        normalized_referer = str(referer_url or "").strip()
        if not normalized_referer:
            raise ValueError(f"{cls.__name__} browser cookie set requires referer_url")
        return (BrowserCookiePayload(values=cookies, domain=normalized_domain, url=normalized_referer),)

    @staticmethod
    def preview_origin(domain: str | None) -> str | None:
        if not domain:
            return None
        parsed = urlparse(domain)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return f"https://{domain}"

    @staticmethod
    def build_referer_url(referer_url: str | None, *, request_url: str | None = None, default_scheme: str = "https") -> str | None:
        raw_referer = str(referer_url or "").strip()
        if not raw_referer:
            return None
        request_scheme = ""
        if request_url:
            request_parts = urlparse(str(request_url).strip())
            request_scheme = str(request_parts.scheme or "").strip().casefold()
            if request_scheme and request_scheme not in {"http", "https"}:
                return None
        final_default_scheme = request_scheme or default_scheme
        referer_parts = urlparse(raw_referer if "://" in raw_referer else f"{final_default_scheme}://{raw_referer}")
        referer_host = str(referer_parts.netloc or referer_parts.path or "").strip()
        if not referer_host:
            return None
        referer_scheme = str(referer_parts.scheme or "").strip().casefold()
        final_scheme = referer_scheme if referer_scheme in {"http", "https"} else final_default_scheme
        referer_path = str(referer_parts.path or "").strip() or "/"
        return urlunparse((final_scheme, referer_host, referer_path, "", str(referer_parts.query or "").strip(), ""))

    @classmethod
    def build_site_headers(
        cls, domain: str, base_headers: dict[str, str] | None = None, *, referer_url: str | None = None, 
        cookies: dict[str, str] | None = None, cookie_serializer: t.Callable[[dict[str, str]], str] | None = None,
    ) -> dict[str, str]:
        headers = {"Host": domain, **(base_headers or {})}
        referer = cls.build_referer_url(referer_url)
        if referer:
            headers["Referer"] = referer
        if cookies and cookie_serializer is not None:
            cookie_str = cookie_serializer(cookies)
            if cookie_str:
                headers["cookie"] = cookie_str
        return headers

    @classmethod
    def normalize_preview_resource(cls, value: str | None, *, domain: str | None = None, default_scheme: str = "https") -> str | None:
        raw_value = str(value or "").strip()
        if not raw_value:
            return value
        if raw_value.startswith("///"):
            raw_value = f"//{raw_value.lstrip('/')}"
        parsed = urlparse(raw_value)
        if parsed.scheme in {"http", "https"}:
            return raw_value
        if raw_value.startswith("//"):
            return f"{default_scheme}:{raw_value}"
        if parsed.scheme:
            return raw_value
        origin = cls.preview_origin(domain)
        if origin is None:
            return raw_value
        prefix = "" if raw_value.startswith("/") else "/"
        return f"{origin}{prefix}{raw_value}"

    @classmethod
    def normalize_preview_fields(
        cls, item, *, domain: str | None = None,
        attrs: tuple[str, ...] = ("preview_url", "url", "img_preview"),
    ):
        for attr in attrs:
            value = getattr(item, attr, None)
            normalized = cls.normalize_preview_resource(value, domain=domain)
            if normalized != value:
                setattr(item, attr, normalized)
        return item

    @staticmethod
    def merge_search_mappings(base: dict | None, custom: dict | None) -> dict:
        merged = copy.deepcopy(base or {})
        merged.update(copy.deepcopy(custom or {}))
        return merged

    @classmethod
    def normalize_mapping_url(cls, domain: str, mapping_value) -> str:
        parsed = urlparse(str(mapping_value))
        origin = cls.preview_origin(domain)
        if origin is None:
            raise ValueError(f"{cls.__name__} requires domain for mapping search")
        return f"{origin}{parsed.path}"

    @classmethod
    def build_page_url(cls, url: str, page: int, page_info: t.Optional[tuple]) -> str:
        page = max(1, int(page or 1))
        if page <= 1 or not page_info:
            return str(url)
        from utils.processed_class import Url
        return str(Url(str(url)).set_next(*page_info).jump(page))

    @classmethod
    def build_basic_search_request(
        cls,
        keyword: str,
        *,
        page: int = 1, domain: str, search_url_head: str, turn_page_info: t.Optional[tuple], 
        turn_page_search: t.Optional[str] = None, mappings: dict | None = None, 
        custom_map: dict | None = None, headers: dict | None = None, state: dict | None = None,
    ) -> PreviewRequestSpec:
        merged = cls.merge_search_mappings(mappings, custom_map)
        if keyword in merged:
            base_url = cls.normalize_mapping_url(domain, merged[keyword])
            page_info = turn_page_info
        else:
            base_url = f"{search_url_head}{keyword}"
            page_info = (turn_page_search,) if turn_page_search else turn_page_info
        return PreviewRequestSpec(
            url=cls.build_page_url(base_url, page, page_info),
            headers=dict(headers or {}),
            state=dict(state or {}),
        )

    @classmethod
    async def perform_preview_request(cls, client, spec: PreviewRequestSpec):
        request_kw = {}
        if spec.headers:
            request_kw["headers"] = spec.headers
        if spec.data is not None:
            request_kw["data"] = spec.data
        resp = await client.request(spec.method, spec.url, follow_redirects=True, timeout=spec.timeout, **request_kw)
        resp.raise_for_status()
        return resp


class EroUtils(Utils):
    uuid_regex = None

    @classmethod
    def get_uuid(cls, info, only_id=False):
        if hasattr(cls, "uuid_regex"):
            try:
                _identity = cls.uuid_regex.search(info).group(1)
            except AttributeError as e:
                print(f"{cls.uuid_regex}\n{info}")
                raise e
        else:
            _identity = info
        return f"{cls.name}-{_identity}" if not only_id else _identity


class DomainUtils(Utils):
    domain = None
    forever_url = ""
    publish_url = ""
    status_forever = True
    status_publish = True
    publish_headers = {}
    EXPIRE = 168

    @classmethod
    async def by_forever(cls):
        if not cls.forever_url:
            return None
        try:
            transport, trust_env = build_proxy_transport(cls.proxy_policy, conf.proxies)
            async with httpx.AsyncClient(headers=cls.headers, follow_redirects=True, transport=transport, trust_env=trust_env) as cli:
                resp = await cli.head(cls.forever_url)
                return re.search(r"https?://(.*)/?", str(resp.request.url)).group(1)
        except httpx.ConnectError:
            cls.status_forever = False
            print(f"永久网址[{cls.forever_url}]失效了")  # logger.warning()
            return None

    @classmethod
    async def by_publish(cls):
        e = None
        if not cls.publish_url:
            return None
        transport, trust_env = build_proxy_transport(cls.proxy_policy, conf.proxies, http2=True, retries=5)
        async with httpx.AsyncClient(headers=cls.publish_headers or cls.headers, transport=transport, trust_env=trust_env) as cli:
            try:
                resp = await cli.get(cls.publish_url)
                resp.raise_for_status()
                if str(resp.status_code).startswith('2'):
                    return await cls.parse_publish(resp.text)
            except httpx.HTTPError as _e:
                e = _e
            cls.status_publish = False
            raise e or ConnectionError(
                res.SPIDER.PUBLISH_INVALID % (cls.publish_url, str(ori_path.joinpath(f'__temp/{cls.name}_domain.txt')))
            )

    @classmethod
    def peek_cached_domain(cls):
        cls.cachef = getattr(cls, "cachef", Cache(f"{cls.name}_domain.txt"))
        cached = cls.cachef.run(lambda: None, cls.EXPIRE)
        if isinstance(cached, str):
            cached = cached.strip()
            if cached:
                return cached
        return None

    @classmethod
    def get_domain(cls):
        def _():
            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(cls._get_domain_thread).result()
            except RuntimeError:
                return cls._get_domain_thread()

        cached = cls.peek_cached_domain()
        if cached:
            return cached
        cls.cachef = getattr(cls, "cachef", Cache(f"{cls.name}_domain.txt"))
        return cls.cachef.run(_, cls.EXPIRE, write_in=True)

    @classmethod
    def _get_domain_thread(cls):
        loop = get_loop()
        try:
            domain = loop.run_until_complete(cls.by_publish()) or loop.run_until_complete(cls.by_forever())
            if not domain and not cls.status_forever and not cls.status_publish:
                raise ConnectionError(f"无法获取 {cls.name} domain，方法均失效了，需要查看")
            return domain
        finally:
            loop.close()

    @classmethod
    async def test_aviable_domain(cls, domain):
        url = f"https://{domain}"
        try:
            transport, trust_env = build_proxy_transport(cls.proxy_policy, conf.proxies, retries=1, verify=False)
            async with httpx.AsyncClient(headers={**cls.headers, 'Referer': url}, transport=transport, trust_env=trust_env) as cli:
                resp = await cli.head(url, follow_redirects=True, timeout=4)
                if resp and str(resp.status_code).startswith('2'):
                    return resp.url.host
        except Exception as e:
            return None
        return None

    @classmethod
    async def parse_publish(cls, html):
        domain = await cls.parse_publish_(html)
        async with aiofiles.open(temp_p.joinpath(f"{cls.name}_domain.txt"), 'w', encoding='utf-8') as f:
            await f.write(domain)
        return domain

    @classmethod
    async def parse_publish_(cls, html_text):
        ...
