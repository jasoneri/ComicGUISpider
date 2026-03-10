# -*- coding: utf-8 -*-
import re

from utils.processed_class import execute_js
from utils.website import MangabzUtils
from utils.website.req_schema import MbBody as Body, MbSearchBody as SearchBody, mb_curr_time_format as curr_time_format
from .basecomicspider import FormReqBaseComicSpider, ComicspiderItem

domain = MangabzUtils.domain


class MangabzSpider(FormReqBaseComicSpider):
    name = 'mangabz'
    ua = MangabzUtils.ua
    num_of_row = 50
    domain = domain
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.MangabzUAMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlAllProxyMiddleware': 6},
        "ITEM_PIPELINES": {'ComicSpider.pipelines.MangabzComicPipeline': 50}
    }
    search_url_head = f"https://{domain}/pager.ashx"
    mappings = {"更新": ["manga-list-0-0-2", "2"],
                "人气": ["manga-list", "10"],
                }
    body = Body()
    _enable_episode_dispatch = True

    @property
    def search(self):
        self._emit_process('search')
        keyword = self.input_state.keyword.strip()
        if keyword in self.mappings.keys():
            search_start_path, body_sort = self.mappings[keyword]  # TODO[5](2024-09-30): 后续支持状态：全部/连载中/完结，排序：上架时间
            search_start = f"https://{domain}/{search_start_path}/mangabz.ashx?d={curr_time_format()}"
            self.body.update(sort=body_sort)
        else:
            search_start = f"{self.search_url_head}?d={curr_time_format()}"
            self.body = SearchBody(title=keyword)
        return search_start

    def frame_book(self, response):
        frame_results = {}
        render_keys = self.body.print_head[1:]
        targets = response.json() if isinstance(self.body, SearchBody) \
            else response.json().get('UpdateComicItems')
        rendering_map = self.body.rendering_map()
        for x, target in enumerate(targets):
            book = MangabzUtils.parse_book_item(
                target, rendering_map, render_keys, x + 1, self.domain)
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, url=response.url)

    def frame_section(self, response):
        book = response.meta.get("book")
        episodes = MangabzUtils.parse_episodes(response, book, domain)
        frame_results = {ep.idx: ep for ep in episodes}
        return self.say.frame_section_print(frame_results)

    def parse_fin_page(self, response):
        ep = response.meta['ep']
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        js = response.xpath('//script[@type="text/javascript"]/text()').getall()
        target_js = next(filter(lambda t: t.strip().startswith('eval'), js), None)
        real_js = execute_js(
            r"""function run(code){var ret="";eval('ret = '+code.replace(/^;*?\s*(window(\.|\[(["'])))?eval(\3\])?/, 
            function ($0) {return 'String';}));   return ret }""",
            "run", target_js)
        img_list_ = re.search(r'\[(.*?)]', real_js).group(1)
        img_list = [re.sub(r"""['"]""", '', _) for _ in re.split(', ?', img_list_)]
        group_infos = {'title':book.name,'section':ep.name,'uuid':uid,'uuid_md5':u_md5}
        ep.pages = len(img_list)
        self.set_task(ep)
        for img_url in img_list:
            item = ComicspiderItem()
            item.update(**group_infos)
            page = int(re.search(r'/(\d+)_\d+\.', img_url).group(1))
            item['page'] = page
            item['image_urls'] = [img_url]
            self.total += 1
            yield item
        self._emit_process('fin')
