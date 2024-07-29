#!/usr/bin/python
# -*- coding: utf-8 -*-
import datetime
import json
import pathlib as p
import httpx
import asyncio
import aiofiles
from dataclasses import dataclass, asdict

from loguru import logger

from utils.script import conf, AioRClient

domain = "kemono.su"
headers = {'accept': 'application/json'}


@dataclass
class TaskMeta:
    user_name: str
    user_id: str
    service: str


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

    conf of ../conf.yml
    ```yaml
    kemono:
      sv_path: ...
      cookie: ...  # get from browser, filed 'session'
    ```
    """
    date_format = "%Y-%m-%dT%H:%M:%S"

    class Api:
        base = f"https://{domain}/api/v1"
        creator_posts = base + "/{service}/user/{creator_id}"
        favorites = base + "/account/favorites"
        file_prefix = "https://n1.kemono.su/data"

    def __init__(self, redis_cli: AioRClient):
        self.sess = httpx.AsyncClient()
        self.conf = conf.kemono
        self.redis = redis_cli
        self.redis_key = self.conf['redis_key']

    @staticmethod
    async def req(sess: httpx.AsyncClient, url, **kw):
        """post almost not use, detail for /api/schema?logged_in=yes&role=consumer"""
        resp = await sess.get(url, **kw)
        return resp

    async def get_favorites(self):
        resp = await self.req(self.sess, self.Api.favorites, headers=headers,
                              cookies={'session': self.conf.get('cookie')})
        return resp.json()

    async def get_creator_posts(self, creator_id, service, **kw):
        resp = await self.req(self.sess,
                              self.Api.creator_posts.format(creator_id=creator_id, service=service),
                              headers=headers, **kw)
        return resp.json()

    @logger.catch
    async def step1_tasks_create(self, interrupt_date):
        """
        :param interrupt_date: '%Y-%m-%d', prevent tasks too old and too large
        :return:
        """

        async def create_task_of_post(post, _task_meta: TaskMeta):
            """commonly values-of-attachments include value-of-file,
            special institution: value-of-file exist but values-of-attachments empty"""
            title = post.get('title')
            meta = asdict(_task_meta)
            tasks = post.get("attachments") or post.get("file") or []
            if isinstance(tasks, dict):
                tasks = [tasks]
            tasks = [{"url": self.Api.file_prefix + task.get("path"),
                      "meta": {**meta, "title": title, "file_name": task.get("name")}}
                     for task in tasks]
            if tasks:
                await self.redis.rpush(self.redis_key, *tasks)

        async def posts_of_creator(info):
            creator_id = info.get('id')
            name = info.get('name')
            service = info.get('service')
            task_meta = TaskMeta(user_name=name, user_id=creator_id, service=service)
            o = 0
            param = None
            while True:
                if o:
                    param = {"o": o}
                posts = await self.get_creator_posts(creator_id, service, params=param)
                valid_posts = list(filter(
                    lambda _: datetime.datetime.strptime(_.get('published'), self.date_format) >= interrupt, posts))
                for post in valid_posts:
                    await create_task_of_post(post, task_meta)
                if len(valid_posts) < 50:
                    break
                o += 50

        interrupt = datetime.datetime.strptime(interrupt_date, '%Y-%m-%d')
        favorites = await self.get_favorites()
        for favorite in favorites:
            await posts_of_creator(favorite)

    async def step2_get_tasks(self):
        out_tasks = []
        per_take = 10
        while True:
            tasks = await self.redis.lpop(self.redis_key, per_take)
            for task in tasks:
                meta = task['meta']
                path = p.Path(self.conf.get('sv_path')) \
                    .joinpath(f"{meta['user_name']}_{meta['service']}", meta['title'])
                file = path.joinpath(meta['file_name'])
                if file.exists():
                    logger.debug(f"[existed] {file}")
                    continue
                path.mkdir(parents=True, exist_ok=True)
                out_tasks.append(task)
            if not tasks or len(tasks) < per_take:
                break
        return out_tasks

    async def step2_run_task(self, _sem, task):
        async with _sem:
            url = task['url']
            meta = task['meta']
            path = p.Path(self.conf.get('sv_path')) \
                .joinpath(f"{meta['user_name']}_{meta['service']}", meta['title'])
            file = path.joinpath(meta['file_name'])
            async with httpx.AsyncClient(headers=headers) as cli:
                logger.debug(f"[crawling] {file}")
                resp = await self.req(cli, url, follow_redirects=True)
            async with aiofiles.open(file, 'wb') as f:
                await f.write(resp.content)
                logger.info(f"[success sv] {file}")

    async def temp_copy_vals(self, restore=False):
        a = self.redis_key
        b = f"{self.redis_key}_d"
        if restore:
            _ = a
            _d = b
            a = _d
            b = _
        elements = await self.redis.lrange(a, 0, -1)
        elements = list(map(json.loads, elements))
        # 将元素插入到新的列表
        await self.redis.rpush(b, *elements)


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    obj = Kemono(AioRClient())
    # loop.run_until_complete(obj.step1_tasks_create('2024-06-01'))
    loop.run_until_complete(obj.temp_copy_vals(True))

    tasks = loop.run_until_complete(obj.step2_get_tasks())
    sem = asyncio.Semaphore(5)
    __tasks = [loop.create_task(obj.step2_run_task(sem, task)) for task in tasks]
    loop.run_until_complete(asyncio.wait(__tasks))
