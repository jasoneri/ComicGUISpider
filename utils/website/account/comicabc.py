"""8comic (無限動漫): 收藏 + 签到定义 (Tier 2)。

端点来源: grok-search 调研 2026-08-02 (推测性, URL 拼写前后不一致):
- 收藏: mylike.html 会员页 + member/mylake.ashx?page=&rows=
- 签到: POST /ajax/Sign.ashx (action=sign)

NOT_REGISTERED: 端点待抓包验证, 不注册进注册表, 避免误用。
"""

from __future__ import annotations

from .flows import CheckinSpec, FavoritesSpec


def _comicabc_favorites_spec() -> FavoritesSpec:
    return FavoritesSpec(
        provider_name="comicabc",
        # TODO(verify-by-capture): 接口名存疑 (mylike.html/mylake.ashx 拼写不一致)
        list_url="https://www.8comic.com/member/mylake.ashx?page={page}&rows=0",
        item_selector="a[href*='/comic/']",
        title_selector="::attr(title)",
        url_selector="::attr(href)",
        headers={"Referer": "https://www.8comic.com/member.html"},
    )


def _comicabc_checkin_spec() -> CheckinSpec:
    return CheckinSpec(
        provider_name="comicabc",
        # TODO(verify-by-capture): 签到端点推测
        url="https://www.8comic.com/ajax/Sign.ashx",
        params={"action": "sign"},
        headers={"Referer": "https://www.8comic.com/member.html"},
        success_contains=("成功", "ok"),
        already_contains=("已签到",),
    )
