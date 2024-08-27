# -*- coding: utf-8 -*-
from .basecomicspider import BaseComicSpider3
from utils import PresetHtmlEl, conf, re
from utils.processed_class import PreviewHtml
from utils.special.ehentai import EhCookies
from assets import res
from ..items import ComicspiderItem

domain = "exhentai.org"


class EHentaiSpider(BaseComicSpider3):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.ComicDlProxyMiddleware': 5,
                                                  'ComicSpider.middlewares.UAMiddleware': 6},
                       "COOKIES_ENABLED": False}
    name = 'ehentai'
    num_of_row = 25
    domain = domain
    # allowed_domains = [domain]
    search_url_head = f'https://{domain}/?f_search='
    mappings = {
        '首页': f'https://{domain}',
        '热门': f'https://{domain}/popular'
    }
    frame_book_format = ['title', 'book_pages']
    turn_page_info = (r"page=\d+",)  # TODO[1](2024-08-27): next=idx, prev=idx

    @property
    def ua(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Priority": "u=0, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "cookie": EhCookies(conf.eh_cookies).to_str,
            "TE": "trailers",
        }

    # TODO[1](2024-08-27): start_request也get_limit查出的结果直接返回

    def frame_book(self, response):
        frame_results = {}
        example_b = r' [ {} ]、- {} -、【 {} 】'
        self.say(example_b.format('序号', '页数', '漫画名') + '<br>')
        preview = PreviewHtml()
        targets = response.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        for x, target in enumerate(targets):
            item_elem = target.xpath('./td/div[@class="glthumb"]')
            title = item_elem.xpath('.//img/@title').get()
            pages = next(filter(lambda _: 'pages' in _, item_elem.xpath('.//div/text()').getall())).replace(" pages",
                                                                                                            "")
            url = preview_url = target.xpath('./td[contains(@class, "glname")]/a/@href').get()
            img_preview = (item_elem.xpath('.//img/@data-src') or item_elem.xpath('.//img/@src')).get()
            self.say(example_b.format(str(x + 1), pages, title, chr(12288)))
            self.say('') if (x + 1) % self.num_of_row == 0 else None
            frame_results[x + 1] = [url, title, pages]
            preview.add(x + 1, img_preview, PresetHtmlEl.sub(title), preview_url)
        # TODO[1](2024-08-27): record first-idx and last-idx
        self.say(preview.created_temp_html)
        return self.say.frame_book_print(frame_results, extra=res.EHentai.JUMP_TIP)

    def frame_section(self, response):
        next_flag = None
        frame_results = response.meta.get('frame_results', {})
        sec_page = response.meta.get('sec_page', 1)
        this_book_pages = response.meta.get('book_pages')
        targets = response.xpath('//div[@class="gdtm"]')
        first_idx = max(frame_results.keys()) if frame_results else 0
        for x, target in enumerate(targets):
            idx = first_idx + x
            url = target.xpath('.//a/@href').get()
            frame_results[idx + 1] = url
        if int(max(frame_results.keys())) < int(this_book_pages):
            if "/?p=" in response.url:
                next_flag = re.sub(r'\?p=\d+', rf'?p={sec_page}', response.url)
            else:
                next_flag = response.url.strip('/') + f"/?p={sec_page}"  # ... book-page-index start with 0，not 1
        return frame_results, next_flag

    def parse_fin_page(self, response):
        url = response.xpath('//img[@id="img"]/@src').get() or ""
        title = response.meta.get('title')
        page = response.meta.get('page')
        if url.endswith('509.gif'):
            self.log(f'[509] https://ehgt.org/g/509.gif: [page-{page}] of [{title}]', level=30)
        else:
            item = ComicspiderItem()
            item['title'] = title
            item['page'] = str(page)
            item['section'] = 'meaningless'
            item['image_urls'] = [url]
            self.total += 1
            yield item
