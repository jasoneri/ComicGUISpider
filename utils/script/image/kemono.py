#!/usr/bin/python
# -*- coding: utf-8 -*-
import asyncio

import httpx

from utils import Conf, ori_path

domain = "kemono.su"
headers = {'accept': 'application/json'}
conf = Conf(path=ori_path.joinpath("utils/script"))


class Kemono:
    """
    Api-service:
      patreon   # Patreon
      fanbox    # Pixiv Fanbox
      # 音声似乎有点麻烦  Discord
      fantia    # Fantia
      # 爱发电没人上传  Afdian
      # 欧美的不要  Boosty
      gumroad   # Gumroad
      subscribestar  # SubscribeStar

    conf of ../settings.yml
    ```yaml
    kemono:
      sv_path: ...
      cookie: ...  # get from browser, filed 'session'
    ```
    """

    class Api:
        base = f"https://{domain}/api/v1"
        creator_posts = base + "/{service}/user/{creator_id}"
        favorites = base + "/account/favorites"
        img_prefix = "https://n1.kemono.su/data/"

    def __init__(self):
        self.sess = httpx.AsyncClient()
        self.conf = conf.kemono

    @staticmethod
    async def req(sess, url, **kw):
        """post almost not use, detail for /api/schema?logged_in=yes&role=consumer"""
        resp = await sess.get(url, **kw)
        return resp

    async def get_favorites(self):
        resp = await self.req(self.sess, self.Api.favorites, headers={**headers, 'Cookie': self.conf.get('cookie')})
        return resp.json()

    async def get_creator_posts(self):
        resp = await self.req(self.sess, self.Api.creator_posts)
        return resp.json()

    def main(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # TODO(2024-07-29):  分批次step1产生直到image——url的任务, 扔上redis上，task做个统一标准 {url, {meta}}
        #   step2开多个session下载
