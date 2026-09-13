# -*- coding: utf-8 -*-
from utils.chore import correct_domain
from .basecomicspider import BaseComicSpider2, font_color

domain = "wnacg.com"


class WnacgSpider(BaseComicSpider2):
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            # Gallery HTML must use curl_cffi before Twisted TLS hits CF challenge.
            "ComicSpider.middlewares.WnacgCurlCffiHtmlMiddleware": 1,
            "ComicSpider.middlewares.ComicDlAllProxyMiddleware": 6,
            # "ComicSpider.middlewares.ScrapyDoHProxyMiddleware": 8,
            "ComicSpider.middlewares.RefererMiddleware": 10,
        },
        "ITEM_PIPELINES": {"ComicSpider.pipelines.WnacgComicPipeline": 50},
    }
    name = "wnacg"
    # curl_cffi image misses do not imply the cached site domain is stale.
    remove_domain_cache_on_finished_miss = False
    html_impersonate = "chrome146"
    num_of_row = 4
    domain = domain
    # allowed_domains = [domain]

    @property
    def ua(self):
        provider = self.spider_site_runtime.provider
        return provider.build_site_headers(self.domain, provider.book_hea)

    def frame_section(self, response):
        image_urls = self.spider_site_runtime.parser.parse_gallery_images(response.text)
        frame_results = {page: url for page, url in enumerate(image_urls, start=1)}
        self.say("📢" + font_color(" 这本已经扔进任务了", cls="theme-tip"))
        return frame_results
