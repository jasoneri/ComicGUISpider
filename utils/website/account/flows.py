"""站点登录私有数据模块 (收藏列表 / 签到), 与 provider class 解耦。

与 utils/website/login/ 同构 (带状态设计): 每个目标站点一个独立模块
(jm.py / ehentai.py / ...), 声明式定义 FavoritesSpec (收藏列表提取) 与
CheckinSpec (每日签到), 消费方只传 provider_name 状态标识, 经
resolve_favorites_spec() / resolve_checkin_spec() 解析。

对齐竞品: jmcomic 官方库 (download_favorite / subscribe_album) +
comic-auto-sign-bot (自动签到)。
"""

from __future__ import annotations

import typing as t
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from utils import conf as _default_conf
from utils.website.login.flows import _read_site_cookies  # 复用 cookie 读取 (同构)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
)

_MAX_FAVORITES_PAGES = 10  # 收藏分页抓取上限 (防失控)


@dataclass(frozen=True, slots=True)
class FavoritesSpec:
    """站点收藏列表提取定义 (登录态下)。

    list_url 支持 {page} 占位符 (分页循环替换); 若含 {username} 占位符,
    由执行器经 username_from_cookies 从已保存 cookies 解析 (jm 网页端
    收藏页 /user/{username}/favorite/albums 对齐官方库 favorite_folder)。

    产出必须尽量对齐搜索 parse_search_item: 同 provider BookInfo 类型 +
    img_preview / pages, 才能进正式 preview_format 封面与下载链路。
    """

    provider_name: str
    list_url: str
    page_start: int = 1
    method: str = "GET"
    item_selector: str = ""      # 条目选择器 (scrapy Selector CSS)
    title_selector: str = ""     # 标题选择器 (相对 item)
    url_selector: str = ""       # 书 URL 选择器 (相对 item, 相对地址自动 urljoin)
    # 封面 / 页数: 与搜索结果卡片同字段, 缺省空则仅 title+url 骨架 (下载可能仍可走 spider)
    cover_selector: str = ""
    pages_selector: str = ""     # 文本或属性; 从中抽取数字
    extra_params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    # False: 不走 conf.proxies (jm 等 CF 绑定场景常需直连, 对齐站点搜索习惯)
    use_proxy: bool = True
    # {username} 占位符解析: 从已保存 cookies 提取用户名 (jm remember_id
    # PHP serialize 场景), 返回 str; 解析失败返回 None → 拉取返回空列表。
    username_from_cookies: t.Callable[[dict[str, str]], str | None] | None = None
    # {domain} 占位符解析: 站点域名机制 (jm: temp_p/jm_domain.txt 缓存 +
    # publish/forever 动态解析, 见 DomainUtils), 返回 str; 失败返回 None。
    # 无代理直连时用缓存域名可避开 Cloudflare 挑战, 不得写死静态域。
    domain_resolver: t.Callable[[], str | None] | None = None


@dataclass(frozen=True, slots=True)
class CheckinSpec:
    """站点每日签到定义 (登录态下)。

    dynamic_params: 参数名 → JS 表达式 (简单字符串计算), 如 jm 的
    code 动态验证码由页面 JS 按日期时间生成。
    """

    provider_name: str
    url: str
    method: str = "POST"
    params: dict = field(default_factory=dict)   # form 参数
    data: dict = field(default_factory=dict)     # json body
    headers: dict = field(default_factory=dict)
    dynamic_params: dict = field(default_factory=dict)
    success_contains: tuple[str, ...] = ()       # 成功特征
    already_contains: tuple[str, ...] = ()       # 已签到特征


@dataclass(slots=True)
class CheckinResult:
    """签到执行结果。"""

    ok: bool = False
    already: bool = False
    message: str = ""
    provider: str = ""


def _css_first(item, selector: str) -> str:
    if not selector:
        return ""
    # Support comma-separated fallbacks (cover data-src, then src).
    for part in (chunk.strip() for chunk in selector.split(",") if chunk.strip()):
        value = item.css(part).get()
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_pages_value(raw: str) -> int | None:
    if not raw:
        return None
    import re

    match = re.search(r"(\d+)", str(raw))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_favorites_page(
    html: str, spec: FavoritesSpec, base_url: str,
) -> list[dict]:
    """解析收藏页 HTML → [{title, url, cover, pages}, ...] (纯函数, 便于单测)。

    选择器均相对 item; title/url/cover 支持 ::attr / ::text。
    """
    from scrapy import Selector

    doc = Selector(text=html)
    items = doc.css(spec.item_selector) if spec.item_selector else doc
    results: list[dict] = []
    for item in items:
        title = _css_first(item, spec.title_selector)
        url = _css_first(item, spec.url_selector)
        if not url:
            continue
        # Skip empty table chrome rows (ehentai itg header etc.)
        if not title and not url:
            continue
        cover = _css_first(item, spec.cover_selector)
        pages_raw = ""
        if spec.pages_selector:
            # Prefer text nodes containing "page(s)" / bare digits (eh glthumb).
            for text in item.css(spec.pages_selector).getall():
                lowered = str(text).lower()
                if "page" in lowered or str(text).strip().isdigit():
                    pages_raw = str(text)
                    break
            if not pages_raw:
                pages_raw = _css_first(item, spec.pages_selector)
        results.append(
            {
                "title": title,
                "url": urljoin(base_url, str(url)),
                "cover": urljoin(base_url, cover) if cover and not cover.startswith(("http://", "https://", "data:")) else cover,
                "pages": _parse_pages_value(pages_raw),
            }
        )
    return results


def run_fetch_favorites(
    provider_name: str,
    *,
    conf_state=_default_conf,
) -> list:
    """登录态拉取收藏列表 → provider BookInfo 列表 (对齐搜索卡片字段)。

    尽量带 img_preview / pages, 以便正式 preview_format 出图 + BOOK 下载。
    解析失败 → 返回空列表 (不抛异常)。构造走 _book_from_entry (站点专用类型)。
    """
    spec = resolve_favorites_spec(provider_name)
    if spec is None:
        return []
    cookies = _read_site_cookies(conf_state, provider_name)
    if not cookies:
        return []
    transport = None
    if spec.use_proxy:
        proxies = tuple(str(p) for p in (getattr(conf_state, "proxies", None) or ()) if p)
        if proxies:
            transport = httpx.HTTPTransport(proxy=f"http://{proxies[0]}", retries=1)
    headers = {"User-Agent": _DEFAULT_UA}
    headers.update(spec.headers)
    books: list = []
    seen_urls: set[str] = set()
    try:
        with httpx.Client(
            transport=transport, timeout=20.0, follow_redirects=True, headers=headers,
            cookies=cookies,
        ) as client:
            for page in range(spec.page_start, spec.page_start + _MAX_FAVORITES_PAGES):
                url = _resolve_list_url(spec, cookies, page)
                if url is None:
                    # {username} 占位符存在但无法从 cookies 解析 → 视为无登录态
                    break
                response = client.request(spec.method, url, params=spec.extra_params)
                response.raise_for_status()
                entries = _parse_favorites_page(response.text, spec, url)
                # 去重终止: 空页或整页重复 (ehentai 越界页返回第一页内容)
                fresh = [entry for entry in entries if entry["url"] not in seen_urls]
                if not fresh:
                    break
                seen_urls.update(entry["url"] for entry in fresh)
                books.extend(_build_book_infos(spec.provider_name, fresh))
    except Exception:
        return books or []
    return books


def _resolve_list_url(spec: FavoritesSpec, cookies: dict[str, str], page: int) -> str | None:
    """构造分页 URL: 替换 {page}; {username} 占位符经 spec 声明的
    username_from_cookies 从 cookies 解析; {domain} 占位符经 spec 声明的
    domain_resolver 解析 (站点域名机制, 非写死)。任一步失败返回 None。"""
    url_template = spec.list_url
    kwargs: dict[str, str | int] = {"page": page}
    if "{username}" in url_template:
        if spec.username_from_cookies is None:
            return None
        username = spec.username_from_cookies(cookies)
        if not username:
            return None
        kwargs["username"] = username
    if "{domain}" in url_template:
        if spec.domain_resolver is None:
            return None
        domain = spec.domain_resolver()
        if not domain:
            return None
        kwargs["domain"] = domain
    return url_template.format(**kwargs)


def _build_book_infos(provider_name: str, entries: list[dict]) -> list:
    """收藏条目 → provider BookInfo (JmBookInfo/EhBookInfo/...), 填封面与页数。"""
    from utils.tray.subscription_runner import _book_from_entry
    from utils.subscription.schema import BookEntry

    books = []
    for entry in entries:
        title = str(entry.get("title") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        try:
            book = _book_from_entry(
                BookEntry(site=provider_name, url=url, title=title or url)
            )
        except Exception:
            continue
        cover = entry.get("cover") or None
        if cover:
            book.img_preview = cover
        pages = entry.get("pages")
        if pages is not None:
            try:
                book.pages = int(pages)
            except (TypeError, ValueError):
                pass
        # Ensure browser-openable absolute preview_url when still relative.
        if getattr(book, "preview_url", None) and not str(book.preview_url).startswith("http"):
            book.preview_url = url
        if getattr(book, "url", None) and not str(book.url).startswith("http"):
            # Keep program-short url when provider expects path; leave as-is if already path.
            pass
        books.append(book)
    return books


def run_checkin(
    provider_name: str,
    *,
    conf_state=_default_conf,
) -> CheckinResult:
    """登录态执行每日签到 → CheckinResult (不抛异常)。"""
    spec = resolve_checkin_spec(provider_name)
    result = CheckinResult(provider=provider_name)
    if spec is None:
        result.message = "no checkin spec"
        return result
    cookies = _read_site_cookies(conf_state, provider_name)
    if not cookies:
        result.message = "no saved cookies"
        return result
    proxies = tuple(str(p) for p in (getattr(conf_state, "proxies", None) or ()) if p)
    transport = None
    if proxies:
        transport = httpx.HTTPTransport(proxy=f"http://{proxies[0]}", retries=1)
    headers = {"User-Agent": _DEFAULT_UA}
    headers.update(spec.headers)
    params = dict(spec.params)
    for name, generator in spec.dynamic_params.items():
        try:
            params[name] = generator() if callable(generator) else _eval_dynamic_param(generator)
        except Exception:
            continue  # 动态参数失败则跳过该参数
    try:
        with httpx.Client(
            transport=transport, timeout=20.0, follow_redirects=True, headers=headers,
        ) as client:
            if spec.data:
                response = client.request(spec.method, spec.url, cookies=cookies, json=spec.data)
            else:
                response = client.request(spec.method, spec.url, cookies=cookies, data=params)
        body = response.text
    except Exception as exc:
        result.message = f"{type(exc).__name__}: {exc}"
        return result
    if any(item in body for item in spec.already_contains):
        result.already = True
        result.message = "already checked in"
    elif any(item in body for item in spec.success_contains):
        result.ok = True
        result.message = "checked in"
    else:
        result.message = f"unexpected response: {body[:200]}"
    return result


def _eval_dynamic_param(js_expr: str):
    """执行简单 JS 表达式生成动态参数值 (jm code 场景: '!!!' + 日期数字)。"""
    return eval(js_expr, {"__builtins__": {}}, {})  # noqa: S307 (受控表达式)


# --- 注册表 (provider_name → spec 懒加载) ---

_favorites_loaders: dict[str, t.Callable[[], FavoritesSpec]] = {}
_checkin_loaders: dict[str, t.Callable[[], CheckinSpec]] = {}


def register_favorites_spec(provider_name: str, loader: t.Callable[[], FavoritesSpec]) -> None:
    _favorites_loaders[provider_name] = loader


def resolve_favorites_spec(provider_name: str | None) -> FavoritesSpec | None:
    if not provider_name:
        return None
    loader = _favorites_loaders.get(str(provider_name))
    return loader() if loader is not None else None


def register_checkin_spec(provider_name: str, loader: t.Callable[[], CheckinSpec]) -> None:
    _checkin_loaders[provider_name] = loader


def resolve_checkin_spec(provider_name: str | None) -> CheckinSpec | None:
    if not provider_name:
        return None
    loader = _checkin_loaders.get(str(provider_name))
    return loader() if loader is not None else None


def supported_account_provider_names() -> tuple[str, ...]:
    return tuple(sorted(set(_favorites_loaders) | set(_checkin_loaders)))
