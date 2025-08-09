#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import pickle
import pathlib as p
import typing as t
from dataclasses import dataclass, asdict, field

import yaml
from loguru import logger as lg
from PyQt5.QtCore import QStandardPaths

from assets import res
from variables import DEFAULT_COMPLETER, COOKIES_SUPPORT
from deploy import curr_os

exc_p = ori_path = p.Path(__file__).parent.parent.parent
env = os.environ.copy()
uv_exc = "uv"

code_env = "git"
if ori_path.name == "site-packages":
    code_env = "uv"
try:
    if ori_path.parent.parent.parent.joinpath("_pystand_static.int").exists():
        code_env = "portable"   # REMARK[20250802] 需要区分绿色包的原因为绿色包的 uv 非系统级 uv,仅限 win 
        exc_p = ori_path.parent.parent.parent
        env['UV_TOOL_DIR'] = str(exc_p)
        env['UV_TOOL_BIN_DIR'] = str(exc_p.joinpath("bin"))
        uv_exc = str(exc_p.joinpath("runtime/uv.exe"))
except (OSError, ValueError):
    pass
conf_dir = p.Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)).joinpath("CGS")
conf_dir.mkdir(parents=True, exist_ok=True)
yaml.warnings({'YAMLLoadWarning': False})


def yaml_update(_f, dic):
    with open(_f, 'r+', encoding='utf-8') as fp:
        cfg = fp.read()
        ori_yml_config = yaml.load(cfg, Loader=yaml.FullLoader)
        ori_yml_config.update(dic)
        fp.seek(0)
        fp.truncate()
        yaml_data = yaml.dump(ori_yml_config, allow_unicode=True, sort_keys=False)
        fp.write(yaml_data)


class ConfCookie:
    """Cookie配置管理类，承担所有cookie的缓存、管理、展示和保存"""
    support_key = list(COOKIES_SUPPORT.keys())
    pickle_file = conf_dir.joinpath("cookies.pkl")

    def __init__(self, cookies_data=None):
        self.cache = cookies_data or self.empty_cache()  # 所有cookie类型的缓存
        self.current_type = self.support_key[0]
        self.load_from_pickle()

    def empty_cache(self):
        return {cookie_type: {} for cookie_type in self.support_key}

    def switch(self, cookie_type):
        """切换当前选中的cookie类型"""
        if cookie_type in self.support_key:
            self.current_type = cookie_type
            return True
        return False

    def show(self):
        """返回当前选中的cookie配置用于显示"""
        return self.cache.get(self.current_type, {})

    def update_current(self, cookie_data):
        if isinstance(cookie_data, dict):
            self.cache[self.current_type] = cookie_data
        else:
            self.cache[self.current_type] = {}
        self.save_to_pickle()

    def save_to_pickle(self):
        with open(self.pickle_file, 'wb') as f:
            pickle.dump(self.cache, f)

    def load_from_pickle(self):
        if self.pickle_file.exists():
            with open(self.pickle_file, 'rb') as f:
                self.cache = pickle.load(f)
            return True
        return False

    def get(self, name):
        return self.cache.get(name, {})

    def save(self):
        """返回用于保存到yaml的字典格式"""
        return {"cookies": self.cache.copy()}


class BaseConf:
    log_path = ori_path.joinpath('log')
    file = None

    def __init__(self, path=None, iname=None):
        self.init_conf()

    def cLog(self, name: str, level: str = None, **kw):
        if not hasattr(self.__class__, '_loggers'):
            self.__class__._loggers = {}
        if name in self.__class__._loggers:
            return self.__class__._loggers[name]
        self.log_path.mkdir(parents=True, exist_ok=True)
        log_file = self.log_path.joinpath(f'{name}.log')
        handlers = [h for h in lg._core.handlers.values()
                   if hasattr(h, 'file_path') and h.file_path == str(log_file)]
        if not handlers:
            lg.remove(handler_id=None)
            lg.add(log_file,
                filter=lambda record: name in record["extra"],
                format="{time:YYYY-MM-DD HH:mm:ss} | {level} | [{name}]: {message}",
                level=level or getattr(self, 'log_level', 'WARNING'), retention='5 days', encoding='utf-8')
        logger = lg.bind(**{name: True})
        self.__class__._loggers[name] = logger
        return logger

    def init_conf(self):  # 脱敏，储存路径和代理等用外部文件读
        ...

    @classmethod
    def duel_conf(cls, ori_conf_yml, iname):
        _i = f"_instance_{iname}" if iname else "_instance"
        return _i, conf_dir.joinpath(ori_conf_yml.name)

    def __new__(cls, *args, path: t.Optional[p.Path] = None, iname: str = None, **kwargs):
        _ori_conf_yml = (path or ori_path).joinpath("conf.yml" if not iname else f"conf_{iname}.yml")
        _instance, file = cls.duel_conf(_ori_conf_yml, iname)
        if not hasattr(cls, _instance):
            setattr(cls, _instance, object.__new__(cls))
            getattr(cls, _instance).file = file
        return getattr(cls, _instance)


@dataclass
class Conf(BaseConf):
    sv_path: t.Union[p.Path, str] = curr_os.default_sv_path
    proxies: list = field(default_factory=list)
    log_level: str = 'WARNING'
    pypi_source: int = 0
    addUuid: bool = False
    isDeduplicate: bool = False
    darkTheme: bool = False
    custom_map: dict = field(default_factory=dict)
    completer: dict = field(default_factory=dict)
    cookies = None
    clip_db: t.Union[p.Path, str] = curr_os.default_clip_db
    rv_script: t.Union[p.Path, str] = ''
    bg_path: t.Union[p.Path, str] = ''
    clip_read_num: str = '20'
    concurr_num: str = '16'
    clip_sql = curr_os.clip_sql

    def __init__(self, path=None, iname=None):
        self.init_conf()

    def init_conf(self):
        if not self.file.exists():
            with open(ori_path.joinpath('assets/conf_sample.yml'), 'r', encoding='utf-8') as fps:
                with open(self.file, 'w', encoding='utf-8') as fpw:
                    fpw.write(fps.read())
        with open(self.file, 'r', encoding='utf-8') as fp:
            cfg = fp.read()
        yml_config = yaml.load(cfg, Loader=yaml.FullLoader)
        for k, v in yml_config.items():
            if k == "sv_path" and v == r"D:\Comic":
                v = curr_os.default_sv_path
            # 跳过cookie相关字段，由ConfCookie处理
            if k == "pypi_source" and res.lang == "zh_CN":
                setattr(self, k, v or 1)
            elif k != "cookies":
                setattr(self, k, v or getattr(self, k, None))
        for _ in ("sv_path", "clip_db", "rv_script", "bg_path"):
            setattr(self, _, p.Path(getattr(self, _)))
        self.completer = getattr(self, 'completer', DEFAULT_COMPLETER)
        self.cookies = ConfCookie()

    def update(self, **kwargs):
        def path_like_handle(_p):
            return str(_p) if isinstance(_p, p.Path) else _p
        for k, v in kwargs.items():
            setattr(self, k, p.Path(v) if k in ("sv_path","rv_script","bg_path") else v)
        props = asdict(self)
        for _ in ("sv_path", "clip_db", "rv_script", "bg_path"):
            props[_] = path_like_handle(props[_])
        self.chain_rv()
        yaml_update(self.file, props)

    def chain_rv(self):
        # 储存目录更改单向联动 rV path值
        if self.rv_script and str(self.rv_script) != ".":
            rv_conf = self.rv_script.parent.joinpath(r"redViewer/backend/conf.yml")
            if rv_conf.exists():
                yaml_update(rv_conf,  {"path": str(self.sv_path)})

    @property
    def settings(self):
        return self.sv_path, self.log_path, self.proxies, self.log_level, self.custom_map, self.concurr_num


@dataclass
class ScriptConf(BaseConf):
    kemono: dict = field(default_factory=dict)
    nekohouse: dict = field(default_factory=dict)
    proxies: list = field(default_factory=list)
    redis: dict = field(default_factory=dict)

    def __init__(self, path=None, iname=None):
        self.init_conf()

    def init_conf(self):
        if not self.file.exists():
            with open(ori_path.joinpath('assets/conf_sample_script.yml'), 'r', encoding='utf-8') as fps:
                with open(self.file, 'w', encoding='utf-8') as fpw:
                    fpw.write(fps.read())
        with open(self.file, 'r', encoding='utf-8') as fp:
            cfg = fp.read()
        yml_config = yaml.load(cfg, Loader=yaml.FullLoader)
        for k, v in yml_config.items():
            setattr(self, k, v or getattr(self, k, None))

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        props = asdict(self)
        yaml_update(self.file, props)
