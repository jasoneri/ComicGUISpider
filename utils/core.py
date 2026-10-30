import re
import time
import typing as t
from dataclasses import asdict, dataclass

from variables import ASSETS_FALLBACK, GITHUB_PRESET_BASE, IMGBED_ASSET_OBJECTS

ILLEGAL_FILENAME_RE = re.compile(r'[|:<>?*"\\/]')


def sanitize_filename(name: str, repl: str = '_') -> str:
    """清理文件名中的非法字符"""
    return ILLEGAL_FILENAME_RE.sub(repl, name).strip() or "unnamed"


def sanitize_for_path(name: str) -> str:
    return ILLEGAL_FILENAME_RE.sub('-', name)


@dataclass(frozen=True)
class ManagedAsset:
    """托管 preset 下载源 (GitHub preset 主源，ImgBed assets 兜底)。"""

    logical_name: str

    @property
    def github_url(self) -> str:
        return f"{GITHUB_PRESET_BASE.rstrip('/')}/{self.logical_name.lstrip('/')}"

    @property
    def fallback_url(self) -> t.Optional[str]:
        object_name = IMGBED_ASSET_OBJECTS.get(self.logical_name.strip())
        if not object_name:
            return None
        return f"{ASSETS_FALLBACK.rstrip('/')}/{object_name.lstrip('/')}"

    @property
    def urls(self) -> t.Tuple[str, ...]:
        """Ordered download URLs: GitHub preset first, ImgBed assets fallback when mapped."""
        urls = [self.github_url]
        fallback_url = self.fallback_url
        if fallback_url:
            urls.append(fallback_url)
        return tuple(urls)

    @property
    def sources(self) -> t.Tuple[t.Dict[str, str], ...]:
        """Ordered (id, url) sources for bootstrap-style failover loops."""
        sources = [{"id": "github", "url": self.github_url}]
        fallback_url = self.fallback_url
        if fallback_url:
            sources.append({"id": "imgbed", "url": fallback_url})
        return tuple(sources)


class State:
    """gui与后端需要共用的一个状态变量时，使用此类；
    由于处于不同进程，需要创建一个对应的Queues做通讯"""
    buffer: dict = None

    def sv_cache(self):
        """take snapshot when sth occur
        run before sent
        """
        try:
            self.buffer = asdict(self)
        except AttributeError:
            ...

    def __eq__(self, other):
        return asdict(self) == other.buffer

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if key != 'buffer':
            self.sv_cache()


class Queues:
    @staticmethod
    def send(queue, state: State, wait=False):
        try:
            if wait:
                while not queue.empty():
                    time.sleep(0.01)
            else:
                if not queue.empty():
                    queue.get()
        except Exception as e:
            raise e
        queue.put(state)

    @staticmethod
    def recv(queue) -> t.Optional[State]:
        try:
            if queue.empty():
                return None
            state = queue.get()
            queue.put_nowait(state)
        except Exception as e:
            raise e
        return state

    @staticmethod
    def clear(queue):
        try:
            while True:
                queue.get_nowait()
        except Exception:
            pass


class TasksObj:
    def __init__(self, taskid: str, title: str, tasks_count: int, title_url: str = None,
                 episode_name: str = None, cover_url: str = None, meta_info=None, source: str = None):
        self.taskid = taskid
        self.title = title
        self.tasks_count = tasks_count
        self.title_url = title_url
        self.episode_name = episode_name
        self.cover_url = cover_url
        self.source = source
        self.cover_bytes = None
        self.downloaded = []
        self.meta_info = meta_info
        self.local_path = None
        self.share_payload = None

    @property
    def display_title(self) -> str:
        return f"{self.title} - {self.episode_name}" if self.episode_name else self.title


class TaskObj:
    success: bool = True

    def __init__(self, taskid: str, page: str, url: str = None):
        self.taskid = taskid
        self.page = page
        self.url = url
