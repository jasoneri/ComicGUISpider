import re
import pathlib as p
import shutil
import zipfile
from typing import Optional, Union
from utils.website.info import BookInfo, Episode


class MetaMixin:
    file = ""
    
    def __init__(self, info: Union[BookInfo, Episode]):
        self.info = info

    @property
    def content(self) -> str:
        return ""

    def sv_meta_in(self, path):
        _p = path.joinpath(self.file)
        if not _p.exists():
            with open(_p, 'w', encoding='utf-8') as f:
                f.write(self.content)

    def fin_callback(self, *args):
        ...


class ComicInfo(MetaMixin):
    file = "ComicInfo.xml"

    def __init__(self, info: Union[BookInfo, Episode]):
        super().__init__(info)
        self.is_ep = isinstance(info, Episode)
        if self.is_ep:
            episode = info
            book = episode.from_book
            self.title = episode.name
            self.series = self._extract_series_name(book.name)
            self.number = self._extract_number_from_episode_name(episode.name)
            self.pages = episode.pages or book.pages
        else:
            book = info
            self.title = book.display_title
            self.series = self._extract_series_name(book.name)
            self.number = None
            self.pages = book.pages
        self.preview_url = book.preview_url
        self.artist = book.artist
        self.tags = book.tags or []
        self.source = book.source
        self.btype = book.btype and book.btype.split(" ")
        self.public_date = getattr(book, "public_date", None)
        
        self.year = self.month = self.day = None
        self._parse_date()
        self.language_iso = self._parse_language()
        self._extra_fields = {}

    def _extract_series_name(self, name: str) -> str:
        """未来可能用语言模型处理成"同系列多本"，当前直接返回原名。"""
        return name

    def _extract_number_from_episode_name(self, episode_name: str) -> Optional[str]:
        match = re.search(r'\d+', episode_name)
        if match:
            return match.group(0)
        return None

    def _parse_date(self):
        if not self.public_date or not isinstance(self.public_date, str):
            return
        sep = "-" if "-" in self.public_date else "/"
        parts = self.public_date.split(sep)
        if len(parts) >= 3 and all(p.strip().isdigit() for p in parts[:3]):
            self.year, self.month, self.day = parts[0], parts[1], parts[2]

    def _parse_language(self) -> str:
        if self.source == "ehentai":
            if lang_tag := next((_ for _ in self.tags if _.startswith("language:")), None):
                match lang_tag.split(":", 1)[1]:
                    case "chinese":
                        return "zh"
                    case "english":
                        return "en"
                    case "japanese":
                        return "ja"
        return "zh"

    def add(self, tag: str, value: Optional[str]) -> 'ComicInfo':
        self._extra_fields[tag] = value
        return self

    @property
    def content(self) -> str:
        def escape(v):
            return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        fields = {
            "Title": self.title, "Writer": self.artist, "Publisher": self.source,
            "Series": self.series, "Number": self.number,
            "Year": self.year, "Month": self.month, "Day": self.day,
            "Tags": ", ".join(map(str, self.tags)) if self.tags else None,
            "Genre": ", ".join(map(str, self.btype)) if self.btype else None,
            "Web": self.preview_url,
            "PageCount": str(self.pages) if self.pages is not None else None,
            "LanguageISO": self.language_iso,
            **self._extra_fields
        }
        
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                 'xmlns:xsd="http://www.w3.org/2001/XMLSchema">']
        
        for tag, value in fields.items():
            if value is not None and (not isinstance(value, str) or value.strip()):
                lines.append(f"  <{tag}>{escape(value)}</{tag}>")
        
        lines.append("</ComicInfo>")
        return "\n".join(lines)

    def fin_callback(self, _p: p.Path):
        create_cbz(_p, self.is_ep)


def create_cbz(src, is_ep):
    cbz_filename = src.parent / f"{src.name}.cbz"
    with zipfile.ZipFile(cbz_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in sorted(src.iterdir()):
            if file.is_file():
                zipf.write(file, arcname=file.name)
    shutil.rmtree(src)
    if not is_ep:
        src.mkdir(exist_ok=True)
        shutil.move(cbz_filename, src)


class Blank(MetaMixin):
    def sv_meta_in(self, path):
        return


class MetaRecorder:
    def __init__(self, _conf):
        self.downloaded_handle = _conf.downloaded_handle

    def toMetaInfo(self, info: Union[BookInfo, Episode]):
        match self.downloaded_handle:
            case ".cbz":
                return ComicInfo(info)
            case "-" | _:
                return Blank(info)
