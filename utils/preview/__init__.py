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

    def add(self, book, flag=None):
        """book's extra property(badges_key) support: pages, likes, lang, btype"""
        badges_kw = {}
        supported_badges = ['pages', 'likes', 'lang', 'btype']
        for key in supported_badges:
            if hasattr(book, key) and getattr(book, key):
                badges_kw[key] = getattr(book, key)
        self.contents.append(self.el.create(*book.preview_args, flag=flag, **badges_kw))

    def duel_contents(self):
        for book in self.binfos:
            self.add(book, flag=getattr(book, 'mark_tip', None))

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


class PreviewByClipHtml:
    @classmethod
    def created_temp_html(cls, url_regex, match_num):
        with open(format_path.joinpath("index_by_clip.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        html = format_text.replace("{bs_theme}", bs_theme()) \
                .replace("{_url_regex}", url_regex) \
                .replace("{_match_num}", str(match_num))
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return TF(f)


class PreviewByAgsHtml:
    @classmethod
    def created_temp_html(cls):
        with open(format_path.joinpath("index_ags.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        html = format_text.replace("{bs_theme}", bs_theme())
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return TF(f)
