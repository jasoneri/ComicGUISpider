import re


tag_regex = re.compile(r"汉化|漢化|粵化|DL版|修正|中国|翻訳|翻译|翻譯|中文|後編|前編|カラー化|個人|" +
                       r"無修|重修|重嵌|机翻|機翻|整合|黑字|Chinese|Japanese|\[Digital]|vol|\[\d+]")


def set_author_ahead(title: str) -> str:
    author_ = re.findall(r"\[.*?]", title)
    if bool(re.search(r"[(（]", "".join(author_))):  # 优先选标签内带括号
        author_ = list(filter(lambda x: bool(re.search(r"[(（]", x)), author_))
    else:  # 采用排除法筛选
        author_ = list(filter(lambda x: not bool(tag_regex.search(x)), author_))
    if len(author_) > 1:
        if len(set(author_)) == 1:  # 去除重复标签
            author_ = [author_[0]]
        else:
            # logger.warning(f"匹配待改善 {author_=}")
            return title
    elif not author_:
        return title
    author = author_[0]
    return (author + title.replace(author, '').replace("  ", " ")).strip()


domain_regex = re.compile("https?://(.*?)/")


def correct_domain(spider_domain, url) -> str:
    _domain = domain_regex.search(url).group(1)
    return url.replace(_domain, spider_domain)
