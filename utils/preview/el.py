import html

from utils import PresetHtmlEl


class ElMinix:
    max_width = 170
    badge_keys = ("pages", "likes", "lang", "btype")

    @classmethod
    def create_from_book(cls, book, *, extra_info=None):
        badges_kw = {}
        for key in cls.badge_keys:
            value = getattr(book, key, None)
            if value:
                badges_kw[key] = value
        return cls.create(
            getattr(book, "idx", ""),
            getattr(book, "img_preview", None) or "",
            getattr(book, "name", "") or "-",
            getattr(book, "preview_url", None) or getattr(book, "url", "") or "",
            extra_info=extra_info,
            **badges_kw,
        )

    @classmethod
    def create(cls, idx, img_src, title, url, meta=None, extra_info=None, **badges_kw):
        safe_title = html.escape(PresetHtmlEl.sub(title or ""), quote=True)
        safe_img_src = html.escape(img_src or "", quote=True)
        safe_url = html.escape(url or "", quote=True)
        safe_idx = html.escape(str(idx), quote=True)
        badges = Badges(**badges_kw)
        return cls.create_(safe_idx, safe_img_src, safe_title, safe_url, badges, meta=meta, extra_info=extra_info)

    @classmethod
    def create_(cls, idx, img_src, title, url, badges, meta=None, extra_info=None):
        extra_html = f'\n            <div class="card-extra-info">{extra_info}</div>' if extra_info else ''
        return f"""<div class="singal-task preview-card">
        <div class="preview-checkbox">
            <input class="preview-checkbox-input" type="checkbox" name="img" id="{idx}">
            <label class="preview-checkbox-label" for="{idx}">
                <span class="preview-checkbox-toggle" aria-hidden="true"><span class="preview-checkbox-tick"></span></span>
                <div class="preview-checkbox-media">
                    <img src="{img_src}" title="{title}" alt="{title}" class="preview-card-image"/>
                    {badges}
                </div>
            </label>
        </div>
        <div class="preview-title">
            <a href="{url}" title="{title}" class="preview-title-link">
                <p class="preview-title-clamp">{title}</p>
            </a>{extra_html}
        </div>
        </div>"""


class MangaEl(ElMinix):
    max_width = 200

    @classmethod
    def create_from_book(cls, book, *, extra_info=None, with_favorite=True):
        meta = []
        meta_badges = []
        if artist := getattr(book, "artist", None):
            meta_badges.append(f"作者: {artist}")
        if popular := getattr(book, "popular", None):
            meta_badges.append(f"热度: {popular}")
        if last_chapter := getattr(book, "last_chapter_name", None):
            meta.append(f"最新: {last_chapter}")
        if updated := getattr(book, "datetime_updated", None):
            meta.append(f"更新: {updated}")
        return cls.create(
            getattr(book, "idx", ""),
            getattr(book, "img_preview", None) or "",
            getattr(book, "name", "") or "-",
            getattr(book, "preview_url", None) or getattr(book, "url", "") or "",
            meta=meta or None,
            meta_badges=meta_badges or None,
            extra_info=extra_info,
            with_favorite=with_favorite,
        )

    @classmethod
    def create(cls, idx, img_src, title, url, meta=None, extra_info=None, with_favorite=True, **badges_kw):
        safe_title = html.escape(title or "", quote=True)
        # safe_url = html.escape(url or "", quote=True)
        safe_img_src = html.escape(img_src or "", quote=True)
        meta_badges = badges_kw.get("meta_badges") or []

        meta_html = ""
        if meta:
            meta_lines = "\n".join(
                f'<p class="book-card-meta-item" title="{html.escape(str(m), quote=True)}">{html.escape(str(m), quote=True)}</p>'
                for m in meta
            )
            meta_html = f"\n{meta_lines}"

        meta_badges_html = ""
        if meta_badges:
            badge_lines = "\n".join(
                f'<span class="demo-badge-manga-meta" title="{html.escape(str(m), quote=True)}"><span class="demo-badge-label">{html.escape(str(m), quote=True)}</span></span>'
                for m in meta_badges
            )
            meta_badges_html = f'\n                    <div class="demo-badge-group demo-badge-group-bottom">{badge_lines}</div>'

        extra_html = f'\n                    <div class="card-extra-info">{extra_info}</div>' if extra_info else ''

        favorite_html = ""
        if with_favorite:
            favorite_html = f'''
                <label class="card-favorite-btn ui-bookmark" data-book-key="{idx}" role="button" tabindex="0" aria-pressed="false" aria-label="收藏/取消收藏" title="收藏/取消收藏">
                    <input class="card-favorite-input" type="checkbox" tabindex="-1" aria-hidden="true">
                    <div class="bookmark" aria-hidden="true">
                        <svg viewBox="0 0 32 32"><g><path d="M27 4v27a1 1 0 0 1-1.625.781L16 24.281l-9.375 7.5A1 1 0 0 1 5 31V4a4 4 0 0 1 4-4h14a4 4 0 0 1 4 4z"></path></g></svg>
                    </div>
                </label>'''

        return f"""<article class="preview-manga-card singal-task">
            <div class="book-card normal-book-card" data-book-key="{idx}" data-book-title="{safe_title}" role="button" aria-label="{safe_title}">{favorite_html}
                <div class="book-card-media">
                    <img src="{safe_img_src}" class="book-card-cover" alt="{safe_title}" title="{safe_title}" onerror="this.onerror=null;this.src='../GUI/src/preview_format/placeholder.svg';">{meta_badges_html}
                </div>
                <div class="book-card-body">
                    <h3 class="book-card-title" title="{safe_title}">{safe_title}</h3>{meta_html}{extra_html}
                </div>
                <div id="status-row-{idx}" class="book-card-status" aria-live="polite"></div>
            </div>
        </article>"""


def El(custom_style) -> ElMinix:
    match custom_style:
        case "manga":
            return MangaEl
        case _:
            return ElMinix


class Badges:
    icon_map = {
        "pages": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="m19 1l-5 5v11l5-4.5zm2 4v13.5c-1.1-.35-2.3-.5-3.5-.5c-1.7 0-4.15.65-5.5 1.5V6c-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6v14.65c0 .25.25.5.5.5c.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5c1.35-.85 3.8-1.5 5.5-1.5c1.65 0 3.35.3 4.75 1.05c.1.05.15.05.25.05c.25 0 .5-.25.5-.5V6c-.6-.45-1.25-.75-2-1M10 18.41C8.75 18.09 7.5 18 6.5 18c-1.06 0-2.32.19-3.5.5V7.13c.91-.4 2.14-.63 3.5-.63s2.59.23 3.5.63z" /></svg>""",
        "likes": """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><path fill="currentColor" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M15 8C8.925 8 4 12.925 4 19c0 11 13 21 20 23.326C31 40 44 30 44 19c0-6.075-4.925-11-11-11c-3.72 0-7.01 1.847-9 4.674A10.99 10.99 0 0 0 15 8" /</svg>"""
    }
    bottom_order = ("likes", "pages")
    top_order = ("lang", "btype")

    def __init__(self, **badges_kw):
        self._content_bottom = []
        self._content_top = []
        for attr in self.bottom_order:
            value = badges_kw.get(attr)
            if value:
                self._content_bottom.append(self._render_bottom(attr, value))
        for attr in self.top_order:
            value = badges_kw.get(attr)
            if value:
                self._content_top.append(self._render_top(attr, value))

    @classmethod
    def _render_bottom(cls, attr, value):
        safe_value = html.escape(str(value), quote=True)
        icon = cls.icon_map.get(attr, "")
        return f'<span class="demo-badge demo-badge-{attr}">{icon}<span class="demo-badge-label">{safe_value}</span></span>'

    @staticmethod
    def _render_top(attr, value):
        safe_value = html.escape(str(value), quote=True)
        return f'''<span class="demo-badge demo-badge-light demo-badge-{attr}" title="{safe_value}">{safe_value}</span>'''

    def __str__(self):
        content = []
        if self._content_bottom:
            content.append(
                '<div class="demo-badge-group demo-badge-group-bottom">'
                + "".join(self._content_bottom)
                + "</div>"
            )
        if self._content_top:
            content.append(
                '<div class="demo-badge-group demo-badge-group-top">'
                + "".join(self._content_top)
                + "</div>"
            )
        return "\n".join(content)
