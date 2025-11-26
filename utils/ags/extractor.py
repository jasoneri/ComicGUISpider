import typing as t
import re


def qq(text: str) -> t.List[str]:
    """
    提取 QQ 聊天记录格式的内容

    格式示例:```
    用户1: 11-07 13:46:54
    [餓了麼漢化組] (学園スターフェスティバル) [けしごむかばー (いっせー、時雨じう)] わたしにもあまえていい、よ (学園アイドルマスター) [中国翻訳]

    用户2: 11-08 12:07:07
    想要這樣的妹妹 [綠茶漢化組/無糖漢化組] [おみなえし] こんな妹がいてほしい
    ```
    """
    pattern = r'.*?\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\n(.*?)(?=\n+|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


# def weixin(text):
#     return [text]
