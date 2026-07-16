from __future__ import annotations

from dataclasses import dataclass
import re
import typing as t
from urllib.parse import parse_qs, quote, unquote, urlparse

from lxml import html as lxml_html

SearchEngineName = t.Literal["danbooru", "moegirl", "baidu", "bing", "google"]
VALID_ENGINES = frozenset({"danbooru", "moegirl", "baidu", "bing", "google"})
HTML_ENGINES = frozenset({"baidu", "bing", "google"})

DANBOORU_BASE = "https://danbooru.donmai.us"
MOEGIRL_API = "https://zh.moegirl.org.cn/api.php"
ANILIST_GRAPHQL = "https://graphql.anilist.co"
ANILIST_QUERY = (
    "query ($search: String) {"
    "  Page(perPage: 8) {"
    "    characters(search: $search) {"
    "      name { full native alternative }"
    "      siteUrl"
    "      description(asHtml: false)"
    "      media(perPage: 4) { nodes { title { romaji native english } } }"
    "    }"
    "  }"
    "}"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 ComicGUISpider-TagTranslate/1.0"
)
CHALLENGE_MARKERS = (
    "captcha",
    "botdetect",
    "unusual traffic",
    "verify you are a human",
    "安全验证",
    "人机验证",
    "access denied",
    "cf-browser-verification",
    "just a moment",
    "enablejs",
)
WIKI_HREF_MARKERS = ("moegirl", "biligame", "fandom.com", "wikipedia", "wiki", "huiji")
NOISE_MARKERS = (
    "vocaloid",
    "niconico",
    "片头曲",
    "片尾曲",
    "主题曲",
    "原创歌曲",
    "专辑",
    "single",
    "op/ed",
    "歌词",
    "同人",
    "r-18",
    "壁纸",
    "users入り",
    "download",
    "captcha",
)


@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    href: str
    body: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class TagQueryParts:
    """Mechanical tag structure only — never holds static translation tables."""

    origin: str
    base_name: str
    costume: str | None
    series: str | None
    cleaned: str
    parent_tag: str | None
    series_tag: str | None


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize_search_query(query: str) -> str:
    term = re.sub(r"\s+", " ", str(query or "").strip())
    if not term:
        return ""
    term = term.replace("_", " ")
    term = re.sub(r"[()]+", " ", term)
    return re.sub(r"\s+", " ", term).strip()


def parse_tag_query(origin: str) -> TagQueryParts:
    """Split Danbooru-style parentheses only. No SERIES_ZH / COSTUME_ZH."""
    raw = re.sub(r"\s+", " ", str(origin or "").strip())
    cleaned = normalize_search_query(raw)
    groups = re.findall(r"\(([^()]+)\)", raw)
    base = re.sub(r"\([^()]*\)", " ", raw)
    base_name = normalize_search_query(base) or cleaned
    costume: str | None = None
    series: str | None = None
    if len(groups) >= 2:
        costume = groups[0].strip()
        series = groups[-1].strip()
    elif len(groups) == 1:
        series = groups[0].strip()

    parent_tag: str | None = None
    series_tag: str | None = None
    if series:
        series_tag = series.strip().lower().replace(" ", "_")
    if costume and series:
        parent_tag = re.sub(r"\([^()]+\)\s*\([^()]+\)$", f"({series})", raw).strip()
        if parent_tag == raw:
            parent_tag = f"{base_name.replace(' ', '_')}_({series})"
    elif series and base_name:
        parent_tag = None

    return TagQueryParts(
        origin=raw,
        base_name=base_name,
        costume=costume.lower().replace("-", "_") if costume else None,
        series=series.lower().replace("-", "_") if series else None,
        cleaned=cleaned,
        parent_tag=parent_tag,
        series_tag=series_tag,
    )


def query_tokens(query: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff\u3040-\u30ff]+", query.lower())
        if len(token) >= 2
    }


def has_han(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def has_kana(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", text or ""))


def mostly_kana(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned or not has_kana(cleaned):
        return False
    han_count = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
    kana_count = len(re.findall(r"[\u3040-\u30ff]", cleaned))
    return kana_count >= 2 and han_count == 0


def looks_like_challenge(page_text: str) -> bool:
    lowered = (page_text or "").lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


def decode_ddg_href(href: str) -> str:
    text = clean_text(href)
    if not text:
        return ""
    if "uddg=" in text:
        parsed = urlparse(text if "://" in text else f"https://duckduckgo.com{text}")
        values = parse_qs(parsed.query).get("uddg") or []
        if values:
            return unquote(values[0])
    return text


def wiki_body_snippet(body: str, *, limit: int = 900) -> str:
    text = str(body or "")
    text = re.sub(r"!post\s*#\d+[^\n]*", " ", text, flags=re.I)
    text = re.sub(r"!asset\s*#\d+[^\n]*", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def wiki_record_to_hits(
    record: dict,
    *,
    source: str,
    max_results: int,
    expand_other_names: bool = True,
    max_individual_names: int = 6,
    include_links: bool = True,
) -> list[SearchHit]:
    """Pure factory: Danbooru wiki JSON → SearchHit list (no session state)."""
    title = clean_text(record.get("title"))
    body = wiki_body_snippet(record.get("body") or "")
    other_names = record.get("other_names") or []
    if not isinstance(other_names, list):
        other_names = []
    names = [clean_text(name) for name in other_names if clean_text(name)]
    href = f"{DANBOORU_BASE}/wiki_pages/{quote(title.replace(' ', '_'), safe='')}" if title else ""
    hits: list[SearchHit] = []

    if names:
        name_limit = 12 if source.endswith("series") or source == "danbooru_series" else 20
        hits.append(
            SearchHit(
                title=title or "danbooru_wiki",
                href=href,
                body="other_names: " + " | ".join(names[:name_limit]),
                source=f"{source}:other_names",
            )
        )
        if expand_other_names:
            expanded = 0
            for name in names:
                if not re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", name):
                    continue
                hits.append(
                    SearchHit(
                        title=name,
                        href=href,
                        body=f"danbooru other_name for {title}",
                        source=f"{source}:other_name",
                    )
                )
                expanded += 1
                if expanded >= max(0, int(max_individual_names or 0)):
                    break
                if len(hits) >= max_results:
                    break

    if body and len(hits) < max_results:
        full_name_bits = re.findall(
            r"(?:full name|本名|全名|正式名称)[^\n.。]{0,40}",
            body,
            flags=re.I,
        )
        body_prefix = ""
        if full_name_bits:
            body_prefix = "name_line: " + " | ".join(clean_text(bit) for bit in full_name_bits[:3]) + " | "
        hits.append(
            SearchHit(
                title=f"{title} (wiki body)" if title else "wiki body",
                href=href,
                body=body_prefix + body,
                source=f"{source}:body",
            )
        )

    if include_links:
        for match in re.finditer(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", str(record.get("body") or "")):
            link_target = clean_text(match.group(1))
            link_label = clean_text(match.group(2) or match.group(1))
            if not link_target:
                continue
            if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", link_label) or "(" in link_target:
                hits.append(
                    SearchHit(
                        title=link_label,
                        href=f"{DANBOORU_BASE}/wiki_pages/{quote(link_target.replace(' ', '_'), safe='')}",
                        body=f"wiki link target={link_target}",
                        source=f"{source}:link",
                    )
                )
            if len(hits) >= max_results * 2:
                break

    return _dedupe_hit_list(hits, max_results=max_results)


def parse_opensearch_payload(payload: t.Any, *, source: str, max_results: int) -> list[SearchHit]:
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    titles = payload[1] if isinstance(payload[1], list) else []
    descriptions = payload[2] if len(payload) > 2 and isinstance(payload[2], list) else []
    hrefs = payload[3] if len(payload) > 3 and isinstance(payload[3], list) else []
    hits: list[SearchHit] = []
    for index, title_raw in enumerate(titles):
        title = clean_text(title_raw)
        if not title:
            continue
        href = clean_text(hrefs[index] if index < len(hrefs) else "")
        body = clean_text(descriptions[index] if index < len(descriptions) else "")
        hits.append(SearchHit(title=title, href=href, body=body, source=source))
        if len(hits) >= max_results:
            break
    return hits


def parse_baidu_html(page_text: str, *, max_results: int) -> list[SearchHit]:
    tree = lxml_html.fromstring(page_text)
    hits: list[SearchHit] = []
    for node in tree.cssselect("div.result, div.c-container"):
        link = node.cssselect("h3 a, a")
        if not link:
            continue
        anchor = link[0]
        title = clean_text(anchor.text_content())
        href = clean_text(anchor.get("href"))
        body_nodes = node.cssselect(".c-abstract, .content-right_8Zs40, span")
        body = clean_text(body_nodes[0].text_content()) if body_nodes else ""
        if not title:
            continue
        hits.append(SearchHit(title=title, href=href, body=body, source="baidu"))
        if len(hits) >= max_results:
            break
    return hits


def parse_bing_html(page_text: str, *, max_results: int) -> list[SearchHit]:
    tree = lxml_html.fromstring(page_text)
    hits: list[SearchHit] = []
    for node in tree.cssselect("li.b_algo"):
        link = node.cssselect("h2 a")
        if not link:
            continue
        title = clean_text(link[0].text_content())
        href = clean_text(link[0].get("href"))
        body_nodes = node.cssselect(".b_caption p, p")
        body = clean_text(body_nodes[0].text_content()) if body_nodes else ""
        if not title:
            continue
        hits.append(SearchHit(title=title, href=href, body=body, source="bing"))
        if len(hits) >= max_results:
            break
    return hits


def parse_google_html(page_text: str, *, max_results: int) -> list[SearchHit]:
    tree = lxml_html.fromstring(page_text)
    hits: list[SearchHit] = []
    for node in tree.cssselect("div.g, div.tF2Cxc"):
        link = node.cssselect("a")
        title_nodes = node.cssselect("h3")
        if not link or not title_nodes:
            continue
        title = clean_text(title_nodes[0].text_content())
        href = clean_text(link[0].get("href"))
        body_nodes = node.cssselect("div.VwiC3b, span.aCOpRe")
        body = clean_text(body_nodes[0].text_content()) if body_nodes else ""
        if not title:
            continue
        hits.append(SearchHit(title=title, href=href, body=body, source="google"))
        if len(hits) >= max_results:
            break
    return hits


def parse_ddg_html(page_text: str, *, max_results: int) -> list[SearchHit]:
    tree = lxml_html.fromstring(page_text)
    hits: list[SearchHit] = []
    for node in tree.cssselect("div.result, div.results_links"):
        link = node.cssselect("a.result__a, a")
        if not link:
            continue
        title = clean_text(link[0].text_content())
        href = decode_ddg_href(link[0].get("href") or "")
        body_nodes = node.cssselect("a.result__snippet, div.result__snippet")
        body = clean_text(body_nodes[0].text_content()) if body_nodes else ""
        if not title:
            continue
        hits.append(SearchHit(title=title, href=href, body=body, source="ddg"))
        if len(hits) >= max_results:
            break
    return hits


def _dedupe_hit_list(hits: list[SearchHit], *, max_results: int) -> list[SearchHit]:
    seen: set[str] = set()
    out: list[SearchHit] = []
    for hit in hits:
        key = f"{hit.source}|{hit.title}|{hit.href}|{hit.body[:80]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
        if len(out) >= max_results:
            break
    return out
