import re
from datetime import datetime, timedelta
import httpx
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
                proxies={"https://": f"http://{conf.proxies[0]}"},
                transport=httpx.HTTPTransport(retries=3))
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
    forever_url = ""
    publish_url = ""
    status_forever = True
    status_publish = True
    uuid_regex = NotImplementedError

    @classmethod
    def by_forever(cls):
        if not cls.forever_url:
            return None
        try:
            resp = httpx.head(cls.forever_url, headers=cls.headers, follow_redirects=True)
        except httpx.ConnectError:
            cls.status_forever = False
            print(f"永久网址[{cls.forever_url}]失效了")  # logger.warning()
        else:
            return re.search(r"https?://(.*)/?", str(resp.request.url)).group(1)

    @classmethod
    def by_publish(cls):
        if not cls.publish_url:
            return None
        with httpx.Client(headers=cls.headers) as cli:
            resp = retry(cli.get, retry_limit=8, raise_error=True, url=cls.publish_url, follow_redirects=True)
        if str(resp.status_code).startswith('2'):
            return cls.parse_publish(resp.text)
        else:
            cls.status_publish = False
            print(f"发布页获取[{cls.publish_url}]失效了")  # logger.warning()

    @classmethod
    def get_domain(cls):
        domain_file = temp_p.joinpath(f"{cls.name}_domain.txt")
        current_time = datetime.now()
        if (domain_file.exists() and
                current_time - datetime.fromtimestamp(domain_file.stat().st_mtime) < timedelta(hours=24)):
            with open(domain_file, 'r', encoding='utf-8') as f:
                domain = f.read().strip()
        else:
            domain = cls.by_publish() or cls.by_forever() or None  # 控制顺序，例如永久页长期没恢复就前置从发布页获取
        if not cls.status_forever and not cls.status_publish:
            raise ConnectionError(f"无法获取 {cls.name} domain，方法均失效了，需要查看")
        return domain

    @classmethod
    def parse_publish(cls, html):
        domain = cls.parse_publish_(html)
        with open(temp_p.joinpath(f"{cls.name}_domain.txt"), 'w', encoding='utf-8') as f:
            f.write(domain)
        return domain

    @classmethod
    def parse_publish_(cls, html):
        ...

    @classmethod
    def get_uuid(cls, info):
        _identity = cls.uuid_regex.search(info).group(1)
        return f"{cls.name}-{_identity}"


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
