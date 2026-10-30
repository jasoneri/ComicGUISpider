import io
import re
from dataclasses import dataclass, asdict

from rich.ansi import AnsiDecoder
from rich.console import Console


@dataclass
class FontEle:
    cls :str = ""
    color: str = ""
    size: int = 3

    def __init__(self, string, **attr):
        self.string = string
        for k, v in attr.items():
            self.__setattr__(k, v or getattr(self, k, None))

    def __str__(self):
        _attr = asdict(self)
        for k in ("cls", "color"):
            if not getattr(self, k):
                del _attr[k]
            if k == "cls" and getattr(self, k):
                _attr["class"] = getattr(self, k)
                del _attr[k]
        attr = re.findall(r"'(.*?)': (.*?)[,\}]",
                          str(_attr))  # 看正则group(2),将dict的value为str时的引号带进去了,dict.items()不行
        return f"""<font {" ".join([f"{_[0]}={_[1]}" for _ in attr])}>{self.string}</font>"""


def font_color(string, **attr):
    return str(FontEle(string, **attr))


_ansi_decoder = AnsiDecoder()
_ansi_html_console = Console(
    file=io.StringIO(), record=True, width=4096, legacy_windows=False, no_color=False
)


def ansi_to_html(line: str) -> str:
    """终端 ANSI 色彩行转内联样式 HTML，供 scriptWin 的 TextBrowser 渲染，转义符不再以乱码形式残留"""
    _ansi_html_console.print(_ansi_decoder.decode_line(line), end="", crop=False)
    return _ansi_html_console.export_html(inline_styles=True, code_format="{code}", clear=True)
