import html

from utils import PresetHtmlEl


class ElMinix:
    max_width = 170

    @classmethod
    def create(cls, idx, img_src, title, url, flag=None, meta=None, **badges_kw):
        title = PresetHtmlEl.sub(title)
        abbreviated_title = f"{title[:18]}..."
        badges = Badges(**badges_kw)
        return cls.create_(idx, img_src, title, abbreviated_title, url, badges, flag=flag, meta=meta)

    @classmethod
    def create_(cls, idx, img_src, title, abbreviated_title, url, badges, flag=None, meta=None):
        container_cls = f" container-{flag}" if flag else ""
        img_cls = f" img-{flag}" if flag else ""
        el = f"""<div class="col-md-3 singal-task" style="max-width:{cls.max_width}px"><div class="form-check{container_cls}">
        <input class="form-check-input" type="checkbox" name="img" id="{idx}">
        <label class="form-check-label" for="{idx}">
            <div style="position: relative; display: inline-block;">
                <img src="{img_src}" title="{title}" alt="{title}" class="img-thumbnail{img_cls}"/>
                {badges}
            </div>
        </label></div>
        <a href="{url}"><p>[{idx}]、{abbreviated_title}</p></a>
        </div>"""
        return el


class MangaEl(ElMinix):
    max_width = 200

    @classmethod
    def create(cls, idx, img_src, title, url, flag=None, meta=None, **badges_kw):
        safe_title = html.escape(title, quote=True)
        # safe_url = html.escape(url or "", quote=True)
        safe_img_src = html.escape(img_src or "", quote=True)

        meta_html = ""
        if meta:
            meta_lines = "\n".join(f'<small class="text-muted d-block text-truncate">{html.escape(str(m), quote=True)}</small>' for m in meta)
            meta_html = f"{meta_lines}"

        return f"""<div class="col-sm-6 col-md-4 col-lg-3 mb-3 singal-task" style="max-width:{cls.max_width}px">
            <div class="card h-100 normal-book-card" data-book-key="{idx}" data-book-title="{safe_title}" role="button" aria-label="{safe_title}">
                <div class="card-favorite-btn" data-book-key="{idx}" role="button" tabindex="0" aria-pressed="false" title="收藏/取消收藏">☆</div>
                <img src="{safe_img_src}" class="card-img-top" alt="{safe_title}" title="{safe_title}" onerror="this.onerror=null;this.src='../GUI/src/preview_format/placeholder.svg';">
                <div class="card-body"><h6 class="card-title mb-2">{safe_title}</h6>{meta_html}</div>
                <div id="status-row-{idx}" class="card-footer bg-transparent border-0 pt-0 pb-2 px-2 d-flex gap-1 flex-wrap align-items-center small"></div>
            </div>
        </div>"""


def El(custom_style) -> ElMinix:
    match custom_style:
        case "manga":
            return MangaEl
        case _:
            return ElMinix


class Badges:
    pages = '<span class="badge bg-info badge-left-bottom">p%s</span>'
    likes = '<span class="badge bg-danger badge-left-bottom">♥️%s</span>'
    lang = '<span class="badge rounded-pill bg-light text-dark badge-right-top badge-lang">%s</span>'
    btype = '<span class="badge bg-light text-dark badge-right-top badge-btype">%s</span>'

    def __init__(self, **badges_kw):
        self._content = []
        self._content.extend(
            getattr(self, attr) % value
            for attr, value in badges_kw.items()
            if value
        )

    def __str__(self):
        return r'<br>'.join(self._content)
