from __future__ import annotations

import re
import typing as t
from urllib.parse import quote_plus

import httpx
from loguru import logger

from .models import (
    ANILIST_GRAPHQL,
    ANILIST_QUERY,
    HTML_ENGINES,
    MOEGIRL_API,
    USER_AGENT,
    VALID_ENGINES,
    SearchEngineName,
    SearchHit,
    clean_text,
    has_han,
    has_kana,
    looks_like_challenge,
    mostly_kana,
    parse_baidu_html,
    parse_bing_html,
    parse_ddg_html,
    parse_google_html,
    parse_opensearch_payload,
    query_tokens,
    wiki_record_to_hits,
)
from .session import EvidenceSession


class SerpTransport:
    """Owns proxy config and short-lived httpx clients."""

    def __init__(self, proxies: object = None):
        self.proxies = proxies

    @staticmethod
    def first_proxy_url(proxies: object) -> str | None:
        values = proxies if isinstance(proxies, (list, tuple)) else []
        for raw in values:
            text = str(raw or "").strip()
            if not text:
                continue
            if "://" in text:
                return text
            return f"http://{text}"
        return None

    def client_kwargs(
        self,
        proxies: object | None = None,
        *,
        timeout: float = 20.0,
        accept: str = "text/html",
    ) -> dict[str, t.Any]:
        proxy_source = self.proxies if proxies is None else proxies
        kwargs: dict[str, t.Any] = {
            "timeout": timeout,
            "follow_redirects": True,
            "headers": {
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
            },
        }
        proxy_url = self.first_proxy_url(proxy_source)
        if proxy_url:
            kwargs["proxy"] = proxy_url
        return kwargs

    def json_get(
        self,
        url: str,
        *,
        params: dict | None = None,
        timeout: float = 20.0,
        try_without_proxy_first: bool = False,
        proxies: object | None = None,
    ) -> t.Any:
        attempts: list[object | None] = []
        if try_without_proxy_first:
            attempts.append(None)
        attempts.append(self.proxies if proxies is None else proxies)
        last_error: Exception | None = None
        for proxy_choice in attempts:
            try:
                kwargs = self.client_kwargs(
                    proxy_choice,
                    timeout=timeout,
                    accept="application/json,text/javascript,*/*",
                )
                with httpx.Client(**kwargs) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    content_type = (response.headers.get("content-type") or "").lower()
                    text = response.text
                    if "html" in content_type or text.lstrip().startswith("<"):
                        if looks_like_challenge(text):
                            raise RuntimeError(f"challenge page from {url}")
                        raise RuntimeError(f"non-json response from {url}")
                    return response.json()
            except Exception as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        raise RuntimeError(f"json get failed: {url}")

    def get_text(self, url: str, *, timeout: float = 12.0, proxies: object | None = None) -> tuple[int, str]:
        kwargs = self.client_kwargs(proxies, timeout=timeout)
        with httpx.Client(**kwargs) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.status_code, response.text

    def post_json(
        self,
        url: str,
        *,
        payload: dict,
        timeout: float = 20.0,
        proxies: object | None = None,
    ) -> t.Any:
        kwargs = self.client_kwargs(proxies, timeout=timeout, accept="application/json")
        with httpx.Client(**kwargs) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()


class DanbooruSource:
    """Source Adapter: writes core wiki evidence into session."""

    def fill_core(self, session: EvidenceSession):
        parts = session.parts
        titles: list[tuple[str, str]] = [(parts.origin, "danbooru")]
        if parts.parent_tag and parts.parent_tag != parts.origin:
            titles.append((parts.parent_tag, "danbooru_parent"))
        if parts.series_tag:
            titles.append((parts.series_tag, "danbooru_series"))

        per_page_budget = max(4, min(8, int(session.danbooru_budget or 5) + 2))
        staged: list[SearchHit] = []
        seen_titles: set[str] = set()
        for title, source in titles:
            key = title.replace(" ", "_").lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            record = self.fetch_wiki(title)
            if not record:
                logger.info(f"[TagTranslate][serp] danbooru wiki empty title={title!r}")
                continue
            other_names = record.get("other_names") or []
            logger.info(
                f"[TagTranslate][serp] danbooru wiki hit title={title!r} "
                f"other_names={len(other_names) if isinstance(other_names, list) else 0} "
                f"body_len={len(str(record.get('body') or ''))}"
            )
            is_series = source.endswith("series") or source == "danbooru_series"
            staged.extend(
                wiki_record_to_hits(
                    record,
                    source=source,
                    max_results=2 if is_series else per_page_budget,
                    expand_other_names=not is_series,
                    max_individual_names=0 if is_series else 4,
                    include_links=not is_series,
                )
            )
            character_hits = [
                hit for hit in staged if not str(hit.source or "").startswith("danbooru_series")
            ]
            if len(character_hits) >= max(3, int(session.danbooru_budget or 5)):
                break

        session.accept_core(
            *staged,
            max_results=max(session.danbooru_budget, per_page_budget + 2),
        )

    def fetch_wiki(self, title: str) -> dict | None:
        tag_title = str(title or "").strip()
        if not tag_title:
            return None
        try:
            from utils.script.image.danbooru.client import DanbooruClient

            with DanbooruClient(timeout=25.0) as client:
                return client.get_wiki_page(tag_title, timeout=25.0)
        except Exception as exc:
            logger.debug(f"[TagTranslate][serp] danbooru wiki miss title={tag_title!r}: {exc}")
            return None

    def fetch_series_aliases(self, session: EvidenceSession) -> list[SearchHit]:
        if not session.parts.series_tag:
            return []
        record = self.fetch_wiki(session.parts.series_tag)
        if not record:
            return []
        return wiki_record_to_hits(
            record,
            source="danbooru_series",
            max_results=2,
            expand_other_names=True,
            max_individual_names=6,
            include_links=False,
        )


class AnilistSource:
    """Source Adapter: native-name bridge into session core."""

    def __init__(self, transport: SerpTransport):
        self.transport = transport

    def fill_bridge(self, session: EvidenceSession):
        parts = session.parts
        series_text = (parts.series or "").replace("_", " ").replace("-", " ").replace(":", " ").strip()
        series_tokens = {
            token
            for token in re.split(r"[^0-9a-z\u4e00-\u9fff\u3040-\u30ff]+", series_text.lower())
            if len(token) >= 3
        }
        base_words = parts.base_name.split() if parts.base_name else []
        base_title = " ".join(word.capitalize() for word in base_words)
        reversed_title = ""
        if len(base_words) == 2 and all(word.isalpha() and len(word) <= 12 for word in base_words):
            reversed_title = " ".join(word.capitalize() for word in reversed(base_words))

        searches: list[str] = []
        for term in (
            base_title,
            parts.base_name,
            reversed_title,
            f"{base_title} {series_text}".strip() if series_text else "",
            f"{parts.base_name} {series_text}".strip() if series_text else "",
            parts.cleaned,
        ):
            text = clean_text(term)
            if text and text not in searches:
                searches.append(text)
        if not searches:
            return

        max_results = min(3, max(2, session.limit // 2 + 1))
        for use_proxy in (False, True):
            client_proxies = self.transport.proxies if use_proxy else None
            try:
                for search_term in searches[:5]:
                    payload = self.transport.post_json(
                        ANILIST_GRAPHQL,
                        payload={"query": ANILIST_QUERY, "variables": {"search": search_term}},
                        proxies=client_proxies,
                    )
                    characters = (
                        (((payload or {}).get("data") or {}).get("Page") or {}).get("characters") or []
                    )
                    ranked: list[tuple[int, dict]] = []
                    for character in characters:
                        if not isinstance(character, dict):
                            continue
                        name = character.get("name") or {}
                        full = clean_text(name.get("full")).lower()
                        native = clean_text(name.get("native"))
                        media_blob_parts = []
                        for node in ((character.get("media") or {}).get("nodes") or []):
                            title = (node or {}).get("title") or {}
                            for key in ("romaji", "native", "english"):
                                media_blob_parts.append(clean_text(title.get(key)).lower())
                        media_blob = " ".join(media_blob_parts)
                        score = 0
                        if any(token in full for token in query_tokens(parts.base_name)):
                            score += 2
                        if series_tokens and any(token in media_blob for token in series_tokens):
                            score += 5
                        if series_text and series_text.lower() in media_blob:
                            score += 3
                        if native:
                            score += 1
                        ranked.append((score, character))
                    ranked.sort(key=lambda item: item[0], reverse=True)
                    if not ranked:
                        continue
                    best_score, character = ranked[0]
                    if series_tokens and best_score < 4:
                        continue
                    name = character.get("name") or {}
                    full = clean_text(name.get("full"))
                    native = clean_text(name.get("native"))
                    alternatives = [
                        clean_text(item)
                        for item in (name.get("alternative") or [])
                        if clean_text(item)
                    ]
                    media_titles = []
                    for node in ((character.get("media") or {}).get("nodes") or []):
                        title = (node or {}).get("title") or {}
                        for key in ("native", "romaji", "english"):
                            value = clean_text(title.get(key))
                            if value and value not in media_titles:
                                media_titles.append(value)
                    body_bits = []
                    if native:
                        body_bits.append(f"native={native}")
                    if alternatives:
                        body_bits.append("alt=" + " / ".join(alternatives[:6]))
                    if media_titles:
                        body_bits.append("media=" + " / ".join(media_titles[:4]))
                    if parts.costume:
                        body_bits.append(f"costume_token={parts.costume}")
                    if parts.series:
                        body_bits.append(f"series_token={parts.series}")
                    desc = clean_text(character.get("description"))
                    if desc:
                        body_bits.append(desc[:220])
                    href = clean_text(character.get("siteUrl"))
                    display = native or full or search_term
                    hits = [
                        SearchHit(
                            title=display,
                            href=href,
                            body=" | ".join(body_bits),
                            source="anilist",
                        )
                    ]
                    if full and full != display:
                        hits.append(
                            SearchHit(
                                title=full,
                                href=href,
                                body=f"anilist full name; native={native}",
                                source="anilist:full",
                            )
                        )
                    logger.info(
                        f"[TagTranslate][serp] anilist hits search={search_term!r} "
                        f"score={best_score} full={full!r} native={native!r}"
                    )
                    session.accept_core(*hits, max_results=max(len(session.core_hits) + max_results, max_results))
                    return
            except Exception as exc:
                logger.debug(f"[TagTranslate][serp] anilist failed proxy={use_proxy}: {exc}")
                continue


class MoegirlSource:
    """Source Adapter: enrichment writes ranked moegirl hits into session."""

    def __init__(self, transport: SerpTransport):
        self.transport = transport

    def fill_enrichment(self, session: EvidenceSession, *, max_results: int):
        parts = session.parts
        seeds = session.seed_names
        raw_hits: list[SearchHit] = []
        character_hits: list[SearchHit] = []
        seen_titles: set[str] = set()
        for query in session.moegirl_queries():
            try:
                payload = self.transport.json_get(
                    MOEGIRL_API,
                    params={
                        "action": "opensearch",
                        "search": query,
                        "limit": str(max(max_results, 8)),
                        "namespace": "0",
                        "redirects": "return",
                        "format": "json",
                    },
                )
            except Exception as exc:
                logger.warning(f"[TagTranslate][serp] moegirl opensearch failed q={query!r}: {exc}")
                continue
            batch = parse_opensearch_payload(payload, source="moegirl", max_results=max_results * 3)
            for hit in batch:
                key = hit.title.lower()
                if key in seen_titles:
                    continue
                body = hit.body or self._extract(hit.title)
                enriched = SearchHit(title=hit.title, href=hit.href, body=body, source="moegirl")
                blob = f"{enriched.title} {enriched.body}".lower()
                base_ok = any(token in blob for token in query_tokens(parts.base_name))
                series_ok = any(
                    token in blob for token in query_tokens((parts.series or "").replace("_", " "))
                )
                seed_ok = any(
                    clean_text(name).lower() in blob
                    or any(token in blob for token in query_tokens(name) if len(token) >= 2)
                    for name in seeds
                )
                if not (base_ok or seed_ok or (series_ok and has_han(hit.title))):
                    continue
                seen_titles.add(key)
                raw_hits.append(enriched)
                if session.moegirl_is_character_level(enriched):
                    character_hits.append(enriched)
            if character_hits:
                kept = session.accept_ranked_enrichment(
                    character_hits,
                    max_results=max_results,
                    min_score=3 if any(mostly_kana(seed) for seed in seeds) else 4,
                )
                if kept:
                    logger.info(
                        f"[TagTranslate][serp] moegirl hits={kept} "
                        f"raw={len(raw_hits)} char={len(character_hits)} q={query!r}"
                    )
                    return
        pool = character_hits or raw_hits
        if pool:
            session.accept_ranked_enrichment(pool, max_results=max_results, min_score=3)

    def _extract(self, title: str) -> str:
        try:
            payload = self.transport.json_get(
                MOEGIRL_API,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "redirects": "1",
                    "format": "json",
                    "titles": title,
                },
                timeout=15.0,
            )
        except Exception as exc:
            logger.debug(f"[TagTranslate][serp] moegirl extract failed title={title!r}: {exc}")
            return ""
        pages = (((payload or {}).get("query") or {}).get("pages") or {})
        if not isinstance(pages, dict):
            return ""
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            extract = clean_text(page.get("extract"))
            if extract:
                return extract[:400]
        return ""


class HtmlSerpSource:
    """Source Adapter: baidu/bing/google (+ DDG fallback) into session enrichment."""

    def __init__(self, transport: SerpTransport, danbooru: DanbooruSource):
        self.transport = transport
        self.danbooru = danbooru

    def fill_enrichment(self, session: EvidenceSession):
        parts = session.parts
        engine_name = session.engine
        final_limit = session.final_limit
        origin = session.origin

        character_seeds = session.character_seeds()
        series_disambiguators = session.series_disambiguators()

        if not series_disambiguators and parts.series_tag:
            series_hits = self.danbooru.fetch_series_aliases(session)
            series_disambiguators = session.series_disambiguators(series_hits)
            if series_disambiguators and series_hits:
                session.accept_core(
                    *series_hits[:2],
                    max_results=max(len(session.core_hits) + 2, session.danbooru_budget + 2),
                )

        parent_display_hits: list[SearchHit] = []
        if parts.costume and parts.parent_tag:
            try:
                from utils.config.qc import danbooru_cfg as _danbooru_cfg

                parent_key = _danbooru_cfg.canonicalize_term(parts.parent_tag)
                parent_display = _danbooru_cfg.get_translate_map().get(parent_key)
                parent_display = _danbooru_cfg.canonicalize_term(str(parent_display or ""))
            except Exception:
                parent_display = ""
            if parent_display and (
                (has_han(parent_display) if session.language == "zh" else True)
                or has_kana(parent_display)
            ):
                costume_token = (parts.costume or "").replace("_", " ").strip()
                parent_display_hits.append(
                    SearchHit(
                        title=parent_display,
                        href="",
                        body=(
                            f"localized base display for parent tag {parts.parent_tag}: "
                            f"{parent_display}. origin is costume variant costume={costume_token}; "
                            f"compose display as {parent_display}({costume_token}) when no fuller "
                            f"costume form appears elsewhere in evidence."
                        ),
                        source="translate_map:parent",
                    )
                )
                if parent_display not in character_seeds:
                    character_seeds.insert(0, parent_display)

        seed_pack = [*character_seeds, *series_disambiguators]
        serp_queries = session.serp_queries(seed_pack, site_domains=session.site_domains())
        kana_seeds = [name for name in character_seeds if has_kana(name)]
        collected: list[SearchHit] = []
        empty_streak = 0
        query_budget = 4 if engine_name == "google" else 6

        for serp_query in serp_queries[:query_budget]:
            serp_hits = self._fetch_html(engine_name, serp_query, max_results=max(3, min(6, final_limit)))
            if not serp_hits:
                empty_streak += 1
                if empty_streak >= 2:
                    logger.warning(
                        f"[TagTranslate][serp] {engine_name} abort after "
                        f"{empty_streak} empty queries tag={origin!r}"
                    )
                    break
                continue
            if not session.looks_relevant(serp_query, serp_hits):
                logger.warning(f"[TagTranslate][serp] {engine_name} irrelevant hits q={serp_query!r}")
                continue
            empty_streak = 0
            collected.extend(serp_hits)
            kept = session.accept_ranked_enrichment(
                collected,
                max_results=max(3, min(5, final_limit // 2 + 1)),
                min_score=3 if kana_seeds else 4,
                seed_override=seed_pack,
            )
            if kept and session.candidates_have_target_script(session.enrichment_hits):
                logger.info(
                    f"[TagTranslate][serp] {engine_name} kept={kept} "
                    f"raw={len(collected)} target_script=yes q={serp_query!r}"
                )
                break

        if parent_display_hits:
            session.prepend_enrichment(
                *parent_display_hits,
                max_results=max(3, min(6, final_limit // 2 + 2)),
            )
        if not session.enrichment_hits and collected:
            session.accept_ranked_enrichment(
                collected,
                max_results=max(2, min(4, final_limit // 2)),
                min_score=3,
            )

    def _fetch_html(self, engine: str, query: str, *, max_results: int) -> list[SearchHit]:
        term = clean_text(query)
        if not term:
            return []
        encoded = quote_plus(term)
        candidates: list[tuple[str, t.Callable[[str], list[SearchHit]]]] = []
        if engine == "baidu":
            candidates = [
                (f"https://www.baidu.com/s?wd={encoded}", lambda text: parse_baidu_html(text, max_results=max_results)),
            ]
        elif engine == "bing":
            candidates = [
                (f"https://www.bing.com/search?q={encoded}", lambda text: parse_bing_html(text, max_results=max_results)),
                (f"https://cn.bing.com/search?q={encoded}", lambda text: parse_bing_html(text, max_results=max_results)),
            ]
        elif engine == "google":
            candidates = [
                (
                    f"https://www.google.com/search?q={encoded}&hl=zh-CN",
                    lambda text: parse_google_html(text, max_results=max_results),
                ),
            ]
        else:
            return []

        candidates.append(
            (
                f"https://html.duckduckgo.com/html/?q={encoded}",
                lambda text: parse_ddg_html(text, max_results=max_results),
            )
        )

        serp_timeout = 8.0 if engine == "google" else 12.0
        for url, parser in candidates:
            try:
                status_code, page_text = self.transport.get_text(url, timeout=serp_timeout)
                if looks_like_challenge(page_text):
                    logger.warning(
                        f"[TagTranslate][serp] {engine} challenge/empty page "
                        f"status={status_code} len={len(page_text)} url={url}"
                    )
                    continue
                hits = parser(page_text)
                if not hits:
                    continue
                if engine in HTML_ENGINES:
                    tagged: list[SearchHit] = []
                    for hit in hits:
                        source = hit.source or engine
                        if source == "ddg":
                            source = f"{engine}:ddg"
                        elif not str(source).startswith(engine):
                            source = f"{engine}:{source}" if source else engine
                        tagged.append(
                            SearchHit(
                                title=hit.title,
                                href=hit.href,
                                body=hit.body,
                                source=source,
                            )
                        )
                    hits = tagged
                logger.info(f"[TagTranslate][serp] {engine} hits={len(hits)} q={term!r}")
                return hits
            except Exception as exc:
                logger.warning(f"[TagTranslate][serp] {engine} failed q={term!r}: {exc}")
        return []


class EvidenceGatherer:
    """
    Session Facade: owns transport + source adapters.

    Each search() opens EvidenceSession (context/accumulator), adapters Tell
    the session, then session.assemble() returns the final hit list.
    """

    def __init__(
        self,
        *,
        proxies: object = None,
        language: str = "zh",
        engine: SearchEngineName | str = "danbooru",
    ):
        self.transport = SerpTransport(proxies)
        self.language = language if language in {"zh", "ja"} else "zh"
        engine_name = str(engine or "danbooru").strip().lower()
        self.engine: SearchEngineName | str = engine_name if engine_name in VALID_ENGINES else "danbooru"
        self.danbooru = DanbooruSource()
        self.anilist = AnilistSource(self.transport)
        self.moegirl = MoegirlSource(self.transport)
        self.html_serp = HtmlSerpSource(self.transport, self.danbooru)

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        engine: SearchEngineName | str | None = None,
        language: str | None = None,
    ) -> list[SearchHit]:
        session = EvidenceSession.open(
            query,
            engine=engine if engine is not None else self.engine,
            language=language if language is not None else self.language,
            max_results=max_results,
        )
        if session is None:
            return []

        self.danbooru.fill_core(session)
        if session.needs_native_bridge() or session.engine in {"danbooru", "moegirl"}:
            self.anilist.fill_bridge(session)

        if session.engine == "moegirl":
            self.moegirl.fill_enrichment(
                session,
                max_results=max(3, min(5, session.final_limit // 2 + 1)),
            )
        elif session.engine in HTML_ENGINES:
            self.html_serp.fill_enrichment(session)
        elif session.engine == "danbooru" and not session.seed_names:
            self.moegirl.fill_enrichment(session, max_results=max(2, min(4, session.limit)))

        return session.assemble()


def search_engine(
    engine: SearchEngineName | str,
    query: str,
    *,
    proxies: object = None,
    max_results: int = 5,
    language: str = "zh",
) -> list[SearchHit]:
    """One-shot entry. Prefer holding EvidenceGatherer across a tag batch."""
    return EvidenceGatherer(proxies=proxies, language=language, engine=engine).search(
        query,
        max_results=max_results,
    )
