"""manhuagui (看漫画): 收藏列表定义。

端点来源: grok-search 调研 2026-08-02:
- 收藏(书架): GET /user/profile/shelf?type=N (1=在读 2=已读 3=想读, HTML 解析)
"""

from __future__ import annotations

from .flows import FavoritesSpec, register_favorites_spec

_MANHUAGUI_SHELF_URL = "https://www.manhuagui.com/user/profile/shelf?type=1"


def _manhuagui_favorites_spec() -> FavoritesSpec:
    return FavoritesSpec(
        provider_name="manhuagui",
        list_url=_MANHUAGUI_SHELF_URL,
        # 书架常见结构: 条目容器内 a + img; 沙箱可再校准
        item_selector=".shelf-item, .book-list li, #shelfList li, .dy_img",
        title_selector="a::attr(title), a::text, img::attr(alt), img::attr(title)",
        url_selector="a::attr(href)",
        cover_selector="img::attr(data-src), img::attr(src)",
        headers={"Referer": "https://www.manhuagui.com/"},
        use_proxy=True,
    )


register_favorites_spec("manhuagui", _manhuagui_favorites_spec)
