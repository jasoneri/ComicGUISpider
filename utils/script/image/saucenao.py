import os
import pathlib
import typing as t
import httpx
import asyncio
import aiofiles
import urllib.parse as urlparse
from loguru import logger
from abc import abstractmethod
from tqdm import tqdm
from lxml import etree
from utils import Conf, ori_path

conf = Conf(path=ori_path.joinpath("utils/script"))
# proxy = {"https://": f"http://{conf.proxies[0]}"}
proxy = None


class SauceNAO:
    """
    saucenao IP Frequency Limiting, resp of 439
    your IP has exceeded the unregistered user's rate limit of 3 searches every 30 seconds
    30s: limit 3
    24h: limit 100
    ... but normal registered-user just 30s limit 4 ...
    """
    limit = 3
    similarity_threshold = 0.9

    def __init__(self, imgurs):
        self.sess = httpx.AsyncClient(headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Origin": "https://saucenao.com",
            # "Connection": "keep-alive",
            "Referer": "https://saucenao.com/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers"
        })
        if proxy:
            self.sess.proxies = proxy
        self.imgurs = imgurs

    async def upload(self, file):
        resp = await self.sess.post("https://saucenao.com/search.php",
                                    files={'file': file}, timeout=15)
        return resp.text

    async def parse_result(self, target_name, html_text) -> t.Optional[tuple]:
        html = etree.HTML(html_text)
        for el in html.xpath('//td[@class="resulttablecontent"]'):
            similarity_str = el.xpath('.//div[@class="resultsimilarityinfo"]/text()')[0]
            similarity = float(similarity_str.rstrip("%")) / 100.0
            for imgur in self.imgurs:
                matched = await eval(imgur).match_rule_from_saucenao(similarity, el)
                if matched:
                    logger.debug(f'[{target_name}] matched [{matched[-1]}], similarity: {similarity}')
                    return matched
        return


class Imgur:
    @staticmethod
    def domain_replace(url):
        return url

    async def req(self, sess, _url, _type='content'):
        resp = await sess.get(_url, follow_redirects=True)
        return getattr(resp, _type)

    @staticmethod
    @abstractmethod
    def parse(html_text) -> str:
        ...

    @classmethod
    @abstractmethod
    async def match_rule_from_saucenao(cls, similarity, el) -> t.Optional[t.Tuple[str, str]]:
        """各图床自主匹配规则
        :return url, match_db
        """
        return

    async def main(self, url):
        async with httpx.AsyncClient(proxies=proxy) as sess:
            show_text = await self.req(sess, url, "text")
            origin_img_url = self.parse(show_text)
            filename = origin_img_url.split('/')[-1]  # db of booru commonly this
            return await self.req(sess, origin_img_url), filename


class Danbooru(Imgur):
    """danbooru.donmai.us"""
    similarity_threshold = 0.9

    @classmethod
    async def match_rule_from_saucenao(cls, similarity, el):
        if similarity > cls.similarity_threshold:
            urls = list(filter(lambda x: 'danbooru' in x, el.xpath('.//a/@href')))
            if urls:
                return urls[0], 'Danbooru'
        return

    @staticmethod
    def domain_replace(url):
        """以下域名国内可用"""
        # sonohara、kagamihara、hijiribe
        return url.replace('danbooru', 'sonohara')  # .replace('/show', '')

    @staticmethod
    def parse(html_text):
        html = etree.HTML(html_text)
        section = html.xpath('//section[@id="content"]')
        if section[0].xpath('.//p/a[@href="/upgrade"]'):
            raise ValueError(''.join(section[0].xpath('.//p/a/text()')))
        img_url = (section[0].xpath('.//a[@class="image-view-original-link"]/@href') or
                   section[0].xpath('.//img[@id="image"]/@src'))[0]
        return img_url


class Yande(Imgur):
    """yande.re
    proxy is necessary
    """
    similarity_threshold = 0.8

    @classmethod
    async def match_rule_from_saucenao(cls, similarity, el):
        if similarity > cls.similarity_threshold:
            urls = list(filter(lambda x: 'yande.re' in x, el.xpath('.//a/@href')))
            if urls:
                return urls[0], 'Yande'
        return

    @staticmethod
    def parse(html_text):
        html = etree.HTML(html_text)
        # 2024-07-25: notice whether account-registered be require like Danbooru
        # if html.xpath('//p/a[@href="/upgrade"]'):
        #     raise ValueError(''.join(section[0].xpath('.//p/a/text()')))
        img_url = (html.xpath('//a[@id="png"]/@href') or html.xpath('//a[@id="highres"]/@href') or
                   html.xpath('//img[@id="image"]/@src'))[0]
        return img_url


def get_tasks(path, first):
    _ = filter(lambda x: not x.is_dir(), path.iterdir())
    __ = sorted(_, key=lambda x: os.path.getsize(x.absolute()))
    if len(__) <= SauceNAO.limit:
        return __
    first_index = __.index(path.joinpath(first)) if first else 0
    return __[first_index:first_index + SauceNAO.limit]


def get_hd_img(path, first=None, imgur_module: list = None):
    target_path = path
    output_path = target_path.joinpath('hd')
    output_path.mkdir(exist_ok=True)
    targets = get_tasks(target_path, first)

    async def step_sauce(_targets: iter):
        infos = {}
        for target in _targets:
            saucenao = SauceNAO(imgur_module)
            with open(target_path.joinpath(target.name), 'rb') as f:
                text = await saucenao.upload(f)
            info = await saucenao.parse_result(target.name, text)
            if not info:
                logger.info(f'{imgur_module} dbs not find[{target.name}]')
                continue
            infos[target.name] = info
        return infos

    async def step_imgur(infos):
        for name, info in tqdm(infos.items()):
            url, sure_imgur_module = info
            imgur = eval(sure_imgur_module)()
            url = imgur.domain_replace(url)
            try:
                content, file_name_from_imgur = await imgur.main(url)
                file_name = urlparse.unquote(file_name_from_imgur) or name
                async with aiofiles.open(output_path.joinpath(file_name), 'wb') as f:
                    await f.write(content)
            except Exception as e:
                logger.exception(str(e))
                logger.warning(f'[{name}] {url}')

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    imgur_infos = loop.run_until_complete(step_sauce(targets))
    loop.run_until_complete(step_imgur(imgur_infos))


if __name__ == '__main__':
    get_hd_img(
        pathlib.Path(r'D:\pic\__convert'),
        # first="e36105fa2a5e1a6ecc3d80e11c6946aa-sample - 副本.jpg"
        imgur_module=['Yande', 'Danbooru']
    )
