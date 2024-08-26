# -*- coding: utf-8 -*-
import re

from .basecomicspider import BaseComicSpider2, font_color
from utils import PresetHtmlEl
from utils.special import WnacgUtils
from utils.processed_class import PreviewHtml

domain = "wnacg.com"


class WnacgSpider(BaseComicSpider2):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.ComicDlProxyMiddleware': 5}}
    name = 'wnacg'
    num_of_row = 4
    domain = domain
    # allowed_domains = [domain]
    search_url_head = f'https://{domain}/search/?f=_all&s=create_time_DESC&syn=yes&q='
    mappings = {'更新': f'https://{domain}/albums-index.html',
                '汉化': f'https://{domain}/albums-index-cate-1.html', }
    turn_page_search = r"p=\d+"
    turn_page_info = (r"-page-\d+", "albums-index%s")

    def start_requests(self):
        if self.settings.get("PROXY_CUST") is None:
            self.domain = WnacgUtils.get_domain()
        return super(WnacgSpider, self).start_requests()

    @staticmethod
    def rule_book_index(book_index: str) -> str:
        len_index = len(book_index)
        book_index = f"{(6 - len_index) * '0'}{book_index}" if len_index < 6 else book_index
        return f"{book_index[:-2]}/{book_index[-2:]}"

    def frame_book(self, response):
        frame_results = {}
        example_b = r' [ {} ]、【 {} 】'
        self.say(example_b.format('序号', '漫画名') + '<br>')
        preview = PreviewHtml(response.url)
        targets = response.xpath('//li[contains(@class, "gallary_item")]')
        title_xpath = './div[contains(@class, "pic")]/a'
        for x, target in enumerate(targets):
            item_elem = target.xpath(title_xpath)
            title = item_elem.xpath('./@title').get()
            pre_url = item_elem.xpath('./@href').get()
            preview_url = f'https://{self.domain}{pre_url}'  # 人类行为读取的页面
            url = preview_url.replace('index', 'gallery')  # 压缩步骤，此链直接返回该本全页uri
            img_preview = 'http:' + item_elem.xpath('./img/@src').get()
            self.say(example_b.format(str(x + 1), title, chr(12288)))
            self.say('') if (x + 1) % self.num_of_row == 0 else None
            frame_results[x + 1] = [url, title]
            preview.add(x + 1, img_preview, PresetHtmlEl.sub(title), preview_url)  # 其实title已兜底处理，但preview受其影响所以前置一下
        self.say(preview.created_temp_html)
        return self.say.frame_book_print(frame_results, url=response.url)

    def frame_section(self, response):
        doc_wlns = re.split(r';[\n\s]+?document\.writeln', response.text)
        selected_doc = next(filter(lambda _: "var imglist" in _, doc_wlns))
        targets = re.findall(r'(//.*?(jp[e]?g|png|webp))', selected_doc)
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = f"https:{target[0]}"
            frame_results[x + 1] = img_url
        self.say("=" * 15 + font_color(' 本子网没章节的 这本已经扔进任务了', color='blue'))
        return frame_results
