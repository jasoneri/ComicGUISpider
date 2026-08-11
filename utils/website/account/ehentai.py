"""ehentai/exhentai: 收藏列表定义。

端点来源: grok-search 调研 2026-08-02:
- 收藏: GET https://e-hentai.org/favorites.php?favcat=0&page={page} (HTML 解析)
注: 收藏列表在表站 e-hentai.org (favorites.php 走表站域); 里站 exhentai 访问
问题由 08-02-08-03-exhentai-browser-fix 修复。
"""

from __future__ import annotations

from .flows import FavoritesSpec, register_favorites_spec

_EHENTAI_FAVORITES_URL = "https://e-hentai.org/favorites.php?favcat=0&page={page}"


def _ehentai_favorites_spec() -> FavoritesSpec:
    # 整行 tr: 标题/链接在 glname, 封面/页数在 glthumb (与 parse_search_item 同字段源)
    return FavoritesSpec(
        provider_name="ehentai",
        list_url=_EHENTAI_FAVORITES_URL,
        item_selector="table.itg tr:has(td.gl3c.glname)",
        title_selector="td.gl3c.glname div.glink::text, td.gl3c.glname a::attr(title)",
        url_selector="td.gl3c.glname a::attr(href)",
        cover_selector="td.gl2c img::attr(data-src), td.gl2c img::attr(src), .glthumb img::attr(data-src), .glthumb img::attr(src)",
        pages_selector=".glthumb div::text",
        headers={
            "Referer": "https://e-hentai.org/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
                "Gecko/20100101 Firefox/140.0"
            ),
        },
        use_proxy=True,
    )


register_favorites_spec("ehentai", _ehentai_favorites_spec)
