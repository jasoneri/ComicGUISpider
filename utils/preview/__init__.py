import tempfile
from utils import ori_path, temp_p, conf, bs_theme
from utils.preview.el import El


class TF(str):
    def __new__(cls, string):
        return super().__new__(cls, string)


format_path = ori_path.joinpath("GUI/src/preview_format")


def _load_preview_template(template_name: str) -> str:
    return format_path.joinpath(template_name).read_text(encoding="utf-8")


def _render_preview_template(template_name: str, replacements: dict[str, str]) -> str:
    html = _load_preview_template(template_name)
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


def _write_preview_temp_html(html: str, *, prefix: str = "tmp") -> TF:
    temp_p.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=prefix,suffix=".html",
        delete=False,dir=temp_p,
    ) as tf:
        tf.write(html.encode("utf-8"))
        return TF(str(tf.name))


class TmpFormatHtml:
    @classmethod
    def created_temp_html(cls, flag, **kw):
        return getattr(cls, f"to_{flag}")(**kw)

    @classmethod
    def to_publish(cls, **kw):
        html = _render_preview_template(
            "pubilsh_helper.html",
            {k: w for k, w in kw.items()},
        )
        return _write_preview_temp_html(html, prefix="publish")


class PreviewHtml:
    def __init__(self, url=None, binfos=None, custom_style=None):
        self.contents = []
        self.el = El(custom_style)
        self.binfos = binfos or []
        self.url = url

    def add(self, book):
        self.contents.append(self.el.create_from_book(book))

    def duel_contents(self):
        for book in self.binfos:
            self.add(book)

    @property
    def created_temp_html(self):
        _content = "\n".join(self.contents)
        if self.url:
            _content += (f'\n<div class="preview-inline-note"><p>for check current page</p><p>检查当前页数</p><p>{self.url}</p></div>')
        html = _render_preview_template("index.html",{"{bs_theme}": bs_theme(),"{body}": _content})
        return _write_preview_temp_html(html)


class PreviewByFixHtml:
    @classmethod
    def created_temp_html(cls, header_html="", upper_html="", lower_html=""):
        html = _render_preview_template("fix.html", {"{bs_theme}": bs_theme()})
        if header_html:
            html = html.replace('<div id="fixHeader" class="fix-preview-header"></div>',
                f'<div id="fixHeader" class="fix-preview-header">{header_html}</div>')
        html = html.replace("{upper_body}", upper_html)
        html = html.replace("{lower_body}", lower_html)
        return _write_preview_temp_html(html, prefix="tmpFix")


class PreviewByClipHtml:
    @classmethod
    def created_temp_html(cls, url_regex, match_num):
        import html as html_mod
        safe_regex = html_mod.escape(url_regex)
        header = (
            f'<script>window.CLIP_MAX_TASKS={int(match_num)};</script>'
            f'<section class="preview-clip-header">'
            f'<div class="preview-clip-copy">'
            f'<p class="preview-clip-label">Current Regex</p>'
            f'<h2 class="preview-clip-title">{safe_regex}</h2>'
            f'</div>'
            f'<div class="preview-clip-status">'
            f'<p class="preview-clip-count">Match Tasks-num <span>{int(match_num)}</span></p>'
            f'<div class="preview-clip-progress" role="progressbar" aria-label="Clip task progress" '
            f'aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">'
            f'<div id="progress-bar" class="preview-clip-progress__bar" style="width:0"></div>'
            f'</div>'
            f'</div>'
            f'</section>'
        )
        return PreviewByFixHtml.created_temp_html(header_html=header)


class PreviewByAgsHtml:
    @classmethod
    def created_temp_html(cls):
        return PreviewByFixHtml.created_temp_html()
