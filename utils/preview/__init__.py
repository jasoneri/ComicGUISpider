import re
import json
import tempfile
from lxml import etree
from utils import ori_path, temp_p
from utils.sql import SqlUtils
from utils.website import Uuid, spider_utils_map
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
    def tip_duplication(spider_name, tf, page):
        handler = InfoHandler(spider_name, tf)
        urls, episode_bids = handler.get_all_urls()

        if not urls and not episode_bids:
            return

        sql_utils = SqlUtils()
        downloaded_urls, downloaded_episode_bids = [], []

        # 统一处理所有URLs
        if urls:
            try:
                url_batch_md5 = handler.batch_md5(urls)
                url_downloaded_md5 = sql_utils.batch_check_dupe(list(url_batch_md5.keys()))
                downloaded_urls = [url_batch_md5[md5] for md5 in url_downloaded_md5]
            except Exception as e:
                print(f"处理URLs时出错: {e}")

        if episode_bids:
            try:
                bid_to_url = {bid: handler.construct_url(bid) for bid in episode_bids}
                episode_urls = list(bid_to_url.values())
                episode_batch_md5 = handler.batch_md5(episode_urls)
                episode_downloaded_md5 = sql_utils.batch_check_dupe(list(episode_batch_md5.keys()))
                url_to_bid = {url: bid for bid, url in bid_to_url.items()}
                downloaded_episode_bids = [url_to_bid[episode_batch_md5[md5]] for md5 in episode_downloaded_md5]
            except Exception as e:
                print(f"处理episode URLs时出错: {e}")

        sql_utils.close()
        PreviewHtml._mark_downloads_via_js(tf, page, downloaded_urls, downloaded_episode_bids)

    @staticmethod
    def _mark_downloads_via_js(tf, page, downloaded_urls, downloaded_episode_bids=None):
        """通过JS回调标记下载状态"""
        def refresh_tf(html):
            if html:
                with open(tf, 'w', encoding='utf-8') as f:
                    f.write(html)
        if not downloaded_episode_bids:
            downloaded_episode_bids = []
        urls_param = json.dumps(downloaded_urls)
        episodes_param = json.dumps(downloaded_episode_bids)
        js_code = f'window.tryMarkDownloadStatus && window.tryMarkDownloadStatus({urls_param}, {episodes_param});'
        try:
            page.runJavaScript(js_code, refresh_tf)
        except Exception as e:
            print(f"JS callback failed: {e}")


class InfoHandler:
    def __init__(self, spider, tf):
        self.spider = spider
        self.tf = tf
        self._capture_group_regex = re.compile(r'\([^)]+\)')
        self._spider_utils = spider_utils_map.get(self.spider)
        self._pattern = (self._spider_utils.uuid_regex.pattern
                        if self._spider_utils and hasattr(self._spider_utils, 'uuid_regex')
                        else None)

    def get_all_urls(self):
        with open(self.tf, 'r', encoding='utf-8') as file:
            html_content = file.read()
            html = etree.HTML(html_content)

        urls = html.xpath('//div[contains(@class, "singal-task")]//a/@href')
        episode_bids = html.xpath('//input[@class="btn-check"]/@value')
        episode_bids = [bid.strip() for bid in episode_bids if bid and bid.strip()]
        return urls, episode_bids

    def construct_url(self, bid):
        if not self._pattern:
            return bid
        url_part = self._capture_group_regex.sub(bid, self._pattern)
        return url_part.replace('$', '').replace('^', '').replace('\\', '')

    def batch_md5(self, urls):
        uuid_obj = Uuid(self.spider)
        return {uuid_obj.id_and_md5(url)[-1]: url for url in urls}


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
