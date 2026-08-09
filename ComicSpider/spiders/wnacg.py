# -*- coding: utf-8 -*-
import re

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
        text = response.text or ""
        if "var imglist" not in text:
            raise ValueError(
                f"wnacg gallery HTML missing var imglist | url={getattr(response, 'url', None)} "
                f"status={getattr(response, 'status', None)} body_len={len(text)}"
            )
        doc_wlns = re.split(r';[\n\s]+?document\.writeln', text)
        selected_doc = next(filter(lambda _: "var imglist" in _, doc_wlns), None)
        if not selected_doc:
            raise ValueError(
                f"wnacg gallery HTML has imglist token but no document.writeln block | url={getattr(response, 'url', None)}"
            )
        targets = re.findall(r"(//.*?(jp[e]?g|png|webp))", selected_doc)
        if not targets:
            raise ValueError(
                f"wnacg gallery imglist produced zero image urls | url={getattr(response, 'url', None)}"
            )
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = f"https:{target[0]}"
            frame_results[x + 1] = img_url
        self.say("📢" + font_color(" 这本已经扔进任务了", cls="theme-tip"))
        return frame_results
