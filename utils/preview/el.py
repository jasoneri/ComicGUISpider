from utils import PresetHtmlEl


class ElMinix:
    max_width = 170
    
    @classmethod
    def create(cls, idx, img_src, title, url, **badges_kw):
        title = PresetHtmlEl.sub(title)
        abbreviated_title = title[:18] + "..."
        badges = Badges(**badges_kw)
        return cls.create_(idx, img_src, title, abbreviated_title, url, badges)
    
    @classmethod
    def create_(cls, idx, img_src, title, abbreviated_title, url, badges):
        el = f"""<div class="col-md-3 singal-task" style="max-width:{cls.max_width}px"><div class="form-check">
        <input class="form-check-input" type="checkbox" name="img" id="{idx}">
        <label class="form-check-label" for="{idx}">
            <div style="position: relative; display: inline-block;">
                <img src="{img_src}" title="{title}" alt="{title}" class="img-thumbnail"/>
                {badges}
            </div>
        </label></div>
        <a href="{url}"><p>[{idx}]、{abbreviated_title}</p></a>
        </div>"""
        return el


def El(custom_style) -> ElMinix:
    match custom_style:
        case _:
            return ElMinix


class Badges:
    pages = '<span class="badge bg-info badge-left-bottom">p%s</span>'
    likes = '<span class="badge bg-danger badge-left-bottom">♥️%s</span>'
    lang = '<span class="badge rounded-pill bg-light text-dark badge-right-top badge-lang">%s</span>'
    btype = '<span class="badge bg-light text-dark badge-right-top badge-btype">%s</span>'

    def __init__(self, **badges_kw):
        self._content = []
        for attr, value in badges_kw.items():
            if value:
                self._content.append(getattr(self, attr) % value)

    def __str__(self):
        return r'<br>'.join(self._content)
