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
                def _get_num(order_num: int):
                    string = str(self.epsId) + self.scramble_id
                    string = string.encode()
                    string = hashlib.md5(string).hexdigest()
                    num = ord(string[-1])
                    num %= order_num
                    return num * 2 + 2

                if self.epsId < int(self.scramble_id):
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
