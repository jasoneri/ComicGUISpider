import re
import os
import functools
import typing as t
from datetime import datetime, timedelta

import httpx
import asyncio
import aiofiles

from utils import temp_p, get_loop

class Cache:
    def __init__(self, cache_f):
        self.cache_f = cache_f
        self.flag = None
        self.val = None

    def with_expiry(self, expiry_time: t.Union[int,datetime]=48, write_in=False):
        """缓存有效期装饰器"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if cache_exists_flag and not expiry_flag:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cached_data = f.read().strip()
                    if cached_data:
                        self.flag = "validate"
                        self.val = cached_data
                        return cached_data
                    else:
                        os.remove(cache_path)
                result = func(*args, **kwargs)
                if result is not None and write_in:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        f.write(str(result))
                self.flag = "new"        
                self.val = result
                return result
            return wrapper
        cache_path = temp_p.joinpath(self.cache_f)
        cache_exists_flag = cache_path.exists()
        expiry_flag = True
        if not cache_exists_flag:
            return decorator
        match expiry_time:
            case int():
                expiry_flag = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime) > timedelta(hours=expiry_time)
            case datetime():
                expiry_flag = datetime.fromtimestamp(cache_path.stat().st_mtime) > expiry_time
        return decorator

    def with_error_cleanup(self):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if cache_path.exists():
                        os.remove(cache_path)
                    raise RuntimeError(f"{cache_path.stem} 失效，已删除<br>重启 CGS 以更新缓存")
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

    @classmethod
    def get_cli(cls, conf, is_async=False, **kwargs):
        client_class = httpx.AsyncClient if is_async else httpx.Client
        transport_class = httpx.AsyncHTTPTransport if is_async else httpx.HTTPTransport
        if conf.proxies:
            base_kwargs = {
                'headers': cls.book_hea,
                'transport': transport_class(proxy=f"http://{conf.proxies[0]}", retries=3)
            }
        else:
            base_kwargs = {'headers': cls.book_hea, 'trust_env': True}
        base_kwargs.update(kwargs)
        return client_class(**base_kwargs)
    book_url_regex = ""

    @classmethod
    def parse_book(cls):
        ...


class Utils:
    name = ""
    headers = {}

    @classmethod
    def get_uuid(cls, info):
        return f"{cls.name}-{info}"


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
    forever_url = ""
    publish_url = ""
    status_forever = True
    status_publish = True
    publish_headers = {}

    @classmethod
    async def by_forever(cls):
        if not cls.forever_url:
            return None
        try:
            async with httpx.AsyncClient(headers=cls.headers, follow_redirects=True) as cli:
                resp = await cli.head(cls.forever_url)
                return re.search(r"https?://(.*)/?", str(resp.request.url)).group(1)
        except httpx.ConnectError:
            cls.status_forever = False
            print(f"永久网址[{cls.forever_url}]失效了")  # logger.warning()
            return None

    @classmethod
    async def by_publish(cls):
        if not cls.publish_url:
            return None
        async with httpx.AsyncClient(headers=cls.publish_headers or cls.headers, 
                transport=httpx.AsyncHTTPTransport(retries=5)) as cli:
            try:
                resp = await cli.get(cls.publish_url)
                resp.raise_for_status()
                if str(resp.status_code).startswith('2'):
                    return await cls.parse_publish(resp.text)
            except httpx.HTTPError as e:
                ...
            cls.status_publish = False
            print(f"发布页获取[{cls.publish_url}]失效了")  # logger.warning()
            return None

    @classmethod
    def get_domain(cls):
        def _():
            loop = get_loop()
            domain = loop.run_until_complete(cls.by_publish()) or loop.run_until_complete(cls.by_forever()) or None  # 控制顺序，例如永久页长期没恢复就前置从发布页获取
            if not cls.status_forever and not cls.status_publish:
                raise ConnectionError(f"无法获取 {cls.name} domain，方法均失效了，需要查看")
            return domain
        cls.cachef = getattr(cls, "cachef", Cache(f"{cls.name}_domain.txt"))
        domain = cls.cachef.with_expiry(48, write_in=True)(_)()
        return domain

    @classmethod
    async def test_aviable_domain(cls, domain):
        url = f"https://{domain}"
        try:
            async with httpx.AsyncClient(headers={**cls.headers, 'Referer': url},transport=httpx.AsyncHTTPTransport(retries=1),verify=False) as cli:
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
    def parse_publish_(cls, html):
        ...


def retry(func, retry_limit, *args, retry_times=0, raise_error=False, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        retry_times += 1
        if retry_times <= retry_limit:
            return retry(func, retry_limit, *args, retry_times=retry_times, raise_error=raise_error, **kwargs)
        if raise_error:
            raise e

