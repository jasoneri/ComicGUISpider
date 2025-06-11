import re
import os
from datetime import datetime, timedelta

import httpx
import asyncio
import aiofiles

from utils import temp_p

class Cookies:
    @staticmethod
    def to_str_(cookie):
        return '; '.join([f"{k}={v}" for k, v in cookie.items()])


class Req:
    book_hea = {}

    @classmethod
    def get_cli(cls, conf):
        if conf.proxies:
            return httpx.Client(
                headers=cls.book_hea,
                transport=httpx.HTTPTransport(proxy=f"http://{conf.proxies[0]}", retries=3))
        return httpx.Client(headers=cls.book_hea, trust_env=True)

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
    def get_uuid(cls, info):
        if hasattr(cls, "uuid_regex"):
            _identity = cls.uuid_regex.search(info).group(1)
        else:
            _identity = info
        return f"{cls.name}-{_identity}"


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
        domain_file = temp_p.joinpath(f"{cls.name}_domain.txt")
        current_time = datetime.now()
        if (domain_file.exists() and current_time - datetime.fromtimestamp(domain_file.stat().st_mtime) < timedelta(hours=48)):
            with open(domain_file, 'r', encoding='utf-8') as f:
                domain = f.read().strip()
            if domain:
                return domain
            else:
                os.remove(domain_file)
        loop = asyncio.get_event_loop()
        domain = loop.run_until_complete(cls.by_publish()) or loop.run_until_complete(cls.by_forever()) or None  # 控制顺序，例如永久页长期没恢复就前置从发布页获取
        if not cls.status_forever and not cls.status_publish:
            raise ConnectionError(f"无法获取 {cls.name} domain，方法均失效了，需要查看")
        return domain

    @classmethod
    async def test_aviable_domain(cls, domain):
        url = f"https://{domain}"
        async with httpx.AsyncClient(headers={**cls.headers, 'Referer': url},transport=httpx.AsyncHTTPTransport(retries=1),verify=False) as cli:
            resp = await cli.head(url, follow_redirects=True, timeout=4)
            if resp and str(resp.status_code).startswith('2'):
                return resp.url.host
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


tag_regex = re.compile(r"汉化|漢化|粵化|DL版|修正|中国|翻訳|翻译|翻譯|中文|後編|前編|カラー化|個人|" +
                       r"無修|重修|重嵌|机翻|機翻|整合|黑字|Chinese|Japanese|\[Digital]|vol|\[\d+]")


def set_author_ahead(title: str) -> str:
    author_ = re.findall(r"\[.*?]", title)
    if bool(re.search(r"[(（]", "".join(author_))):  # 优先选标签内带括号
        author_ = list(filter(lambda x: bool(re.search(r"[(（]", x)), author_))
    else:  # 采用排除法筛选
        author_ = list(filter(lambda x: not bool(tag_regex.search(x)), author_))
    if len(author_) > 1:
        if len(set(author_)) == 1:  # 去除重复标签
            author_ = [author_[0]]
        else:
            # logger.warning(f"匹配待改善 {author_=}")
            return title
    elif not author_:
        return title
    author = author_[0]
    return (author + title.replace(author, '').replace("  ", " ")).strip()
