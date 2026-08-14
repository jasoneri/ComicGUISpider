# -*- coding: utf-8 -*-
"""ANIMA prompt 文档模型：把 prompt 文本拆回 M3 段落、合并补充 tag、再渲染回文本。

存在理由是两个消费方必须对「同一段文本」得出同一结构：
  - GUI 的格式化按钮：from_text(...).to_text()
  - WD14 补充 tag 回显：from_text(...).merge_tags(...).to_text()
若各写一套，用户会看到「格式化后再提交」与「直接提交」产出不同的图。

刻意不含 Qt，以符合 GUI/utils 边界契约；仅依赖 anima_spec 与标准库。
"""
import re

if __package__:
    from . import anima_spec
else:
    import anima_spec

# 段序即 M3：[quality/meta/year/safety] [1girl/…] [character] [series] [artist] [general]
_LORA_RE = re.compile(r"<[^:>]+:[^:>]+:[^>]*>")


def split_prompt(text):
    """按逗号切分 prompt。转义括号内不含逗号，故简单切分即可。"""
    return [seg.strip() for seg in str(text or "").split(",") if seg.strip()]


def is_model_ref(token):
    """`<lora:name:weight>` 形态。本机无 LoRA 文件，写了不生效，应当被标错而非默默忽略。"""
    return bool(_LORA_RE.search(str(token or "")))


class PromptDoc:
    """M3 段落化的 prompt。

    `known` 映射可用时（GUI 持有 post 的分组信息），character/series 独立成段，
    `to_text()` 与 `build_anima_prompt()` 段序逐字一致。
    映射缺失时不猜——判不出的一律落 body，宁可少归类也不打乱用户已摆好的顺序。
    """

    SECTIONS = anima_spec.SECTION_ORDER
    __slots__ = SECTIONS

    def __init__(self, prefix=None, subject=None, character=None,
                 series=None, artist=None, body=None):
        self.prefix = list(prefix or [])
        self.subject = list(subject or [])
        self.character = list(character or [])
        self.series = list(series or [])
        self.artist = list(artist or [])
        self.body = list(body or [])

    def tokens(self):
        return [t for name in self.SECTIONS for t in getattr(self, name)]

    @classmethod
    def from_text(cls, text, known=None, normalize=True):
        """解析 prompt 文本。

        known: {规范化后的 tag: 段名}，段名取自 SECTIONS。
        缺省时只按谓词判定 prefix/subject/artist，其余留在 body。

        normalize=True  —— 规范化后入段，用于格式化与渲染。
        normalize=False —— 保留原文 token，用于违规检测。
            规范化本身就是「修复」：把 long_hair 变成 long hair 之后
            has_bare_underscore 便不再成立，违规会被自己抹掉。
            高亮器需要看见未修的原文，故必须走这条分支。
        分段与去重始终按规范化后的形态判定，两条分支的段落归属一致。
        """
        known = known or {}
        doc = cls()
        seen = set()
        for raw in split_prompt(text):
            key = raw if is_model_ref(raw) else anima_spec.normalize_tag(raw)
            if key in seen:
                continue
            seen.add(key)
            token = key if normalize else raw
            section = known.get(key)
            if section == "artist" or key.startswith("@"):
                if normalize and not token.startswith("@"):
                    token = f"@{token}"
                doc.artist.append(token)
            elif section in ("character", "series"):
                getattr(doc, section).append(token)
            elif section == "prefix" or anima_spec.is_prefix_tag(key):
                doc.prefix.append(token)
            elif section == "subject" or anima_spec.is_subject_count_tag(key):
                doc.subject.append(token)
            else:
                doc.body.append(token)
        return doc

    def merge_tags(self, tags):
        """把补充 tag（如 WD14 产出）并入 body，去重后返回新实例。"""
        merged = list(self.body)
        existing = set(self.tokens())
        for raw in tags or []:
            token = anima_spec.normalize_tag(raw)
            if not token or token in existing:
                continue
            existing.add(token)
            merged.append(token)
        return PromptDoc(self.prefix, self.subject, self.character,
                         self.series, self.artist, merged)

    def insert_tag(self, raw, section=None):
        """把一个 tag 插进指定段位，返回新实例（原实例不变）。

        与 merge_tags 的差别：那个只往 body 塞，供 WD14 这种「一律是 general」的来源用；
        收藏夹送来的多是 character / artist，落错段就违反 M3 段序，故必须能指定段位。

        section=None 时按 from_text 的同一套谓词判定，判不出落 body ——
        两处若各判各的，同一个 tag 点进来和打进去会去到不同段落。
        """
        # normalize_tag 不 strip（split_prompt 已在上游切干净），本组原语吃的是
        # chip 与用户输入，得自己收边，否则空白会被当成合法 tag 插进去。
        token = anima_spec.normalize_tag(raw).strip()
        if not token:
            return self
        if section == "artist" or token.startswith("@"):
            section = "artist"
            if not token.startswith("@"):
                token = f"@{token}"
        elif section not in ("character", "series", "prefix", "subject", "body"):
            if anima_spec.is_prefix_tag(token):
                section = "prefix"
            elif anima_spec.is_subject_count_tag(token):
                section = "subject"
            else:
                section = "body"
        # 去重按「裸形」比对：@nnn yryr 与 nnn yryr 是同一个作者，
        # 只因插入路径不同而多一个 @，不该在 prompt 里出现两次。
        if token.lstrip("@") in {t.lstrip("@") for t in self.tokens()}:
            return self
        parts = {name: list(getattr(self, name)) for name in self.SECTIONS}
        parts[section].append(token)
        return PromptDoc(**parts)

    def remove_tag(self, raw):
        """按裸形移除一个 tag，返回新实例。chip 再次点击需要能取消插入。"""
        target = anima_spec.normalize_tag(raw).strip().lstrip("@")
        if not target:
            return self
        parts = {
            name: [t for t in getattr(self, name) if t.lstrip("@") != target]
            for name in self.SECTIONS
        }
        return PromptDoc(**parts)

    def contains_tag(self, raw):
        """chip 选中态判定：与 insert_tag / remove_tag 共用同一「裸形」口径。"""
        target = anima_spec.normalize_tag(raw).strip().lstrip("@")
        return bool(target) and target in {t.lstrip("@") for t in self.tokens()}

    def to_text(self):
        """按 M3 段序渲染，与 build_anima_prompt() 一致。"""
        return ", ".join(self.tokens())

    def violations(self):
        """返回 [(token, 原因)]，供高亮器与提交前校验共用同一判定。"""
        found = []
        for token in self.tokens():
            if is_model_ref(token):
                found.append((token, "model-ref"))  # 本机无 LoRA 文件
            elif anima_spec.has_bare_underscore(token):
                found.append((token, "underscore"))
            elif anima_spec.needs_paren_escape(token):
                found.append((token, "paren"))
        for token in self.artist:
            if anima_spec.missing_at_prefix(token):
                found.append((token, "artist-at"))
        return found
