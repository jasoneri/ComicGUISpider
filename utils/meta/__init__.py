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
        """完成大部分通用正确的数据转换。"""
        super().__init__(info)
        if isinstance(info, Episode):
            episode = info
            book = episode.from_book
            self.title = episode.display_title
            self.series = self._extract_series_name(book.name)
            self.number = self._extract_number_from_episode_name(episode.name)
            self.pages = episode.pages or book.pages
        else:
            book = info
            self.title = book.display_title
            self.series = self._extract_series_name(book.name)
            self.number = None
            self.pages = book.pages
        self.web = book.preview_url
        self.artist = book.artist
        self.tags = book.tags or []
        self.source = book.source
        self.public_date = getattr(book, "public_date", None)

        self.year = None
        self.month = None
        self.day = None
        self._parse_date()

        self.language_iso = self._parse_language()
        self._extra_fields = {}

    def _extract_series_name(self, name: str) -> str:
        """未来可能用语言模型处理成"同系列多本"，当前直接返回原名。"""
        return name

    def _extract_number_from_episode_name(self, episode_name: str) -> Optional[str]:
        """从 Episode.name 中提取数字或中文数字作为 Number。"""
        match = re.search(r'\d+', episode_name)
        if match:
            return match.group(0)
        return None

    def _parse_date(self):
        """从 public_date 解析 Year/Month/Day。"""
        if not self.public_date or not isinstance(self.public_date, str):
            return
        sep = "-" if "-" in self.public_date else "/"
        parts = self.public_date.split(sep)
        if len(parts) >= 3 and all(p.strip().isdigit() for p in parts[:3]):
            self.year, self.month, self.day = parts[0], parts[1], parts[2]

    def _parse_language(self) -> str:
        """从 source/tags 推断语言代码。明确解析到时写，否则默认 zh。"""
        if self.source == "ehentai":
            if lang_tag := next((_ for _ in self.tags if _.startswith("language:")), None):
                lang = lang_tag.split(":", 1)[1]
                if lang == "chinese":
                    return "zh"
                elif lang == "english":
                    return "en"
                elif lang == "japanese":
                    return "ja"
        return "zh"

    def add(self, tag: str, value: Optional[str]) -> 'ComicInfo':
        """添加或覆盖特殊字段。"""
        self._extra_fields[tag] = value
        return self

    @property
    def content(self) -> str:
        """生成 ComicInfo.xml 字符串。"""
        xml_lines = []
        xml_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_lines.append(
            '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        )

        def add_field(tag: str, value: Optional[str]):
            if value is None:
                return
            if isinstance(value, str) and not value.strip():
                return
            v = (
                str(value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            xml_lines.append(f"  <{tag}>{v}</{tag}>")

        add_field("Title", self.title)
        add_field("Series", self.series)
        add_field("Number", self.number)
        add_field("Writer", self.artist)
        add_field("Publisher", self.source)
        # TODO[0](2025-12-08): jm发布日期，来源等等

        if self.year:
            add_field("Year", self.year)
        if self.month:
            add_field("Month", self.month)
        if self.day:
            add_field("Day", self.day)

        if self.tags:
            joined = ", ".join(map(str, self.tags))
            add_field("Genre", joined)
            add_field("Tags", joined)

        add_field("Web", self.web)
        add_field("PageCount", str(self.pages) if self.pages is not None else None)
        add_field("LanguageISO", self.language_iso)

        for tag, value in self._extra_fields.items():
            add_field(tag, value)

        xml_lines.append("</ComicInfo>")
        return "\n".join(xml_lines)

    def fin_callback(self, _p: p.Path):
        create_cbz(_p)


def create_cbz(src):
    cbz_filename = src.parent / f"{src.name}.cbz"
    with zipfile.ZipFile(cbz_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in sorted(src.iterdir()):
            if file.is_file():
                zipf.write(file, arcname=file.name)
    shutil.rmtree(src)


class Blank(MetaMixin):
    def sv_meta_in(self, path):
        return


class MetaRecorder:
    def __init__(self, _conf):
        self.meta_type = _conf.meta_type

    def toMetaInfo(self, info: Union[BookInfo, Episode]):
        match self.meta_type:
            case "ComicInfo.xml":
                return ComicInfo(info)
            case "-" | _:
                return Blank(info)
