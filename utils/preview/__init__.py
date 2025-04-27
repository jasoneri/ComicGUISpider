import tempfile
from lxml import etree
from utils import ori_path, temp_p
from utils.sql import SqlUtils
from utils.website import Uuid
from utils.preview.el import El


class PreviewHtml:
    format_path = ori_path.joinpath("GUI/src/preview_format")

    def __init__(self, url=None, custom_style=None):
        self.contents = []
        self.el = El(custom_style)
        self.url = url

    def add(self, *args, **badges_kw):
        """badges_kw support: pages, likes, lang, btype"""
        self.contents.append(self.el.create(*args, **badges_kw))

    @property
    def created_temp_html(self):
        temp_p.mkdir(exist_ok=True)
        with open(self.format_path.joinpath("index.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        _content = "\n".join(self.contents)
        if self.url:
            _content += f'\n<div class="col-md-3"><p>for check current page</p><p>检查当前页数</p><p>{self.url}</p></div>'
        html = format_text.replace("{body}", _content)
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return f

    @staticmethod
    def tip_duplication(spider, tf):
        handler = InfoHandler(spider, tf)
        infos = handler.get_infos()
        if not infos:
            print("tip_duplication got info None")
            return
        batch_md5 = handler.batch_md5(infos)
        sql_utils = SqlUtils()
        downloaded_md5 = sql_utils.batch_check_dupe(list(batch_md5.keys()))
        sql_utils.close()

        with open(tf, 'r+', encoding='utf-8') as fp:
            html_content = fp.read()
            for _md5 in downloaded_md5:
                info = batch_md5[_md5]
                html_content = html_content.replace(
                    f'href="{info}"',
                    f'href="{info}" class="downloaded"'
                )
            fp.seek(0)
            fp.truncate()
            fp.write(html_content)


class InfoHandler:
    def __init__(self, spider, tf):
        self.spider = spider
        self.tf = tf

    def get_infos(self):
        with open(self.tf, 'r', encoding='utf-8') as file:
            html_content = file.read()
            html = etree.HTML(html_content)
        # titles = html.xpath('//div[@class="col-md-3"]//img/@title')
        urls = html.xpath('//div[contains(@class, "singal-task")]//a/@href')
        return urls

    def batch_md5(self, infos):
        # return {md5(title): title for title in titles}
        uuid_obj = Uuid(self.spider)
        _ = {uuid_obj.id_and_md5(info)[-1]: info for info in infos}
        return _


class PreviewByClipHtml:
    format_path = ori_path.joinpath("GUI/src/preview_format")

    @classmethod
    def created_temp_html(cls, url_regex, match_num):
        with open(cls.format_path.joinpath("index_by_clip.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        html = format_text.replace("{_url_regex}", url_regex).replace("{_match_num}", str(match_num))
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return f
