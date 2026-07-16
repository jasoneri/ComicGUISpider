from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib.parse import urlparse

from loguru import logger

from .models import (
    HTML_ENGINES,
    NOISE_MARKERS,
    VALID_ENGINES,
    WIKI_HREF_MARKERS,
    SearchEngineName,
    SearchHit,
    TagQueryParts,
    clean_text,
    has_han,
    has_kana,
    mostly_kana,
    parse_tag_query,
    query_tokens,
)


@dataclass(slots=True)
class EvidenceSession:
    """
    Encapsulated Context + Accumulator for one tag query.

    Owns core/enrichment hits and seed names. Source adapters Tell this object
    (accept_core / accept_enrichment / accept_ranked_enrichment); they never
    thread list[SearchHit] through free-function chains.
    """

    origin: str
    parts: TagQueryParts
    language: str
    engine: str
    limit: int
    final_limit: int
    danbooru_budget: int
    core_hits: list[SearchHit] = field(default_factory=list)
    enrichment_hits: list[SearchHit] = field(default_factory=list)
    seed_names: list[str] = field(default_factory=list)
    _seen_keys: set[str] = field(default_factory=set, repr=False)

    @classmethod
    def open(
        cls,
        query: str,
        *,
        engine: SearchEngineName | str,
        language: str,
        max_results: int,
    ) -> EvidenceSession | None:
        origin = str(query or "").strip()
        if not origin:
            return None
        target_language = language if language in {"zh", "ja"} else "zh"
        engine_name = str(engine or "danbooru").strip().lower()
        if engine_name not in VALID_ENGINES:
            engine_name = "danbooru"
        limit = max(1, int(max_results or 5))
        final_limit = max(limit, 10) if engine_name != "danbooru" else max(limit, 8)
        danbooru_budget = max(4, final_limit - (4 if engine_name != "danbooru" else 0))
        return cls(
            origin=origin,
            parts=parse_tag_query(origin),
            language=target_language,
            engine=engine_name,
            limit=limit,
            final_limit=final_limit,
            danbooru_budget=danbooru_budget,
        )

    # -- Tell API (adapters write here) -------------------------------------

    def accept_core(self, *hits: SearchHit, max_results: int | None = None):
        """Accumulate core evidence; rebuild seeds from owned core list."""
        budget = max_results if max_results is not None else max(self.danbooru_budget, 12)
        for hit in hits:
            self._append_unique(self.core_hits, hit, budget)
        self.rebuild_seeds()

    def accept_enrichment(self, *hits: SearchHit, max_results: int | None = None):
        budget = max_results if max_results is not None else max(2, self.final_limit // 2 + 2)
        for hit in hits:
            self._append_unique(self.enrichment_hits, hit, budget)

    def accept_ranked_enrichment(
        self,
        candidates: list[SearchHit],
        *,
        max_results: int,
        min_score: int = 4,
        seed_override: list[str] | None = None,
        replace: bool = True,
    ) -> int:
        """Score candidates with owned parts/seeds/language; keep ranked subset."""
        ranked = self.rank(candidates, max_results=max_results, min_score=min_score, seed_override=seed_override)
        if replace:
            self._forget_bucket(self.enrichment_hits)
            self.enrichment_hits = []
        for hit in ranked:
            self._append_unique(self.enrichment_hits, hit, max_results)
        return len(ranked)

    def prepend_enrichment(self, *hits: SearchHit, max_results: int):
        merged = [*hits, *self.enrichment_hits]
        self._forget_bucket(self.enrichment_hits)
        self.enrichment_hits = []
        for hit in merged:
            self._append_unique(self.enrichment_hits, hit, max_results)

    # -- Owned analytics (no free-function hit threading) -------------------

    def rebuild_seeds(self):
        raw_names = self._localized_names_from_owned_core()
        self.seed_names = self._prefer_seed_order(raw_names)

    def needs_native_bridge(self) -> bool:
        if not self.seed_names:
            return True
        return not re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", " ".join(self.seed_names))

    def score(self, hit: SearchHit, *, seed_override: list[str] | None = None) -> int:
        seeds = seed_override if seed_override is not None else self.seed_names
        title = clean_text(hit.title)
        body = clean_text(hit.body)
        blob = f"{title} {body}".lower()
        score = 0
        for token in query_tokens(self.parts.base_name):
            if token in blob:
                score += 4
        for token in query_tokens((self.parts.series or "").replace("_", " ")):
            if token in blob:
                score += 3
        for token in query_tokens(self.parts.cleaned or self.parts.origin):
            if len(token) >= 4 and token in blob:
                score += 1
        for seed in seeds:
            seed_text = clean_text(seed).lower()
            if not seed_text:
                continue
            if seed_text in blob:
                score += 6
            else:
                for token in query_tokens(seed):
                    if len(token) >= 2 and token in blob:
                        score += 2
        if self.language == "zh" and has_han(title):
            score += 3
        elif self.language == "zh" and mostly_kana(title) and not has_han(body):
            score -= 2
        if self.language == "ja" and (has_kana(title) or has_han(title)):
            score += 2
        href = (hit.href or "").lower()
        if any(marker in href for marker in WIKI_HREF_MARKERS):
            score += 3
        if "danbooru" in href or "anilist" in href:
            score += 1
        if any(marker in blob for marker in NOISE_MARKERS) and score < 10:
            score -= 6
        character_seed_hit = any(
            clean_text(seed).lower() in blob
            for seed in seeds
            if has_kana(seed) or re.search(r"[a-z]", seed.lower())
        )
        series_seed_hit = any(
            clean_text(seed).lower() in blob
            for seed in seeds
            if has_han(seed) and not has_kana(seed) and not re.search(r"[A-Za-z]", seed)
        )
        target_script_title = (
            (has_han(title) and not mostly_kana(title))
            if self.language == "zh"
            else (has_kana(title) or has_han(title))
        )
        if character_seed_hit and series_seed_hit and target_script_title:
            score += 6
        elif character_seed_hit and target_script_title:
            score += 3
        return score

    def rank(
        self,
        candidates: list[SearchHit],
        *,
        max_results: int,
        min_score: int = 4,
        seed_override: list[str] | None = None,
    ) -> list[SearchHit]:
        ranked: list[tuple[int, SearchHit]] = []
        for hit in candidates:
            score = self.score(hit, seed_override=seed_override)
            if score < min_score:
                logger.debug(
                    f"[TagTranslate][serp] drop weak enrichment "
                    f"score={score} title={hit.title!r} source={hit.source}"
                )
                continue
            ranked.append((score, hit))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in ranked[: max(0, max_results)]]

    def looks_relevant(self, query: str, candidates: list[SearchHit]) -> bool:
        tokens = query_tokens(query)
        if not tokens or not candidates:
            return bool(candidates)
        for hit in candidates:
            blob = f"{hit.title} {hit.body}".lower()
            if any(token in blob for token in tokens):
                return True
        return False

    def enrichment_has_target_script(self) -> bool:
        for hit in self.enrichment_hits:
            blob = f"{hit.title} {hit.body}"
            if self.language == "zh" and has_han(blob) and not mostly_kana(hit.title):
                return True
            if self.language == "ja" and (has_kana(blob) or has_han(blob)):
                return True
        return False

    def candidates_have_target_script(self, candidates: list[SearchHit]) -> bool:
        for hit in candidates:
            blob = f"{hit.title} {hit.body}"
            if self.language == "zh" and has_han(blob) and not mostly_kana(hit.title):
                return True
            if self.language == "ja" and (has_kana(blob) or has_han(blob)):
                return True
        return False

    def character_seeds(self) -> list[str]:
        out: list[str] = []

        def add(name: str | None):
            text = clean_text(name)
            if not text:
                return
            bare = re.sub(r"[（(][^）)]+[）)]", "", text).strip() or text
            for item in (bare, text):
                if item and item not in out:
                    out.append(item)

        for hit in self.core_hits:
            source = str(hit.source or "")
            if source.startswith("danbooru_series"):
                continue
            is_alias = (
                source.endswith(":other_name")
                or source.endswith(":other_names")
                or source.startswith("anilist")
            )
            if not is_alias:
                continue
            if source.endswith("other_names") and hit.body.startswith("other_names:"):
                for piece in hit.body.split(":", 1)[1].split("|"):
                    add(piece)
            else:
                add(hit.title)
                if "native=" in hit.body:
                    for match in re.finditer(r"native=([^|]+)", hit.body):
                        add(match.group(1))
        if self.parts.base_name:
            add(self.parts.base_name)
        if self.parts.costume and self.parts.base_name:
            add(self.parts.base_name)
            add(f"{self.parts.base_name} {self.parts.costume.replace('_', ' ')}")
        return out

    def series_disambiguators(self, extra_hits: list[SearchHit] | None = None) -> list[str]:
        out: list[str] = []
        for hit in [*self.core_hits, *(extra_hits or [])]:
            source = str(hit.source or "")
            if not source.startswith("danbooru_series"):
                continue
            if "other_names" in source and hit.body.startswith("other_names:"):
                for piece in hit.body.split(":", 1)[1].split("|"):
                    name = clean_text(piece)
                    if not name or name in out:
                        continue
                    if re.search(r"[A-Za-z]", name) and not has_han(name):
                        continue
                    if len(name) > 24:
                        continue
                    out.append(name)
        out.sort(key=lambda name: (0 if (has_han(name) and not has_kana(name)) else 1, len(name)))
        return out

    def site_domains(self, *, limit: int = 3) -> list[str]:
        domains: list[str] = []
        for hit in self.core_hits:
            href = clean_text(hit.href or "")
            if not href or not href.startswith("http"):
                continue
            try:
                host = (urlparse(href).hostname or "").lower()
            except Exception:
                host = ""
            if not host or host in domains:
                continue
            if host.endswith("donmai.us") or "anilist" in host:
                continue
            domains.append(host)
            if len(domains) >= limit:
                break
        return domains

    def serp_queries(self, seed_pack: list[str], *, site_domains: list[str] | None = None) -> list[str]:
        variants: list[str] = []

        def add(term: str | None):
            text = clean_text(term)
            if text and text not in variants:
                variants.append(text)

        character_seeds = [name for name in seed_pack if clean_text(name)]
        series_aliases = [
            name
            for name in seed_pack
            if has_han(name) and not mostly_kana(name) and len(clean_text(name)) <= 16
        ]
        kana_seeds = [name for name in character_seeds if has_kana(name)]
        series_text = (self.parts.series or "").replace("_", " ").strip()
        base_name = self.parts.base_name or self.parts.cleaned
        costume_text = (self.parts.costume or "").replace("_", " ").strip()

        primary: list[str] = []
        for seed in (kana_seeds or character_seeds):
            bare = re.sub(r"[（(][^）)]+[）)]", "", seed).strip() or seed
            if bare not in primary:
                primary.append(bare)
            if len(primary) >= 3:
                break

        han_series = [
            name
            for name in series_aliases
            if has_han(name) and not has_kana(name) and not re.search(r"[A-Za-z]", name)
        ][:3]
        locale_ops = ("中文名", "中文") if self.language == "zh" else ("日本語名", "読み")

        for bare in primary:
            for series_name in han_series:
                add(f"{bare} {series_name}")
                for op in locale_ops:
                    add(f"{bare} {series_name} {op}")
                if costume_text:
                    add(f"{bare} {costume_text} {series_name}")
            if series_text and not han_series:
                add(f"{bare} {series_text}")
                for op in locale_ops:
                    add(f"{bare} {series_text} {op}")
            if costume_text:
                add(f"{bare} {costume_text}")
            for op in locale_ops:
                add(f"{bare} {op}")
            add(bare)

        if base_name:
            for series_name in series_aliases[:2]:
                add(f"{base_name} {series_name}")
            if series_text:
                add(f"{base_name} {series_text}")
                for op in locale_ops:
                    add(f"{base_name} {series_text} {op}")
            elif self.language == "zh":
                add(f"{base_name} 角色 中文名")

        if self.parts.costume and base_name:
            add(f"{base_name} {costume_text} {series_text}".strip())

        focus = (kana_seeds[0] if kana_seeds else base_name) or ""
        if focus and self.engine in HTML_ENGINES:
            for domain in (site_domains or [])[:3]:
                add(f"{focus} site:{domain}")
                if series_text:
                    add(f"{focus} {series_text} site:{domain}")

        add(self.parts.cleaned)
        return variants

    def moegirl_queries(self) -> list[str]:
        variants: list[str] = []

        def add(term: str | None):
            text = clean_text(term)
            if text and text not in variants:
                variants.append(text)

        seed_list = [clean_text(name) for name in self.seed_names if clean_text(name)]
        kana_seeds = [name for name in seed_list if mostly_kana(name) or has_kana(name)]
        han_seeds = [name for name in seed_list if has_han(name)]
        series_text = (self.parts.series or "").replace("_", " ").strip()

        for kana in kana_seeds[:4]:
            bare = re.sub(r"[（(][^）)]+[）)]", "", kana).strip() or kana
            for series_zh in han_seeds[:4]:
                add(f"{bare} {series_zh}")
                add(f"{bare}（{series_zh}）")
            if series_text:
                add(f"{bare} {series_text}")
            add(bare)
            add(kana)

        for name in han_seeds:
            add(name)
            bare = re.sub(r"[（(][^）)]+[）)]", "", name).strip()
            add(bare)

        for name in seed_list:
            add(name)
            bare = re.sub(r"[（(][^）)]+[）)]", "", name).strip()
            add(bare)

        add(self.parts.cleaned)
        add(self.parts.base_name)
        if self.parts.series:
            add(f"{self.parts.base_name} {series_text}")
            for series_zh in han_seeds[:3]:
                add(f"{self.parts.base_name} {series_zh}")
        if self.parts.costume:
            add(f"{self.parts.base_name} {self.parts.costume.replace('_', ' ')}")
        add(self.parts.origin)
        return variants

    def moegirl_is_character_level(self, hit: SearchHit) -> bool:
        blob = f"{hit.title} {hit.body}".lower()
        if any(token in blob for token in query_tokens(self.parts.base_name)):
            return True
        for seed in self.seed_names:
            seed_text = clean_text(seed)
            if not seed_text:
                continue
            if has_han(seed_text) and not has_kana(seed_text) and not re.search(r"[a-z]", seed_text.lower()):
                if len(seed_text) <= 8 and seed_text in hit.title and seed_text != hit.title:
                    return True
                continue
            if seed_text.lower() in blob:
                return True
            if any(token in blob for token in query_tokens(seed) if len(token) >= 2):
                return True
        return False

    def assemble(self) -> list[SearchHit]:
        reserve = 0 if self.engine == "danbooru" else min(4, max(2, self.final_limit // 3))
        result = self._merge_owned(reserve_enrichment=reserve)
        if not result:
            logger.warning(
                f"[TagTranslate][serp] no evidence tag={self.origin!r} engine={self.engine}"
            )
            return result
        sources = sorted({hit.source for hit in result if hit.source})
        enrichment_sources = sorted(
            {
                hit.source
                for hit in result
                if hit.source
                and not str(hit.source).startswith("danbooru")
                and not str(hit.source).startswith("anilist")
            }
        )
        logger.info(
            f"[TagTranslate][serp] evidence assembled tag={self.origin!r} "
            f"engine={self.engine} hits={len(result)} sources={sources} "
            f"enrichment={enrichment_sources or []}"
        )
        return result

    # -- internals ----------------------------------------------------------

    def _hit_key(self, hit: SearchHit) -> str:
        return f"{hit.source}|{hit.title}|{hit.href}|{hit.body[:80]}"

    def _forget_bucket(self, bucket: list[SearchHit]):
        for hit in bucket:
            self._seen_keys.discard(self._hit_key(hit))

    def _append_unique(self, bucket: list[SearchHit], hit: SearchHit, max_results: int):
        if len(bucket) >= max_results:
            return
        key = self._hit_key(hit)
        if key in self._seen_keys:
            return
        self._seen_keys.add(key)
        bucket.append(hit)

    def _merge_owned(self, *, reserve_enrichment: int) -> list[SearchHit]:
        final_limit = max(1, int(self.final_limit or 5))
        if not self.enrichment_hits:
            return self._slice_unique(self.core_hits, final_limit)
        reserve = max(
            0,
            min(int(reserve_enrichment or 0), final_limit - 1, len(self.enrichment_hits)),
        )
        core_budget = max(1, final_limit - reserve)
        selected_core = self._slice_unique(self.core_hits, core_budget)
        selected_enrichment = self._slice_unique(self.enrichment_hits, reserve)
        return self._slice_unique([*selected_core, *selected_enrichment], final_limit)

    @staticmethod
    def _slice_unique(hits: list[SearchHit], max_results: int) -> list[SearchHit]:
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

    def _localized_names_from_owned_core(self) -> list[str]:
        names: list[str] = []
        for hit in self.core_hits:
            for blob in (hit.title, hit.body):
                text = clean_text(blob)
                if not text:
                    continue
                if text.startswith("other_names:"):
                    for piece in text.split(":", 1)[1].split("|"):
                        name = clean_text(piece)
                        if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", name) and name not in names:
                            names.append(name)
                elif re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", text) and len(text) <= 40:
                    if text not in names:
                        names.append(text)
                for match in re.findall(r"[（(]([^）)]{1,30})[）)]", text):
                    inner = clean_text(match)
                    if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", inner) and inner not in names:
                        names.append(inner)
        return names[:12]

    def _prefer_seed_order(self, seed_names: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add_many(candidates: list[str]):
            for name in candidates:
                text = clean_text(name)
                key = text.lower()
                if not text or key in seen:
                    continue
                seen.add(key)
                ordered.append(text)

        if self.language == "ja":
            add_many([name for name in seed_names if has_kana(name)])
            add_many([name for name in seed_names if has_han(name)])
            add_many(seed_names)
        else:
            add_many([name for name in seed_names if has_han(name) and not mostly_kana(name)])
            add_many([name for name in seed_names if has_han(name)])
            add_many([name for name in seed_names if has_kana(name)])
            add_many(seed_names)
        return ordered
