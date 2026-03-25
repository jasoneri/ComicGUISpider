import tempfile
from utils import ori_path, temp_p, conf, bs_theme
from utils.preview.el import El


class TF(str):
    def __new__(cls, string):
        return super().__new__(cls, string)


format_path = ori_path.joinpath("GUI/src/preview_format")


class TmpFormatHtml:
    @classmethod
    def created_temp_html(cls, flag, **kw):
        return getattr(cls, f"to_{flag}")(**kw)

    @classmethod
    def to_publish(cls, **kw):
        with open(format_path.joinpath('pubilsh_helper.html'), encoding='utf-8') as f:
            html = f.read()
        for k, w in kw.items():
            html = html.replace(k, w)
        with tempfile.NamedTemporaryFile(prefix="publish", suffix=".html", delete=False, dir=temp_p) as tf:
            tf.write(bytes(html, 'utf-8'))
            f = str(tf.name)
        return TF(f)


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
        temp_p.mkdir(exist_ok=True)
        with open(format_path.joinpath("index.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        _content = "\n".join(self.contents)
        if self.url:
            _content += f'\n<div class="col-md-3"><p>for check current page</p><p>检查当前页数</p><p>{self.url}</p></div>'
        html = format_text.replace("{bs_theme}", bs_theme()).replace("{body}", _content)
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return TF(f)


class PreviewByFixHtml:
    @classmethod
    def created_temp_html(cls, header_html="", upper_html="", lower_html=""):
        temp_p.mkdir(exist_ok=True)
        with open(format_path.joinpath("fix.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        html = format_text.replace("{bs_theme}", bs_theme())
        if header_html:
            html = html.replace('<div id="fixHeader"></div>',
                                f'<div id="fixHeader">{header_html}</div>')
        html = html.replace("{upper_body}", upper_html)
        html = html.replace("{lower_body}", lower_html)
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return TF(f)


class PreviewByClipHtml:
    @classmethod
    def created_temp_html(cls, url_regex, match_num):
        import html as html_mod
        safe_regex = html_mod.escape(url_regex)
        header = (
            f'<script>window.CLIP_MAX_TASKS={int(match_num)};</script>'
            f'<div class="container-fluid py-2">'
            f'<div class="row"><div class="col-auto me-auto"><h5>Current Regex：{safe_regex}</h5></div></div>'
            f'<div class="row"><div class="col-ms"><h5>Match Tasks-num '
            f'<span style="font-size:larger;color:#00aa00">{int(match_num)}</span></h5></div>'
            f'<div class="col-ms-auto"><div class="progress">'
            f'<div id="progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" '
            f'role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width:0"></div>'
            f'</div></div></div></div>'
        )
        return PreviewByFixHtml.created_temp_html(header_html=header)


class PreviewByAgsHtml:
    @classmethod
    def created_temp_html(cls):
        return PreviewByFixHtml.created_temp_html()
