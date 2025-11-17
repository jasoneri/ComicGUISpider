import tempfile
from utils import ori_path, temp_p, conf
from utils.preview.el import El


def bs_theme():
    return "dark" if conf.darkTheme else "light"


class TF(str):
    def __new__(cls, string):
        instance = super().__new__(cls, string)
        instance.tasks_progress_panel_flag = False
        return instance

    def set_tasks_progress_panel(self):
        self.tasks_progress_panel_flag = True


format_path = ori_path.joinpath("GUI/src/preview_format")


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
