# -*- coding: utf-8 -*-
import re

from utils.website import WnacgUtils, correct_domain
from .basecomicspider import BaseComicSpider2, font_color

domain = "wnacg.com"


class WnacgSpider(BaseComicSpider2):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {
        'ComicSpider.middlewares.ComicDlProxyMiddleware': 6,
        'ComicSpider.middlewares.RefererMiddleware': 10,
    }}
    name = 'wnacg'
    num_of_row = 4
    domain = domain
    # allowed_domains = [domain]
    search_url_head = f'https://{domain}/search/?f=_all&s=create_time_DESC&syn=yes&q='
    mappings = {'更新': f'https://{domain}/albums-index.html',
                '汉化': f'https://{domain}/albums-index-cate-1.html', }
    turn_page_search = r"p=\d+"
    turn_page_info = (r"-page-\d+", "albums-index%s")
    book_id_url = f'https://{domain}/photos-gallery-aid-%s.html'
    transfer_url = staticmethod(lambda url: url.replace('index', 'gallery'))

    def preready(self):
        if self.settings.get("PROXY_CUST") is None:
            self.domain = self.ut.get_domain()
            self.book_id_url = correct_domain(self.domain, self.book_id_url)

    def frame_book(self, response):
        frame_results = {}
        self.say(self.say_fm.format('序号', '漫画名') + '<br>')
        targets = response.xpath('//li[contains(@class, "gallary_item")]')
        for x, target in enumerate(targets):
            book = WnacgUtils.parse_search_item(target)
            book.idx = x + 1
            book.preview_url = f'https://{self.domain}{book.preview_url}'
            book.url = f'https://{self.domain}{book.url}'
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, url=response.url, make_preview=True)

    def frame_section(self, response):
        doc_wlns = re.split(r';[\n\s]+?document\.writeln', response.text)
        selected_doc = next(filter(lambda _: "var imglist" in _, doc_wlns))
        targets = re.findall(r'(//.*?(jp[e]?g|png|webp))', selected_doc)
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = f"https:{target[0]}"
            frame_results[x + 1] = img_url
        self.say("📢" + font_color(' 这本已经扔进任务了', cls='theme-tip'))
        return frame_results
