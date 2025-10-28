import typing as t
from dataclasses import dataclass, asdict
from utils import md5, TasksObj
from .registry import Uuid


@dataclass
class InfoMinix:
    def __init__(self, **kw):
        for k, v in {**asdict(self), **kw}.items():
            setattr(self, k, v or getattr(self, k, None))


class BookInfo(InfoMinix):
    """每个网站应产生子类以覆盖source等常用属性
    episodes与pages互斥，有episodes则无pages
    """
    id: str = ""
    idx: int = None
    source: str = ""
    url: str = None		     # 程序内使用的最短路径获取下级信息链接
    preview_url: str = None  # 浏览器能打开的链接
    name: str = None
    artist: str = None
    public_date: str = None
    episodes: list = None
    pages: int = None
    btype: str = None        # booktype
    tags: list = []
    mark_tip = None

    @property
    def children_length(self):
        return len(self.episodes or []) or self.pages

    @property
    def uuid(self):
        return Uuid(self.source)

    @property
    def display_title(self):
        return self.name

    def get_id(self, info):
        self.id = self.uuid.get(info, only_id=True)
        return self


class Manga(BookInfo):
    episodes: list = []
    latest_sec: str = None
    render_keys: list = []
    
    @property
    def frame_result(self):
        return self.url, self.name, self.preview_url

    @property
    def say(self):
        render_vals = [getattr(self, k, '') for k in self.render_keys]
        return (str(self.idx), *render_vals, chr(12288))


class Ero(BookInfo):
    img_preview: str = None  

    @property
    def say(self):
        return str(self.idx), self.name, chr(12288)

    @property
    def frame_result(self):
        return self.url, self.name, self.preview_url

    @property
    def preview_args(self):
        return self.idx, self.img_preview, self.name, self.preview_url

    @property
    def uid(self):
        return f"{self.source}-{self.id}"

    @property
    def u_md5(self):
        return md5(self.uid)

    def id_and_md5(self):
        return self.uid, self.u_md5

    def clip_info(self):
        episodes = []
        for episode in (self.episodes or []):
            episodes.append({"ep": episode.name, "idx": episode.idx, "bid": episode.id})
        return self.idx, self.url, self.img_preview, self.name, \
                self.artist, self.pages, self.tags[:20] if self.tags else [], episodes

    def to_tasks_obj(self):
        assert self.pages is not None
        return TasksObj(
            self.u_md5, self.name, int(self.pages), self.preview_url, 'meaningless'
        )


class Episode(InfoMinix):
    from_book: t.Union[Ero, Manga] = None
    id: str = None
    idx: int = None
    url: str = None
    name: str = "meaningless"
    pages: t.Union[str, int] = None
    
    def id_and_md5(self):
        _uuid = f"{self.from_book.source}-{self.id}" if self.id else \
            f"{self.from_book.source}-{self.from_book.name}-{self.name}"
        uuid_md5 = md5(_uuid)
        return _uuid, uuid_md5

    @property
    def display_title(self):
        return f"{self.from_book.name} - {self.name}"

    def __str__(self):
        return str(self.name)

    def to_tasks_obj(self):
        _, u_md5 = self.id_and_md5()
        assert self.pages is not None
        return TasksObj(
            u_md5, self.from_book.name, int(self.pages), self.from_book.preview_url, self.name
        )
# ---

class KbBookInfo(Manga):
    source = "kaobei"


class MangabzBookInfo(Manga):
    source = "mangabz"

# ---

class JmBookInfo(Ero):
    source = "jm"
    likes: int = None


class WnacgBookInfo(Ero):
    source = "wnacg"


class EhBookInfo(Ero):
    source = "ehentai"

    @property
    def say(self):
        return str(self.idx), self.pages, self.name, chr(12288)
    
    def get_group_infos(self) -> dict:
        return {'title': self.name,'section': 'meaningless','uuid': self.uid,'uuid_md5': self.u_md5}


class HitomiBookInfo(Ero):
    source = "hitomi"
    lang: str = None
    pics: list = []
    say_fm = r' [ {} ], lang_{}, p_{}, ⌈ {} ⌋ '
    
    @property
    def say(self):
        return str(self.idx), self.lang, self.pages, self.name, chr(12288)
