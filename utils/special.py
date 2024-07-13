#!/usr/bin/python
# -*- coding: utf-8 -*-
import hashlib
import math
import re
from PIL import Image
from io import BytesIO
import httpx


class JmUtils:
    forever_url = "https://jm365.work/3YeBdF"

    class JmImage:
        regex = re.compile(r"(\d+)/(\d+)")
        epsId = None  # 书id '536323'
        scramble_id = None  # 页数(带前缀0) '00020'

        def convert_img(self, img_content: bytes):
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
        cli = httpx.Client()
        resp = cli.get(cls.forever_url)
        if str(resp.status_code).startswith('3'):
            return re.search(r"http[s]?://(.*)", str(resp.next_request.url)).group(1)
        else:
            raise ConnectionError(f"永久网址[{cls.forever_url}]似乎失效了，需要更新")


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
