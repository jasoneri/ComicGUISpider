# -*- coding: utf-8 -*-
import re

from .basecomicspider import BaseComicSpider2, font_color
from utils.website import WnacgUtils, correct_domain
from utils.processed_class import PreviewHtml

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
        example_b = r' [ {} ]、【 {} 】'
        self.say(example_b.format('序号', '漫画名') + '<br>')
        preview = PreviewHtml(response.url)
        targets = response.xpath('//li[contains(@class, "gallary_item")]')
        tar_xpath = './div[contains(@class, "pic")]'
        for x, target in enumerate(targets):
            item_elem = target.xpath(f"{tar_xpath}/a")
            title = item_elem.xpath('./@title').get()
            pre_url = item_elem.xpath('./@href').get()
            preview_url = f'https://{self.domain}{pre_url}'  # 人类行为读取的页面
            url = self.transfer_url(preview_url)
            img_preview = 'http:' + item_elem.xpath('./img/@src').get()
            self.say(example_b.format(str(x + 1), title, chr(12288)))
            self.say('') if (x + 1) % self.num_of_row == 0 else None
            frame_results[x + 1] = [url, title, preview_url]
            _page = target.xpath('.//div[contains(@class, "info_col")]/text()').get()
            pages = re.search(r'(\d+)[張张]', _page.strip()).group(1) if _page else 0
            _cate = (target.xpath(f"{tar_xpath}/@class").get() or "").split(" ")[-1]
            btype = WnacgUtils.cate_mappings.get(_cate, "")
            preview.add(x + 1, img_preview, title, preview_url, pages=pages, btype=btype)
        self.say(preview.created_temp_html)
        return self.say.frame_book_print(frame_results, url=response.url)

    def frame_section(self, response):
        doc_wlns = re.split(r';[\n\s]+?document\.writeln', response.text)
        selected_doc = next(filter(lambda _: "var imglist" in _, doc_wlns))
        targets = re.findall(r'(//.*?(jp[e]?g|png|webp))', selected_doc)
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = f"https:{target[0]}"
            frame_results[x + 1] = img_url
        self.say("=" * 15 + font_color(' 本子网没章节的 这本已经扔进任务了', cls='theme-tip'))
        return frame_results
