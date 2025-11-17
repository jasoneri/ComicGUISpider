import typing as t
import re


def qq(text: str) -> t.List[str]:
    """
    提取 QQ 聊天记录格式的内容

    格式示例:```
    用户1: 11-07 13:46:54
    (C106)[サルパッチョ(わいら)]トネリコと。(Fate/Grand Order)

    用户2: 11-08 12:07:07
    玉ぼん老师的玻璃の欠落
    ```
    """
    pattern = r'.*?\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\n(.*?)(?=\n\n|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


# def weixin(text):
#     return [text]
