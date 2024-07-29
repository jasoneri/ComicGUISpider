#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
import typing as t
from functools import partial

from redis import asyncio as aioredis
from utils import Conf, ori_path

conf = Conf(path=ori_path.joinpath("utils/script"))
redis_conf: dict = conf.redis


class AioRClient(aioredis.Redis):
    """
    conf of ./conf.yml
    ```yaml
    redis:
      host: 127.0.0.1
      port: 6379
      db: 0
      password:
    ```
    """

    def __init__(self):
        """preset redis conf of utils/script/conf.yml"""
        super(AioRClient, self).__init__(host=redis_conf['host'], port=redis_conf['port'], db=redis_conf['db'])

    async def hgetall(self, name):
        """already decode && json.loads"""
        result = await super(AioRClient, self).hgetall(name)
        try:
            return {key.decode(): json.loads(value) for key, value in result.items()}
        except (json.decoder.JSONDecodeError, TypeError):
            return {key.decode(): value.decode() for key, value in result.items()}

    async def hget(self, name, key):
        """already json.loads"""
        result = await super(AioRClient, self).hget(name, key)
        try:
            return json.loads(result)
        except (json.decoder.JSONDecodeError, TypeError):
            return result

    async def rpush(self, name, *values):  # TODO(2024-07-29): json.dumps写在里面
        _values = tuple(map(partial(json.dumps, ensure_ascii=False), values))
        return await super(AioRClient, self).rpush(name, *_values)

    async def lpop(self, name: str, count: t.Optional[int] = None) -> list:
        results = await super(AioRClient, self).lpop(name, count)
        if isinstance(results, str):
            results = [results]
        elif results is None:
            results = []
        return list(map(json.loads, results))
