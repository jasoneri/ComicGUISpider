import re
from dataclasses import dataclass, asdict


@dataclass
class FontEle:
    color: str = "black"
    size: int = 3

    def __init__(self, string, **attr):
        self.string = string
        for k, v in attr.items():
            self.__setattr__(k, v or getattr(self, k, None))
        if "color" not in attr:
            self.__setattr__("class", "theme-text")

    def __str__(self):
        attr = re.findall(r"'(.*?)': (.*?)[,\}]",
                          str(asdict(self)))  # 看正则group(2),将dict的value为str时的引号带进去了,dict.items()不行
        return f"""<font {" ".join([f"{_[0]}={_[1]}" for _ in attr])}>{self.string}</font>"""


def font_color(string, **attr):
    return str(FontEle(string, **attr))
