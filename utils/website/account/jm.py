"""jm/18comic (禁漫天堂): 收藏列表 + 每日签到定义。

端点来源: jmcomic 官方库 (hect0x7/JMComic-Crawler-Python, master 2026-08-02)
源码级确认 (GitHub API 拉取):
- 收藏 (网页端): GET /user/{username}/favorite/albums?page={page}&o=latest&folder=0
  (官方 JmcomicClient.favorite_folder 同款; HTML 解析, 条目结构
  div#favorites_album_* + div.video-title.title-truncate + /album/{id}/)
- 签到 (移动端): POST /v1/app-checkin/v2 (check_in=1 + 动态 code + merchant_id=13)
  沙箱实测 ok=True; 官方 App API 备选: /login → /daily_list/filter → /daily_chk
  (token=md5(ts+185Hcomic3PAPP7R), 响应 AES-ECB 解密, 见 rueificebw/manga-checkin)

注意: 官方 App API (/favorite 返回 JSON + token 签名 + AES 解密) 与网页端
路径并存; 本实现走网页端 HTML 路径 (无需签名/解密), username 从 cookies 的
remember_id (PHP serialize) 解析。
"""

from __future__ import annotations

import re
import urllib.parse

from .flows import CheckinSpec, FavoritesSpec, register_checkin_spec, register_favorites_spec

_JM_FAVORITES_URL = (
    "https://{domain}/user/{username}/favorite/albums?page={page}&o=latest&folder=0"
)

# 官方正则结构: 条目容器 div#favorites_album_* → 链接 /album/{aid}/ → 标题
# div.video-title.title-truncate (jmcomic JmPageTool.pattern_html_favorite_content)
_JM_REMEMBER_ID_USERNAME = re.compile(
    r's:\d+:"username";s:\d+:"([^"]*)"'
)


def _jm_domain_resolver() -> str | None:
    """当前 jm 域名 (域名机制, 见 DomainUtils): 缓存 temp_p/jm_domain.txt 优先
    (纯读盘无网络, 无代理直连场景可避开 Cloudflare 挑战), 缺缓存时
    get_domain() 经 publish/forever 动态解析, 全失败兜底静态域 18comic.vip。"""
    from utils.website.providers.jm import JmUtils

    try:
        cached = JmUtils.peek_cached_domain()
        if cached:
            return cached
        return JmUtils.get_domain() or getattr(JmUtils, "domain", None)
    except Exception:
        return getattr(JmUtils, "domain", None)


def _jm_username_from_cookies(cookies: dict[str, str]) -> str | None:
    """从 cookies 的 remember_id (PHP serialize, URL 编码) 解析用户名。

    示例 (URL 解码后):
      a:3:{s:8:"username";s:9:"jsoneri18";s:8:"password";...}
    对齐官方 jmcomic: 网页端收藏页 /user/{username}/favorite/albums 需要用户名。
    """
    raw = cookies.get("remember_id") or ""
    if not raw:
        return None
    try:
        decoded = urllib.parse.unquote(raw)
    except Exception:
        return None
    match = _JM_REMEMBER_ID_USERNAME.search(decoded)
    if not match:
        return None
    username = match.group(1).strip()
    return username or None


def _jm_favorites_spec() -> FavoritesSpec:
    from utils.website.providers.jm import JmUtils

    return FavoritesSpec(
        provider_name="jm",
        list_url=_JM_FAVORITES_URL,
        item_selector='div[id^="favorites_album_"]',
        title_selector='div.video-title.title-truncate::text, img::attr(title)',
        url_selector='a[href*="/album/"]::attr(href)',
        # 对齐 JmUtils.parse_search_item 封面字段
        cover_selector=(
            "img::attr(data-original), img::attr(data-src), "
            "a img::attr(data-original), a img::attr(src), img::attr(src)"
        ),
        # UA 必须与 cookies 生成环境一致 (cf_clearance 绑定 UA)
        headers=dict(JmUtils.book_hea or {}),
        # JM 搜索常禁代理; CF 与 clearance 直连更稳
        use_proxy=False,
        username_from_cookies=_jm_username_from_cookies,
        domain_resolver=_jm_domain_resolver,
    )


def _jm_checkin_code() -> str:
    """jm 签到动态验证码: '!!!' + 日期时间数字 (页面 JS 同款计算)。"""
    from datetime import datetime

    now = datetime.now()
    return f"!!!{now.month}{now.day}{now.hour}{now.minute}{now.second}"


def _jm_checkin_spec() -> CheckinSpec:
    return CheckinSpec(
        provider_name="jm",
        url="https://18comic.vip/v1/app-checkin/v2",
        params={"check_in": "1", "merchant_id": "13"},
        dynamic_params={"code": _jm_checkin_code},
        success_contains=("签到成功", "checkin"),
        already_contains=("已签到", "already"),
    )


register_favorites_spec("jm", _jm_favorites_spec)
register_checkin_spec("jm", _jm_checkin_spec)
