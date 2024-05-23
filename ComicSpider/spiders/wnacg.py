# -*- coding: utf-8 -*-
import re
from .basecomicspider import BaseComicSpider2, font_color

domain = "wnacg.com"


class WnacgSpider(BaseComicSpider2):
    name = 'wnacg'
    num_of_row = 4
    img_domain = 'img5.qy0.ru'  # TODO(2024-05-20): 加代理middleware
    allowed_domains = [domain, 'img5.qy0.ru', 't4.qy0.ru']
    search_url_head = f'https://{domain}/albums-index-tag-'
    index_regex = re.compile(r'aid-(\d+)\.html')
    mappings = {'更新': f'https://{domain}/albums.html',
                '汉化': f'https://{domain}/albums-index-cate-1.html',
                }

    @property
    def search(self):
        _ = super(WnacgSpider, self).search
        return f"{_}.html"

    @staticmethod
    def rule_book_index(index: str) -> str:
        len_index = len(index)
        index = f"{(6 - len_index) * '0'}{index}" if len_index < 6 else index
        return f"{index[:-2]}/{index[-2:]}"

    def frame_book(self, response):
        frame_results = {}
        example_b = r' [ {} ]、【 {} 】'
        self.say(example_b.format('序号', '漫画名') + '<br>')
        targets = response.xpath('//div[@class="info"]')
        title_xpath = './div[@class="title"]/a'
        for x, target in enumerate(targets):
            title_elem = target.xpath(title_xpath)
            title = title_elem.xpath('./@title').get()
            pre_url = title_elem.xpath('./@href').get()
            url = f'https://{domain}{pre_url}'.replace('index', 'gallery')
            self.say(example_b.format(str(x + 1), title, chr(12288)))
            self.say('') if (x + 1) % self.num_of_row == 0 else None
            frame_results[x + 1] = [title, url]
        return self.say.frame_book_print(frame_results)

    def frame_section(self, response):
        doc_wlns = re.split(r';[\n\s]+?document\.writeln', response.text)
        selected_doc = next(filter(lambda x: "var imglist" in x, doc_wlns))
        targets = re.findall(r'(//.*?(jp[e]?g|png|webp))', selected_doc)

        frame_results = {}
        for x, target in enumerate(targets):
            img_url = f"https:{target[0]}"
            frame_results[x + 1] = img_url
        self.say("===============" + font_color(' 本子网没章节的 这本已经扔进任务了', color='blue'))
        return frame_results
