# -*- coding: utf-8 -*-
from .basecomicspider2 import BaseComicSpider2, font_color


class JoyhentaiSpider(BaseComicSpider2):
    name = 'joyhentai'
    allowed_domains = ['zh.joyhentai.pw', 'i0.nyacdn.com']
    search_url_head = 'https://zh.joyhentai.pw/search/q_'
    mappings = {'最新': 'https://zh.joyhentai.pw/latest/popular',
                '日排名': 'https://zh.joyhentai.pw/rank/popular',
                '周排名': 'https://zh.joyhentai.pw/rank/week',
                '月排名': 'https://zh.joyhentai.pw/rank/month',
                }

    def frame_book(self, response):
        frame_results = {}
        example_b = r' [ {} ]、【 {} 】'
        self.print_Q.put(example_b.format('序号', '漫画名') + '<br>')
        targets = response.xpath('//a[@class="target-by-blank"]')  # sign -*-
        title_xpath = './/p[@class="title"]/@title' if 'rank' in self.search_start else './/h3/text()'
        for x, target in enumerate(targets):
            title = target.xpath(title_xpath).get().strip()
            # img_url = target.xpath('.//img[@class="lazyload"]/@data-src').get()
            pre_url = target.xpath('./@href').get()
            url = f'https://zh.joyhentai.pw{pre_url}'
            self.print_Q.put(example_b.format(str(x + 1), title, chr(12288)))
            self.print_Q.put('') if (x + 1) % 6==0 else None
            frame_results[x + 1] = [title, url]
        return self.frame_book_print(frame_results)

    def frame_section(self, response):
        targets = response.xpath('//div[@class="col s12 m12 l12 center"]//img[@class="lazyload"]')  # sign -*-

        img_url_xpath = './@data-src'
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = target.xpath(img_url_xpath).get()
            frame_results[x + 1] = img_url
        self.print_Q.put("===============" + font_color(' 本子网没章节的 这本已经扔进任务了', 'blue'))
        return frame_results
