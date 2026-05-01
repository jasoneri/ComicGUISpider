# -*- coding: utf-8 -*-
import re

from utils.website import correct_domain
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

    @property
    def ua(self):
        provider = self.spider_site_runtime.provider
        return provider.build_site_headers(self.domain, provider.book_hea)

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
