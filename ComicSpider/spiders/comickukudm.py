# -*- coding: utf-8 -*-
from asyncio import run
from aiohttp import ClientSession
import re
from lxml import etree
from urllib.parse import quote
from ComicSpider.items import ComicspiderItem
from ComicSpider.spiders.basecomicspider import BaseComicSpider


class ComickukudmSpider(BaseComicSpider):
    name = 'comickukudm'
    allowed_domains = ['m.kukudm.com', 'm.kkkkdm.com', 'wap.kukudm.com']
    search_url_head = 'https://so.kukudm.com/m_search.asp?kw='
    mappings = {'推荐': 'https://wap.kukudm.com/',
                '更新': 'https://wap.kukudm.com/top100.htm'}

    @property
    def search(self):
        search_start = super(ComickukudmSpider, self).search
        if 'm_search.asp' in search_start:
            _keyword = search_start.split('kw=')[1]
            search_start = f"{self.search_url_head}{quote(f'{_keyword}'.encode('gb2312'))}"
        return search_start

    def frame_book(self, response):
        async def fetch(session, url):
            resp = await session.get(url)
            try:
                return await resp.text()
            except UnicodeDecodeError:
                return await resp.text('gbk')

        async def main(urls):
            async with ClientSession() as session:
                try:
                    example_b = r' {}、   《{}》   【{}】    [{}]   [{}]'
                    self.print_Q.put(
                        '<br>' + example_b.format('序号', '漫画名', '作者', '更新时间', '最新章节') + ' ( 这网有点慢稍等几秒 )<br>')
                    for x, url in enumerate(urls):
                        if 'http' not in url:
                            url = f'https://wap.kukudm.com{url}'
                        html = await fetch(session, url)
                        _resp = etree.HTML(html)
                        title = _resp.xpath('.//div[@id="comicName"]/text()')[0].strip()
                        author = _resp.xpath('.//p[@class="txtItme"]/text()')[0].strip()
                        refresh_time = _resp.xpath('.//span[@class="date"]/text()')[0].strip()
                        refresh_section = _resp.xpath('.//div[@id="list"]//a/text()')[0].strip()
                        sort_print.append(
                            [x, example_b.format(str(x + 1), title, author, refresh_time, refresh_section, chr(12288))])
                        frame_results[x + 1] = [title, url]
                except Exception as e:
                    self.logger.error(f'又是你出错喔kukudm: {str(type(e))}:: {str(e)}')

        sort_print = []
        frame_results = {}
        target = '//div[@class="itemImg"]/a/@href' if 'top100' in self.search_start else '//div[@class="imgBox"]//li//a[contains(@class, "ImgA")]/@href'  # -*-
        urls = response.xpath(target).getall()
        run(main(urls))

        sort_print = sorted(sort_print, key=lambda x: x[0])
        for show in sort_print:
            self.print_Q.put(show[1])

        return self.frame_book_print(frame_results, extra=" →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选<br>")

    def frame_section(self, response):
        frame_results = {}
        example_s = ' -{}、【{}】'
        self.print_Q.put(example_s.format('序号', '章节') + '<br>')
        targets = response.xpath('//div[@id="list"]//a')  # sign -*-
        for x, target in enumerate(targets):
            _section_url = target.xpath('./@href').get()
            section_url = f"https://m.kkkkdm.com/{_section_url}"
            section = target.xpath('./text()').get()
            frame_results[x + 1] = [section, section_url]
        return self.frame_section_print(frame_results, print_example=example_s, print_limit=4)

    def mk_page_tasks(self, **kw):
        try:
            _response = etree.HTML(kw['session'].get(kw['url']).content.decode('gbk'))
            total_page_div = _response.xpath('//ul[@class="subNav"]/li/following-sibling::li[1]/text()')[0]
            total_page = int(re.search(r'(\d+)/(\d+)', total_page_div).group(2))
            _compile = re.compile(r'[\\/][\d]+\.htm')
            url_list = list(map(lambda x: _compile.sub(f'/{x}.htm', kw['url']), range(total_page + 1)[1:]))
        except Exception as e:
            self.logger.error(f"可能是域名或者页面框架换了，手动看看能不能打开这页面{kw['url']}\ntraceback: {str(type(e))}:: {str(e)}")
        else:
            return url_list
            
    def parse_fin_page(self, response):
        item = ComicspiderItem()
        item['title'] = response.meta.get('title')
        item['section'] = response.meta.get('section')

        page_div = response.xpath('//ul[@class="subNav"]/li/following-sibling::li[1]/text()').get()  # sign -*-
        item['page'] = re.search(r'(\d+)/(\d+)', page_div).group(1)

        # 该网站url规则：urlencode化
        short_url = re.search(r"""<IMG SRC='"(.*?)"(.*?kuku.*?\.(jpg|png))'>?""", response.text)[2]
        transfer_url = "".join(('https://s1.kukudm.com/', quote(f'{short_url}'.encode('utf-8'))))
        item['image_urls'] = [f"{transfer_url}"]
        self.total += 1
        yield item

