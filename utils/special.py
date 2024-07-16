#!/usr/bin/python
# -*- coding: utf-8 -*-
import hashlib
import math
import re
from PIL import Image
from io import BytesIO
import httpx
from lxml import etree


class JmUtils:
    forever_url = "https://jm365.work/3YeBdF"
    publish_url = "https://jm365.work/mJ8rWd"
    status_forever = True
    status_publish = True

    class JmImage:
        regex = re.compile(r"(\d+)/(\d+)")
        epsId = None  # 书id '536323'
        scramble_id = None  # 页数(带前缀0) '00020'

        def convert_img(self, img_content: bytes) -> Image:
            self.epsId = int(self.epsId)

            def get_num():
                def _get_num(__: int):
                    string = str(self.epsId) + self.scramble_id
                    string = string.encode()
                    string = hashlib.md5(string).hexdigest()
                    _ = ord(string[-1])
                    _ %= __
                    return _ * 2 + 2

                if self.epsId < 220980:
                    return 0
                elif self.epsId < 268850:
                    return 10
                elif self.epsId > 421926:
                    return _get_num(8)
                else:
                    return _get_num(10)

            num = get_num()
            img = BytesIO(img_content)
            srcImg = Image.open(img)
            if not num:
                return srcImg
            size = (width, height) = srcImg.size
            desImg = Image.new(srcImg.mode, size)
            rem = height % num
            copyHeight = math.floor(height / num)
            block = []
            totalH = 0
            for i in range(num):
                h = copyHeight * (i + 1)
                if i == num - 1:
                    h += rem
                block.append((totalH, h))
                totalH = h
            h = 0
            for start, end in reversed(block):
                coH = end - start
                temp_img = srcImg.crop((0, start, width, end))
                desImg.paste(temp_img, (0, h, width, h + coH))
                h += coH
            srcImg.close()
            del img
            return desImg

        @classmethod
        def by_url(cls, url):
            obj = cls()
            obj.epsId, obj.scramble_id = cls.regex.search(url).groups()
            return obj

    @classmethod
    def get_domain(cls):
        def by_forever():
            try:
                resp = cli.get(cls.forever_url, follow_redirects=True)
            except httpx.ConnectError:
                cls.status_forever = False
                print(f"永久网址[{cls.forever_url}]失效了")  # logger.warning()
            else:
                # return re.search(r"https?://(.*)", str(resp.next_request.url)).group(1)
                return re.search(r"https?://(.*)/", str(resp.request.url)).group(1)

        def by_publish():
            resp = cli.get(cls.publish_url, follow_redirects=True)
            if str(resp.status_code).startswith('2'):
                return cls.parse_publish(resp.text)
            else:
                cls.status_publish = False
                print(f"发布页获取[{cls.publish_url}]失效了")  # logger.warning()

        cli = httpx.Client(headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Alt-Used": "jm365.work",
            "Connection": "keep-alive",
            "Priority": "u=0, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers"
        })
        domain = by_publish() or by_forever() or None  # 控制顺序，例如永久页长期没恢复就前置从发布页获取
        if not cls.status_forever and not cls.status_publish:
            raise ConnectionError(f"无法获取domain，方法均失效了，需要查看")
        return domain

    @classmethod
    def parse_publish(cls, html_text):
        html = etree.HTML(html_text)
        ps = html.xpath('//div[@class="main"]/p')
        order_p = list(filter(lambda p: '內地' in ''.join(p.xpath('.//text()')), ps))  # 小心这个"内"字是繁体
        if order_p:
            domain = order_p[0].xpath('.//text()')[-1].strip()
            return domain
        else:
            cls.status_publish = False
            print(f"发布页[{cls.publish_url}]清洗失效")  # logger.warning()
            return None


chn_regex = re.compile(r"汉化|漢化|粵化|DL版|修正|中国|翻訳|翻译|翻譯|中文|後編|前編|カラー化|個人|" +
                       r"無修|重修|重嵌|机翻|機翻|整合|黑字|Chinese|Japanese|\[Digital]|vol|\[\d+]")


def set_author_ahead(title: str) -> str:
    author_ = re.findall(r"\[.*?]", title)
    if bool(re.search(r"[(（]", "".join(author_))):  # 优先选标签内带括号
        author_ = list(filter(lambda x: bool(re.search(r"[(（]", x)), author_))
    else:  # 采用排除法筛选
        author_ = list(filter(lambda x: not bool(chn_regex.search(x)), author_))
    if len(author_) > 1:
        if len(set(author_)) == 1:  # 去除重复标签
            author_ = [author_[0]]
        else:
            # logger.warning(f"匹配待改善 {author_=}")
            return title
    elif not author_:
        return title
    author = author_[0]
    return author + title.replace(author, '').replace("  ", " ")


def get_one_extra():
    import asyncio
    import aiofiles
    from lxml import etree
    import pathlib as p
    from tqdm.asyncio import tqdm
    from utils import conf

    name = "おもちゃの人生"  # dmkumh.com
    book_html = r"../test/analyze/temp/temp.html"
    tar_path = p.Path(conf.sv_path).joinpath(r"本子\web", name)

    async def do(targets):
        async def pic_fetch(sess, url):
            resp = await sess.get(url)
            return resp.content

        async with httpx.AsyncClient() as sess:
            for page, url in tqdm(targets.items()):
                content = await pic_fetch(sess, url)
                async with aiofiles.open(tar_path.joinpath(f"第{page}页.jpg"), 'wb') as f:
                    await f.write(content)

    tar_path.mkdir(exist_ok=True)
    with open(book_html, 'r', encoding='utf-8') as f:
        html = etree.HTML(f.read())
    divs = html.xpath("//div[contains(@class, 'rd-article-wr')]/div")
    targets = {div.xpath("./@data-index")[0]: div.xpath("./img/@data-original")[0]
               for div in divs}
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do(targets))
