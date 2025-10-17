# -*- coding: utf-8 -*-
from scrapy import Request

from utils import conf, re
from utils.processed_class import PreviewHtml, Url
from utils.website import EHentaiKits as EK, EhBookInfo
from assets import res
from .basecomicspider import BaseComicSpider3
from ..items import ComicspiderItem

domain = "exhentai.org"


class EHentaiSpider(BaseComicSpider3):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.ComicDlProxyMiddleware': 5,
                                                  'ComicSpider.middlewares.UAMiddleware': 6},
                       "COOKIES_ENABLED": False}
    name = 'ehentai'
    num_of_row = 25
    domain = domain
    search_url_head = f'https://{domain}/?f_search='
    mappings = {
        res.EHentai.MAPPINGS_INDEX: f'https://{domain}',
        res.EHentai.MAPPINGS_POPULAR: f'https://{domain}/popular'
    }
    say_fm = r' [ {} ], p_{}, ⌈ {} ⌋ '
    frame_book_format = ['title', 'book_pages', 'preview_url']  # , 'book_idx']
    turn_page_info = (r"page=\d+",)
    book_id_url = f'https://{domain}/g/%s'

    @property
    def ua(self):
        return {**EK.headers, "cookie": EK.to_str_(conf.cookies.get(self.name))}

    def frame_book(self, response):
        frame_results = {}
        self.say(self.say_fm.format('index', 'pages', 'name') + '<br>')
        targets = response.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        for x, target in enumerate(targets):
            item_elem = target.xpath('./td/div[@class="glthumb"]')
            pages = (next(filter(
                lambda _: 'pages' in _, item_elem.xpath('.//div/text()').getall()))
                     .replace(" pages", ""))
            _url = target.xpath('./td[contains(@class, "glname")]/a/@href').get()
            book = EhBookInfo(
                idx=x+1,
                name=item_elem.xpath('.//img/@title').get(),
                preview_url=_url,
                url=_url,
                pages=int(pages),
                btype=target.xpath('./td[contains(@class, "glcat")]/div/text()').get(),
                img_preview=(item_elem.xpath('.//img/@data-src') or item_elem.xpath('.//img/@src')).get()
            ).get_id(_url)
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, extra=f"<br>{res.EHentai.JUMP_TIP}", url=response.url,
                                         make_preview=True)

    def page_turn(self, response):
        if 'next' in self.input_state.pageTurn:
            find_prevurl = re.search(r"""var nexturl="(.*?)";""", response.text)
            url = Url(find_prevurl.group(1) if bool(find_prevurl) else "")
            yield from self.page_turn_(url)
        elif 'previous' in self.input_state.pageTurn:
            find_prevurl = re.search(r"""var prevurl="(.*?)";""", response.text)
            url = Url(find_prevurl.group(1) if bool(find_prevurl) else "")
            yield from self.page_turn_(url)
        else:
            yield Request(url=self.search, callback=self.parse, meta=response.meta, dont_filter=True)

    def parse_section(self, response):
        if not response.meta.get('sec_page'):
            title_gj = response.xpath('//h1[@id="gj"]/text()')
            if title_gj:
                response.meta['book'].name = title_gj.get()
            else:
                titles = response.xpath("//h1/text()").getall()
                if response.meta['book'].name in titles and len(titles) > 1:
                    titles.remove(response.meta['book'].name)
                    response.meta['book'].name = titles[0]
        yield from super(EHentaiSpider, self).parse_section(response)

    def frame_section(self, response):
        next_flag = None
        frame_results = response.meta.get('frame_results', {})
        sec_page = response.meta.get('sec_page', 1)
        this_book_pages = response.meta.get('book_pages') or re.search(r">(\d+) pages<", response.text).group(1)
        targets = response.xpath('//div[@id="gdt"]/a')
        first_idx = max(frame_results.keys()) if frame_results else 0
        for x, target in enumerate(targets):
            idx = first_idx + x
            url = target.xpath('./@href').get()
            frame_results[idx + 1] = url
        if int(max(frame_results.keys())) < int(this_book_pages):
            if "/?p=" in response.url:
                next_flag = re.sub(r'\?p=\d+', rf'?p={sec_page}', response.url)
            else:
                next_flag = response.url.strip('/') + f"/?p={sec_page}"  # ... book-page-index start with 0，not 1
        return frame_results, next_flag

    def parse_fin_page(self, response):
        url = response.xpath('//img[@id="img"]/@src').get() or ""
        page = response.meta.get('page')
        book = response.meta.get('book')
        if url.endswith('509.gif'):
            self.log(f'[509] https://ehgt.org/g/509.gif: [page-{page}] of [{book.name}]', level=30)
        else:
            item = ComicspiderItem()
            item.update(**book.get_group_infos())
            item['page'] = str(page)
            item['image_urls'] = [url]
            self.total += 1
            yield item
