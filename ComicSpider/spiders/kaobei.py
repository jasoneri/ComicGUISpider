# -*- coding: utf-8 -*-
import re

from utils.processed_class import Url
from utils.website import KaobeiUtils
from utils.website.req_schema import KbFrameBook as FrameBook
from .basecomicspider import BaseComicSpider, ComicspiderItem, conf


class KaobeiSpider(BaseComicSpider):
    name = 'manga_copy'
    ua = headers = KaobeiUtils.ua
    ua_mapi = KaobeiUtils.ua_mapi
    domain = KaobeiUtils.api_domain
    pc_domain = KaobeiUtils.pc_domain
    proxy_domains = [domain, pc_domain]  # 需要代理的域名列表
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.UAKaobeiMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlProxyMiddleware': 6},
        "REFERER_ENABLED": False
    }
    search_url_head = ''
    preset_book_frame = FrameBook(domain)
    turn_page_info = (r"offset=\d+", None, 30)
    section_limit = 300
    _enable_episode_dispatch = True

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        KaobeiUtils.get_aes_key()
        return super().from_crawler(crawler, *args, **kwargs)

    @property
    def search(self):
        keyword = self.input_state.keyword
        url, self.preset_book_frame = KaobeiUtils.build_search_spec(keyword, self.domain)
        return Url(url).set_next(*self.turn_page_info)

    def frame_book(self, response):
        frame_results = {}
        say_fm = self.preset_book_frame.say_fm
        render_keys = self.preset_book_frame.print_head[1:]
        targets = response.json().get('results', {}).get('list', [])
        rendering_map = self.preset_book_frame.rendering_map()
        for x, target in enumerate(targets):
            book = KaobeiUtils.parse_book_item(target, rendering_map, render_keys, x + 1)
            frame_results[book.idx] = book
        return self.say.frame_book_print(
            frame_results, fm=say_fm, url=response.url,
            extra=" →_→ 拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算")

    def frame_section(self, response):
        book = response.meta.get("book")
        say_ep_fm = ' -{}、【{}】'
        episodes = KaobeiUtils.parse_episodes(
            response.json()['results'], book, url=response.url, show_dhb=conf.kbShowDhb)
        frame_results = {ep.idx: ep for ep in episodes}
        self.say.frame_section_print(frame_results, fm=say_ep_fm)

    def mk_page_tasks(self, **kw):
        return [kw['url']]

    def parse_fin_page(self, response):
        ep = response.meta['ep']
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title':book.name,'section':ep.name,'uuid':uid,'uuid_md5':u_md5}
        contentKey_script = response.xpath('//script[contains(text(), "var contentKey =")]/text()').get()
        if not contentKey_script:
            raise ValueError("拷贝更改了contentKey xpath")
        contentKey = re.search(r"""var contentKey = ["']([^']*)["']""", contentKey_script).group(1)
        imageData = KaobeiUtils.decrypt_chapter_data(contentKey, url=response.url, group_infos=group_infos)
        ep.pages = len(imageData)
        self.set_task(ep)
        for page, url_item in enumerate(imageData):
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page + 1
            item['image_urls'] = [url_item['url']]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
