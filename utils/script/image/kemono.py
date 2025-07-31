#!/usr/bin/python
# -*- coding: utf-8 -*-
import datetime
import argparse
import json
import re
import os
import sys
import shutil
import asyncio
import pickle
import pathlib as p
from dataclasses import dataclass, asdict

import yaml
import httpx
import pandas as pd
from loguru import logger
import tqdm

proj_p = p.Path(__file__).parent.parent.parent.parent
sys.path.append(str(proj_p))
from utils.script import conf, AioRClient, BlackList
from utils.script.image.expander import ArtistsEnum, Filter
from utils.config.qc import kemono_cfg
temp_p = proj_p.joinpath("__temp")
temp_p.mkdir(parents=True, exist_ok=True)


@dataclass
class KemonoAuthor:
    id: str
    name: str
    service: str
    updated: int
    favorited: int


kemono_topic = """
  ┏┓┏┓┏┓  ┓            
  ┃ ┃┓┗┓━━┃┏┏┓┏┳┓┏┓┏┓┏┓
  ┗┛┗┛┗┛  ┛┗┗ ┛┗┗┗┛┛┗┗┛
"""
domain = "kemono.cr"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    'Accept': 'application/json',
}


class OverSizeErr(Exception):
    ...


@dataclass
class TaskMeta:
    user_name: str
    user_id: str
    service: str


t_format = '%Y-%m-%dT%H:%M:%S'


def time_format(_):
    try:
        return datetime.datetime.strptime(_, t_format)
    except ValueError:
        return datetime.datetime.strptime(_.split(".")[0], t_format)


class ListArtistsInfo:
    def __init__(self, order_l: list):
        self.order_l = order_l

    def match(self, _info):
        df = pd.DataFrame(_info)
        out = []
        for search_input in self.order_l:
            if isinstance(search_input, str):
                _df = df[df['name'].str.contains(search_input.strip(), na=False)]
                if not _df.empty:
                    out.extend(_df.to_dict(orient='records'))
            elif isinstance(search_input, list) and len(search_input) == 2:
                _df = df[(df['name'] == search_input[0].strip()) & (df['service'] == search_input[1])]
                if not _df.empty:
                    out.extend(_df.to_dict(orient='records'))
        for _ in out:
            yield _


class Api:
    base = f"https://{domain}/api/v1"
    creator_posts = base + "/{service}/user/{creator_id}"
    post = base + "/{service}/user/{creator_id}/post/{post_id}"
    favorites = base + "/account/favorites"
    file_prefix = "https://n3.kemono.cr"
    creators_txt = base + "/creators.txt"

    def __init__(self, conf):
        if conf.proxies:
            self.sess = httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(http2=True,
                    proxy=f"http://{conf.proxies[0]}", retries=3)
            )
        else:
            self.sess = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(http2=True, retries=2))
        self.conf = conf.kemono

    async def req(self, url, method="GET", **kw):
        """post almost not use, detail for /api/schema?logged_in=yes&role=consumer"""
        if not kw.get("timeout"):
            kw.update(timeout=30)
        resp = await self.sess.request(method, url, **kw)
        return resp

    async def get_favorites(self):
        resp = await self.req(self.favorites, headers=headers,
                              cookies={'session': self.conf.get("cookie")})
        return resp.json()

    async def get_creator_posts(self, creator_id, service, **kw):
        resp = await self.req(self.creator_posts.format(creator_id=creator_id, service=service),
                              headers=headers, **kw)
        return resp.json()

    async def get_post(self, creator_id, service, post_id, **kw):
        resp = await self.req(self.post.format(creator_id=creator_id, service=service, post_id=post_id),
                              headers=headers, **kw)
        return resp.json()


class RPC:
    url = "http://localhost:16800/jsonrpc"
    
    @staticmethod
    def format_data(params: list, method="aria2.addUri", _id=None):
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": _id
        }
    
    def __init__(self) -> None:
        self.sess = httpx.AsyncClient()

    async def check_gid_status(self, gid):
        try:
            status_resp = await self.sess.request(
                "POST", self.url, headers={"Content-Type": "application/json"}, 
                json=self.format_data([gid], method="aria2.tellStatus"))
            status_resp_json = status_resp.json()
            return (gid, status_resp_json)
        except Exception as e:
            return (gid, {"error": str(e)})


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
    file_size_limit = 100 * 1024 * 1024  # 100mb
    suffixes = ['jpg', 'jpeg', 'png', 'gif', 'mp4']

    def __init__(self, redis_cli: AioRClient):
        self.conf = conf.kemono
        self.api = Api(conf)
        self.rpc = RPC()
        qconfig_text = kemono_cfg.filterText.value
        if qconfig_text.strip():
            filter_dict = yaml.safe_load(qconfig_text)
        else:
            filter_dict = self.conf.get('filter', {})
        self.f = Filter(filter_dict)
        self.redis = redis_cli
        self.redis_key = self.conf['redis_key']
        self.sv_path = p.Path(self.conf.get('sv_path'))
        self.sorted_record = self.sv_path.joinpath('__sorted_record')
        self.blacklist_obj = BlackList(self.sv_path / 'blacklist.json')
        self.blacklist = self.blacklist_obj.read()

    class Creator:
        cache_path = temp_p.joinpath("kemono_data.pkl")
        
        def __init__(self, parent, **ckw):
            self.k = parent
            self.ckw = ckw
            self.start_date = datetime.datetime.strptime(self.ckw.get('start_date'), r'%Y-%m-%d')
            self.end_date = datetime.datetime.strptime(self.ckw.get('end_date'), r'%Y-%m-%d')

        async def create_task_of_post(self, post, _task_meta: TaskMeta):
            """commonly values-of-attachments include value-of-file,
            special institution: value-of-file exist but values-of-attachments empty"""
            title = post.get('title').strip()
            published = time_format(post.get('published')).strftime("%Y-%m-%d")
            meta = asdict(_task_meta)
            tasks = post.get("attachments", [])
            file = post.get("file")
            preview_post = await self.k.api.get_post(post.get("user"), post.get("service"), post.get("id"))
            preview = preview_post.get("previews", [])
            server_map = {_['name']: _['server'] for _ in preview}
            if file and file not in tasks:
                tasks = [file, *tasks]
            post_tasks = [
                {"url": f'''{server_map.get(task["name"], self.k.api.file_prefix)}/data{task.get("path")}?f={task.get("name")}''',
                    "file_name": task.get("name")} 
                for task in tqdm.tqdm(tasks, ncols=100, desc=f"[{published}]{title}")
                if not self.k.f.file(task.get("name"))
            ]
            redis_task = {
                "tasks": post_tasks, "meta": {**meta, "published": published, "title": title}
            }
            if tasks:
                this_artist_record = self.k.sorted_record.joinpath(f'{_task_meta.user_name}_{_task_meta.service}')
                this_artist_record.mkdir(parents=True, exist_ok=True)
                this_post_record = this_artist_record.joinpath(f'[{published}]{title}.json')
                if not this_post_record.exists():
                    with open(this_post_record, 'w', encoding='utf-8') as f:
                        json.dump([_['name'] for _ in tasks], f, ensure_ascii=False)
                await self.k.redis.rpush(self.k.redis_key, redis_task)

        async def _filter(self, posts, _info):
            valid_posts = list(filter(lambda _: 
                self.end_date >= time_format(_.get('published')) >= self.start_date, 
                posts))
            """get filter from kemono_expander.Artists etc."""
            if valid_posts:
                if hasattr(self.k.f.Artists, _info["name"]):
                    _expander = getattr(self.k.f.Artists, _info["name"])
                elif _info["id"] in ArtistsEnum:
                    _expander = getattr(self.k.f.Artists, ArtistsEnum(_info["id"]).name)
                else:
                    _expander = self.k.f.Artists.base_process
                valid_posts = _expander(valid_posts)
                return valid_posts
            else:
                return []

        async def posts_of_creator(self, info):
            creator_id = info.get('id')
            name = info.get('name')
            service = info.get('service')
            task_meta = TaskMeta(user_name=name, user_id=creator_id, service=service)
            o = 0
            param = None
            while True:
                if o:
                    param = {"o": o}
                posts = await self.k.api.get_creator_posts(creator_id, service, params=param)
                valid_posts = await self._filter(posts, info)
                for post in valid_posts:
                    await self.create_task_of_post(post, task_meta)
                if len(posts) < 50:
                    break
                o += 50

        @logger.catch
        async def by_favorites(self, order_creators=None):
            """only by favorites of your account
            :param order_creators: list
            :param start/end _date: '%Y-%m-%d', prevent tasks too old and too large
            """
            favorites = await self.k.api.get_favorites()
            order_creators = order_creators or ListArtistsInfo(
                list(map(lambda _: [_.get('name'), _.get('service')], favorites)))
            for matched in order_creators.match(favorites):
                await self.posts_of_creator(matched)

        @logger.catch
        async def by_creatorid(self, order_creatorids=None):
            order_creatorids = set(map(str, order_creatorids))
            all_creators = None
            if self.cache_path.exists():
                with open(self.cache_path, 'rb') as f:
                    all_creators = pickle.load(f)
            else:
                all_creators = await self._download_and_cache_kemono_data()

            found_ids = set()
            for creator_id in order_creatorids:
                if creator_id in all_creators:
                    creator = all_creators[creator_id]
                    found_ids.add(creator_id)
                    creatorinfo = asdict(creator)
                    await self.posts_of_creator(creatorinfo)
            not_found = order_creatorids - found_ids
            if not_found:
                logger.warning(f"not found creatorid: {not_found}")

        async def _download_and_cache_kemono_data(self):
            """下载kemono创作者数据并转换为KemonoAuthor映射字典"""
            creators_txt = temp_p.joinpath("creators.txt")
            if not creators_txt.exists():
                _data = [[Api.creators_txt], {"dir": str(temp_p)}]
                resp = await self.k.rpc.sess.request(
                    "POST", RPC.url, headers={"Content-Type": "application/json"},
                    json=RPC.format_data(_data, _id="creators.txt"))
                add_result = resp.json()
                gid = add_result.get('result')
                
                run_flag = True
                while run_flag:
                    status_tasks = [self.k.rpc.check_gid_status(gid)]
                    results = await asyncio.gather(*status_tasks)
                    for gid, result in results:
                        if 'error' in result:
                            result = {'result': {'status': 'error'}}
                        status = result.get('result', {}).get('status')
                        if status == 'complete':
                            run_flag = False
                        elif status == 'error':
                            raise ValueError(f"""Download creators.txt failed,\n
                                you can download it from {Api.creators_txt},\n
                            then put it into {creators_txt}""")
                    await asyncio.sleep(1.5)
            with open(creators_txt, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            author_dict = {}
            for item in json_data:
                author_id = item['id']
                author = KemonoAuthor(
                    id=author_id, name=item['name'], service=item['service'],
                    updated=item['updated'], favorited=item['favorited']
                )
                author_dict[author_id] = author
            with open(self.cache_path, 'wb') as f:
                pickle.dump(author_dict, f)

            return author_dict

    def run_filter(self, u_s, p_t, _task) -> bool:
        """
        :param u_s: user_service
        :param p_t: [published]title
        """
        flag = False
        already = []
        post_path = self.sv_path.joinpath(rf"{u_s}\{p_t}")
        if post_path.exists():
            for file in post_path.iterdir():
                if file.stat().st_size == 146:
                    # 146 bytes, empty file
                    os.remove(file)
                else:
                    already.append(file.name)
        _task["tasks"] = [_ for _ in _task["tasks"] if _["file_name"] not in already]
        if (not _task["tasks"]
                or u_s in self.blacklist
                or rf"{u_s}/{p_t}" in self.blacklist
                or p_t in self.blacklist  # not sure p_t whether recurring on other creator
        ):
            flag = True
        return flag

    async def step2_get_tasks(self):
        out_tasks = []
        per_take = 10
        while True:
            tasks = await self.redis.lpop(self.redis_key, per_take)
            for task in tasks:
                meta = task['meta']
                user_service = f"{meta['user_name']}_{meta['service']}"
                published_title = f"[{meta['published']}]{meta['title']}".strip()
                path = self.sv_path.joinpath(user_service, published_title)
                if self.run_filter(user_service, published_title, task):
                    logger.debug(rf"[filtered] {user_service}/{published_title}")
                    continue
                path.mkdir(parents=True, exist_ok=True)
                out_tasks.append(task)
            if not tasks or len(tasks) < per_take:
                break
        return out_tasks

    async def step2_run_task(self, _sem, _tasks):
        async def run_rpc_task(_path, _tasks, _id=None):
            # 事实上只支持单个任务单个文件，uris列表可以塞的是其他镜像源而不是兄弟任务的文件
            # todo[5]: rpc有个问题是当同一post发出不同类型的下载时（例如图片与MP4混杂），mortix会报错22，headers的问题
            async with _sem:
                gids = {}
                for task in _tasks:
                    _data = [[task["url"]], {"dir": str(_path)}]
                    resp = await self.rpc.sess.request(
                        "POST", RPC.url, headers={"Content-Type": "application/json"}, 
                        json=RPC.format_data(_data, _id=f"{_id}/{task['file_name']}"))
                    add_result = resp.json()
                    gid = add_result.get('result')
                    gids[gid] = task['file_name']
                
                errors = []
                completed = []
                while gids:
                    status_tasks = [self.rpc.check_gid_status(gid) for gid in gids.keys()]
                    results = await asyncio.gather(*status_tasks)
                    for gid, result in results:
                        if 'error' in result:
                            errors.append(f"GID {gids.pop(gid)} 查询失败：{result['error']}")
                            continue
                        status = result.get('result', {}).get('status')
                        if status == 'complete':
                            completed.append(gids.pop(gid))
                        elif status == 'error':
                            errors.append(f"任务 {gids.pop(gid)} 错误")
                    await asyncio.sleep(1.5)
                return {"t": _path.name, "complete": completed, "error": errors}

        tasks_future = []
        for tasks in _tasks:
            meta = tasks['meta']
            user_service = f"{meta['user_name']}_{meta['service']}"
            published_title = f"[{meta['published']}]{meta['title']}".strip()
            path = self.sv_path.joinpath(user_service, published_title)
            path.mkdir(parents=True, exist_ok=True)
            tasks_future.append(asyncio.ensure_future(run_rpc_task(path, tasks['tasks'], _id=published_title)))
        tasks_iter = asyncio.as_completed(tasks_future)
        fk_task_iter = tqdm.tqdm(tasks_iter, total=len(_tasks), ncols=80)
        for coroutine in fk_task_iter:
            try:
                res = await coroutine
                if res.get("complete"):
                    logger.info(f"[success {res.get('t')}] {res.get('complete')}")
                if res.get("error"):
                    logger.warning(f"[err {res.get('t')}] {res.get('error')}")
            except OverSizeErr as e:
                logger.warning(f"{e}")
            except Exception as e:
                logger.error(f"{e}")

    async def clean_residual_tasks(self):
        await self.redis.delete(self.redis_key)
        await self.redis.delete(f"{self.redis_key}_d")

    async def temp_copy_vals(self, restore=False):
        """redis"""
        a = self.redis_key
        b = f"{self.redis_key}_d"
        if restore:
            _ = a
            _d = b
            a = _d
            b = _
        elements = await self.redis.lrange(a, 0, -1)
        elements = list(map(json.loads, elements))
        if elements:
            await self.redis.rpush(b, *elements)
        if not restore:
            await self.redis.delete(self.redis_key)

    def delete(self, *args):
        """
        Notice! This way to delete file can let you never download again! As its blacklist system.
            Or, you can manually append blacklist to blacklist.json,
                format refers to Kemono().filter
        """
        blacklist = self.blacklist
        len_parts = len(self.sv_path.parts)
        for path in tqdm.tqdm(args):
            blacklist.append("/".join(path.parts[len_parts:]))
            if path.is_dir():
                shutil.rmtree(path)
            else:
                os.remove(path)
        self.blacklist_obj.save(blacklist)


class Process:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.k = Kemono(AioRClient())
        
    def create(self, **ckw):
        # 0. 清除遗留任务
        self.loop.run_until_complete(self.k.clean_residual_tasks())
        # 1. 获取/生成任务
        # 1.1 指定作品
        if "fav" in ckw:
            # 1.2.1 fav指定作者 ListArtistsInfo(['Gsusart2222', 'サインこす', ...])
            # 1.2.2 fav指定作者+平台 例如`keihh_fanbox`：ListArtistsInfo([['keihh', 'fanbox'], 'サインこす', ...])
            t = ListArtistsInfo(ckw.pop('fav'))
            # self.loop.run_until_complete(self.k.step1_tasks_create_by_favorites(t, **ckw))
            self.loop.run_until_complete(self.k.Creator(self.k, **ckw).by_favorites(t))
        elif "creatorid" in ckw:
            t = ckw.pop('creatorid')
            self.loop.run_until_complete(self.k.Creator(self.k, **ckw).by_creatorid(t))

        # 1.5 备份redis任务，restore=False时备份任务，restore=True时还原任务
        #       下面第二步无论成功与否都会消耗掉任务，不备份就要返回第一步生成任务了
        self.loop.run_until_complete(self.k.temp_copy_vals(restore=False))
    
    def run(self, **rkw):
        # 2 处理/执行任务
        self.loop.run_until_complete(self.k.temp_copy_vals(restore=True))

        tasks = self.loop.run_until_complete(self.k.step2_get_tasks())
        sem = asyncio.Semaphore(rkw.get('sem'))
        self.loop.run_until_complete(self.k.step2_run_task(sem, tasks))

    # self.k.delete(
    #     *self.k.sv_path.joinpath(r'MだSたろう_fanbox\[2024-06-16]フリーナっクス-アニメメーション版').glob('*動画*.zip')
    # )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=kemono_topic,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-p', '--process', type=str, nargs='?', default='main', help='optinal: create/run')
    parser.add_argument('-c', '--ckw', type=str, nargs='?', default=None, 
                        help='''创建任务传参，支持`fav`,`creatorid`,`postid`，就算只爬一个最外层也必须是列表，例子如下
    fav=[["keihh","fanbox"],"サインこす"]
    creatorid=[16015726,70050825]
使用fav时必须设置cookies''')
    parser.add_argument('-sd', '--start_date', type=str, nargs='?', default='2005-01-01', help='[筛选]发布时间大于此时间，default: 2005-01-01')
    parser.add_argument('-ed', '--end_date', type=str, nargs='?', default='2045-01-01', help='[筛选]发布时间小于此时间，default: 2045-01-01')
    parser.add_argument('--sem', type=int, default=3, help='[post]并发数')
    args = parser.parse_args()

    # 简易处理：当process为create时，ckw为必须参数
    if args.process != "run" and args.ckw is None:
        parser.error("当process非run时，必须提供--ckw参数")
    uri_ckw = json.loads("{"+re.sub(r'([a-zA-Z_]\w*)=', r'"\1":', args.ckw)+"}") if args.ckw else {}
    filter_ckw = {_: getattr(args, _)
        for _ in ("start_date", "end_date")
        if getattr(args, _)
    }
    ckw = {**uri_ckw, **filter_ckw}
    print(ckw)
    rkw = {
        "sem": args.sem
    }
    process = Process()
    match args.process:
        case "create":
            process.create(**ckw)
        case "run":
            process.run(**rkw)
        case _:
            process.create(**ckw)
            process.run(**rkw)
