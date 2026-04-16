# -*- coding: utf-8 -*-
import re
from concurrent.futures import ThreadPoolExecutor

from utils.website import WnacgUtils, correct_domain
from .basecomicspider import BaseComicSpider2, font_color

domain = "wnacg.com"


class WnacgSpider(BaseComicSpider2):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {
        'ComicSpider.middlewares.ComicDlAllProxyMiddleware': 6,
        # 'ComicSpider.middlewares.ScrapyDoHProxyMiddleware': 8,
        'ComicSpider.middlewares.RefererMiddleware': 10,
    },
        "ITEM_PIPELINES": {'ComicSpider.pipelines.WnacgComicPipeline': 50},
    }
    name = 'wnacg'
    # curl_cffi image misses do not imply the cached site domain is stale.
    remove_domain_cache_on_finished_miss = False
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

    @property
    def ua(self):
        return WnacgUtils.build_site_headers(self.domain, WnacgUtils.book_hea)

    def preready(self):
        if self._runtime_origin:
            return
        self.domain = self.site.resolve_domain()
        self.site.reqer.domain = self.domain
        self.book_id_url = correct_domain(self.domain, self.book_id_url)

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
