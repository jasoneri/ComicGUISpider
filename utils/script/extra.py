#!/usr/bin/python
# -*- coding: utf-8 -*-
import httpx
from utils import ori_path


def get_one_extra():
    """
    jpr18.com
    dmkumh.com
    """
    import asyncio
    import aiofiles
    from lxml import etree
    import pathlib as p
    from tqdm.asyncio import tqdm
    from utils import conf

    name = "[野際かえで] おもちゃの人生3 [無修正] [sky110036漢化]"
    book_html = ori_path.joinpath(r"test/analyze/temp/temp.html")
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


if __name__ == '__main__':
    get_one_extra()
