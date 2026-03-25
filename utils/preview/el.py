import html

from utils import PresetHtmlEl


class ElMinix:
    max_width = 170
    downloaded_state = "downloaded"

    @classmethod
    def create(cls, idx, img_src, title, url, flag=None, meta=None, **badges_kw):
        safe_title = html.escape(PresetHtmlEl.sub(title or ""), quote=True)
        safe_img_src = html.escape(img_src or "", quote=True)
        safe_url = html.escape(url or "", quote=True)
        safe_idx = html.escape(str(idx), quote=True)
        badges = Badges(**badges_kw)
        return cls.create_(safe_idx, safe_img_src, safe_title, safe_url, badges, flag=flag, meta=meta)

    @classmethod
    def create_(cls, idx, img_src, title, url, badges, flag=None, meta=None):
        is_downloaded = flag == cls.downloaded_state
        card_state_cls = " preview-card-state-downloaded" if is_downloaded else ""
        media_state_cls = " container-downloaded" if is_downloaded else ""
        image_state_cls = " img-downloaded" if is_downloaded else ""
        disabled_attr = ' disabled aria-disabled="true"' if is_downloaded else ""
        label_disabled_attr = ' aria-disabled="true"' if is_downloaded else ""
        return f"""<div class="col-md-3 singal-task preview-card-shell{card_state_cls}">
        <div class="form-check preview-card-check">
            <input class="form-check-input preview-checkbox-input" type="checkbox" name="img" id="{idx}"{disabled_attr}>
            <label class="form-check-label preview-checkbox-label" for="{idx}"{label_disabled_attr}>
                <span class="preview-checkbox-toggle" aria-hidden="true"><span class="preview-checkbox-tick"></span></span>
                <div class="preview-checkbox-media{media_state_cls}">
                    <img src="{img_src}" title="{title}" alt="{title}" class="img-thumbnail preview-card-image{image_state_cls}"/>
                    {badges}
                </div>
            </label>
        </div>
        <div class="preview-title-shell">
            <a href="{url}" title="{title}" class="preview-title-link">
                <p class="preview-title-clamp">{title}</p>
            </a>
        </div>
        </div>"""


class MangaEl(ElMinix):
    max_width = 200

    @classmethod
    def create(cls, idx, img_src, title, url, flag=None, meta=None, **badges_kw):
        safe_title = html.escape(title, quote=True)
        # safe_url = html.escape(url or "", quote=True)
        safe_img_src = html.escape(img_src or "", quote=True)

        meta_html = ""
        if meta:
            meta_lines = "\n".join(
                f'<p class="book-card-meta-item" title="{html.escape(str(m), quote=True)}">{html.escape(str(m), quote=True)}</p>'
                for m in meta
            )
            meta_html = f"\n{meta_lines}"

        return f"""<article class="book-card-shell singal-task">
            <div class="book-card normal-book-card" data-book-key="{idx}" data-book-title="{safe_title}" role="button" aria-label="{safe_title}">
                <label class="card-favorite-btn ui-bookmark" data-book-key="{idx}" role="button" tabindex="0" aria-pressed="false" aria-label="收藏/取消收藏" title="收藏/取消收藏">
                    <input class="card-favorite-input" type="checkbox" tabindex="-1" aria-hidden="true">
                    <div class="bookmark" aria-hidden="true">
                        <svg viewBox="0 0 32 32"><g><path d="M27 4v27a1 1 0 0 1-1.625.781L16 24.281l-9.375 7.5A1 1 0 0 1 5 31V4a4 4 0 0 1 4-4h14a4 4 0 0 1 4 4z"></path></g></svg>
                    </div>
                </label>
                <img src="{safe_img_src}" class="book-card-cover" alt="{safe_title}" title="{safe_title}" onerror="this.onerror=null;this.src='../GUI/src/preview_format/placeholder.svg';">
                <div class="book-card-body">
                    <h3 class="book-card-title" title="{safe_title}">{safe_title}</h3>{meta_html}
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
    icon = (
        '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">'
        '<path d="M4 3.75A1.75 1.75 0 0 1 5.75 2h8.5A1.75 1.75 0 0 1 16 3.75v12.5a.75.75 0 0 1-1.18.616'
        'L10 13.607l-4.82 3.259A.75.75 0 0 1 4 16.25V3.75Z"/></svg>'
    )
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
        label = f"p{safe_value}" if attr == "pages" else safe_value
        return (
            f'<span class="demo-badge demo-badge-{attr}">{cls.icon}'
            f'<span class="demo-badge-label">{label}</span></span>'
        )

    @staticmethod
    def _render_top(attr, value):
        safe_value = html.escape(str(value), quote=True)
        return (
            f'<span class="demo-badge demo-badge-light demo-badge-{attr}" '
            f'title="{safe_value}">{safe_value}</span>'
        )

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
