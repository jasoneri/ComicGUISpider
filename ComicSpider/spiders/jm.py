# -*- coding: utf-8 -*-
import re
import typing as t
from urllib.parse import urlencode
from .basecomicspider import BaseComicSpider2, font_color
from utils.special import JmUtils

domain = JmUtils.get_domain()


class JmSpider(BaseComicSpider2):
    name = 'jm'
    custom_settings = {"ITEM_PIPELINES": {'ComicSpider.pipelines.JmComicPipeline': 50},
                       "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.UAMiddleware': 5}
                       }
    num_of_row = 4
    domain = domain
    mappings = {}

    time_regex = re.compile(r".*?([日周月总])")
    kind_regex = re.compile(r".*?(更新|点击|评分|评论|收藏)")
    expand_map: t.Dict[str, dict] = {
        "日": {'t': 't'}, "周": {'t': 'w'}, "月": {'t': 'm'}, "总": {'t': 'a'},
        "更新": {'o': 'mr'}, "点击": {'o': 'mv'}, "评分": {'o': 'tr'}, "评论": {'o': 'md'}, "收藏": {'o': 'tf'}
    }

    @property
    def ua(self):
        return {
            'Host': self.domain,
            'User-Agent': 'Mozilla/5.0(WindowsNT10.0;Win64;x64;rv:127.0)Gecko/20100101Firefox/127.0',
            'Accept': 'image/webp;application/xml;q=0.9;image/avif;application/xhtml+xml;text/html;*/*;q=0.8',
            'Accept-Language': 'zh;q=0.8;en;q=0.2;zh-CN;zh-TW;q=0.7;zh-HK;q=0.5;en-US;q=0.3',
            'Accept-Encoding': 'br;zstd;deflate;gzip',
            'Alt-Used': self.domain,
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1', 'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-User': '?1',
            'Priority': 'u=1', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache', 'TE': 'trailers'
        }

    @property
    def search_url_head(self):
        return f'https://{self.domain}/search/photos?search_query='

    @property
    def search(self):
        keyword = self.input_state.keyword
        __t = self.time_regex.search(keyword)
        __k = self.kind_regex.search(keyword)
        if not bool(__k):  # 不好说标题匹配到关键字情况，视情况返至前置带*触发
            return f"{self.search_url_head}{keyword}"
        _t = __t.group(1) if bool(__t) else '周'
        _k = __k.group(1) if bool(__k) else '点击'
        params = {**self.expand_map[_t], **self.expand_map[_k]}
        url = f"https://{self.domain}/albums?{urlencode(params)}"
        if len(keyword) > 4:
            url += keyword[4:]
        return url

    def frame_book(self, response):
        frame_results = {}
        example_b = r' [ {} ]、【 {} 】'
        self.say(example_b.format('序号', '漫画名') + '<br>')
        targets = response.xpath('//div[contains(@class,"thumb-overlay")]')
        for x, target in enumerate(targets):
            title = target.xpath('.//img/@title').get().strip().replace("\n", "")
            pre_url = '/'.join(target.xpath('../@href | ./a/@href').get().split('/')[:-1])
            url = f'https://{domain}{pre_url}'.replace('album', 'photo')
            self.say(example_b.format(str(x + 1), title, chr(12288)))
            self.say('') if (x + 1) % self.num_of_row == 0 else None
            frame_results[x + 1] = [title, url]
        return self.say.frame_book_print(frame_results)

    def frame_section(self, response):
        targets = response.xpath(".//img[contains(@id,'album_photo_')]")
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = target.xpath('./@data-original').get()
            frame_results[x + 1] = img_url
        self.say("=" * 15 + font_color(' 本子网没章节的 这本已经扔进任务了', color='blue'))
        return frame_results
