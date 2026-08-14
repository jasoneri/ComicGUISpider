# -*- coding: utf-8 -*-
"""ANIMA prompt 规范：官方 model card 的词表、分段与违规判定。

单一事实来源：https://huggingface.co/circlestone-labs/Anima/raw/main/README.md
本模块只放**数据与纯谓词**，不含改写逻辑（改写在 danbooru_anima.py）。

消费方有二，故必须保持 stdlib-only 且 Qt-free：
  - utils/script/image/anima/danbooru_anima.py  组装 prompt（自包含脚本，不可引入三方库）
  - GUI/script/danbooru/  语法高亮与预设 chip 面板
"""
import re

# --- M3 官方分段顺序 ---
# [quality/meta/year/safety] [1girl/1boy/1other] [character] [series] [artist] [general]
# 段名与 prompt_doc.PromptDoc.SECTIONS 必须一致，两处若分叉会导致渲染顺序不同。
SECTION_ORDER = ("prefix", "subject", "character", "series", "artist", "body")

# --- M5/M7 质量词 ---
QUALITY_TAGS = ("masterpiece", "best quality", "good quality",
                "normal quality", "low quality", "worst quality")
SCORE_TAGS = tuple(f"score_{n}" for n in range(9, 0, -1))

# --- 安全词，及 danbooru rating 映射（danbooru 用 g/s/q/e，旧数据用全称）---
SAFETY_TAGS = ("safe", "sensitive", "nsfw", "explicit")
RATING_TO_SAFETY = {
    "g": "safe", "general": "safe", "s": "sensitive", "sensitive": "sensitive",
    "q": "nsfw", "questionable": "nsfw", "e": "explicit", "explicit": "explicit",
}

# --- 时期词 / meta 词 ---
PERIOD_TAGS = ("newest", "recent", "mid", "early", "old")
META_TAGS = ("highres", "absurdres", "anime screenshot", "jpeg artifacts", "official art")

# --- 官方推荐基线（M5/M6）。aesthetic 需另行剔除 score_*（M7）---
OFFICIAL_POSITIVE_PREFIX = "masterpiece, best quality, score_7, safe"
OFFICIAL_NEGATIVE = ("worst quality, low quality, score_1, score_2, score_3, "
                     "artist name, blurry, jpeg artifacts, chromatic aberration")

# --- danbooru tag 分类 type 码 → 高亮配色 ---
# 沿用 danbooru 站点与 a1111-sd-webui-tagcomplete 的既有惯例，不自创配色。
# type 码与 CGS 的 TAG_GROUP_ORDER 一一对应。
# 用具名键而非 (暗,亮) 元组：元组顺序只能靠注释表达，调用方极易取反索引。
TAG_CATEGORY_COLORS = {
    0: {"dark": "lightblue", "light": "dodgerblue"},    # General
    1: {"dark": "indianred", "light": "firebrick"},     # Artist
    3: {"dark": "violet", "light": "darkorchid"},       # Copyright / series
    4: {"dark": "lightgreen", "light": "darkgreen"},    # Character
    5: {"dark": "orange", "light": "darkorange"},       # Meta
}
GROUP_TO_CATEGORY = {"General": 0, "Artist": 1, "Copyright": 3, "Character": 4, "Meta": 5}


def category_color(category, is_dark):
    """按当前主题取分类配色。调用方不必记忆键序。"""
    return TAG_CATEGORY_COLORS[category]["dark" if is_dark else "light"]

_SCORE_RE = re.compile(r"^score_\d$")
_SUBJECT_RE = re.compile(r"^\d+(girls?|boys?|others?)$")
_YEAR_RE = re.compile(r"^year \d{4}$")
_BARE_PAREN_RE = re.compile(r"(?<!\\)[()]")


def is_score_tag(tag):
    """score_N 是 M2 中唯一保留下划线的标签族。"""
    return bool(_SCORE_RE.match(str(tag or "").strip()))


def is_subject_count_tag(tag):
    """1girl / 2boys / 1other —— M3 中拥有独立槽位，需从 General 段析出前置。"""
    return bool(_SUBJECT_RE.match(str(tag or "").strip().lower()))


def is_prefix_tag(tag):
    """归属 M3 首槽 [quality/meta/year/safety] 的标签。"""
    text = str(tag or "").strip().lower()
    return (text in QUALITY_TAGS or text in SAFETY_TAGS or text in PERIOD_TAGS
            or text in META_TAGS or is_score_tag(text) or bool(_YEAR_RE.match(text)))


def safety_tag_for_rating(rating):
    """danbooru post.rating → ANIMA 安全标签；未知评级返回 None 而非猜测。"""
    return RATING_TO_SAFETY.get(str(rating or "").strip().lower())


def normalize_tag(tag):
    """danbooru 原始 tag → ANIMA 合法 tag。

    唯一实现：prompt 组装(danbooru_anima)与 GUI 的格式化按钮必须逐字一致，
    否则「格式化后提交」与「直接提交」会产出两种不同的图。
      M2 小写 + 下划线转空格（score_N 例外）
      D6 圆括号转义，否则 danbooru 的消歧后缀会被当作权重组解析

    必须幂等：格式化按钮可被反复点击，重复转义会把 `\\(` 变成 `\\\\(` 并弄坏 prompt。
    """
    text = str(tag or "").lower()
    if not is_score_tag(text):
        text = text.replace("_", " ")
    return _BARE_PAREN_RE.sub(lambda m: "\\" + m.group(0), text)


# --- 违规判定（供 Stage B 语法高亮当场标记，而非提交时静默改写）---

def has_bare_underscore(tag):
    """M2 违规：非 score 标签仍带下划线。"""
    text = str(tag or "")
    return "_" in text and not is_score_tag(text.strip())


def needs_paren_escape(tag):
    """D6 违规：存在未转义圆括号，会被 ComfyUI 当作权重组解析。"""
    return bool(_BARE_PAREN_RE.search(str(tag or "")))


def missing_at_prefix(tag):
    """M4 违规：artist 段标签缺 `@` 前缀，缺失时模型响应极弱。"""
    return not str(tag or "").strip().startswith("@")


# --- Stage D 桥接：把本模块的规范渲染成可嵌入 system prompt 的英文规则 ---
# 面向 LLM 故用英文，与 capabilities/tag_translate/prompts.py 的既有惯例一致。
_SECTION_BRIEF = {
    "prefix": "quality / period / safety words",
    "subject": "subject count words such as 1girl, 2boys, 1other",
    "character": "character names",
    "series": "series (copyright) names",
    "artist": "artist names, each prefixed with @",
    "body": "all remaining descriptive tags",
}


def format_rules_text():
    """渲染 M2/M3/M4 的硬约束，供 NL 合并的 system prompt 直接嵌入。

    段序与词表**由本模块常量插值**，提示词里不另抄一份。抄一份必然漂移，
    而漂移的表现极难归因：LLM 按旧规则产出，`PromptDoc.violations()` 按新规则判违规，
    用户看到的是「AI 生成的 prompt 满屏警告」，却查不出是谁的规则变了。
    """
    order = "\n".join(
        f"  {index}. {_SECTION_BRIEF[name]}"
        for index, name in enumerate(SECTION_ORDER, 1)
    )
    return (
        "Section order (mandatory, quality words come FIRST, never last):\n"
        f"{order}\n"
        f"- Quality words must come from: {', '.join(QUALITY_TAGS)}\n"
        f"- Score words must come from: {', '.join(SCORE_TAGS)}"
        " (the only tag family that keeps underscores)\n"
        f"- Safety words must come from: {', '.join(SAFETY_TAGS)}\n"
        f"- Period words must come from: {', '.join(PERIOD_TAGS)}, or `year YYYY`\n"
        "- Every other tag is lowercase with spaces instead of underscores\n"
        "- Round brackets must be escaped as \\( and \\)\n"
        "- Artist tags must start with @"
    )
