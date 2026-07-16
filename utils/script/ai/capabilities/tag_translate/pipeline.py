from __future__ import annotations

from dataclasses import dataclass, field
import typing as t

from loguru import logger

from utils.script.ai.kernel import AiProvider, OpenAiCompatClient

from .prompts import build_messages, parse_translation_items
from .serp import EvidenceGatherer, SearchEngineName, SearchHit, parse_tag_query


ProgressCallback = t.Callable[["TagTranslateProgress"], None]


@dataclass(slots=True)
class TagTranslateProgress:
    done: int
    total: int
    message: str = ""


@dataclass(slots=True)
class TagTranslateResult:
    translations: dict[str, str] = field(default_factory=dict)
    failed_tags: list[str] = field(default_factory=list)
    skipped_no_evidence: list[str] = field(default_factory=list)


def chunk_tags(tags: t.Iterable[str], size: int = 5) -> list[list[str]]:
    batch_size = max(1, int(size or 5))
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = " ".join(str(raw or "").split())
        if not tag or tag in seen:
            continue
        seen.add(tag)
        ordered.append(tag)
    return [ordered[index : index + batch_size] for index in range(0, len(ordered), batch_size)]


class TagTranslatePipeline:
    def __init__(
        self,
        provider: AiProvider,
        *,
        engine: SearchEngineName = "danbooru",
        language: str = "zh",
        proxies: object = None,
        batch_size: int = 5,
        on_progress: ProgressCallback | None = None,
    ):
        self.provider = provider
        self.engine = engine
        self.language = language if language in {"zh", "ja"} else "zh"
        self.proxies = proxies
        self.batch_size = batch_size
        self.on_progress = on_progress
        self.llm = OpenAiCompatClient(provider, proxies=proxies)
        self.evidence = EvidenceGatherer(
            proxies=proxies,
            language=self.language,
            engine=engine,
        )

    def _emit(self, done: int, total: int, message: str = ""):
        if self.on_progress is None:
            return
        self.on_progress(TagTranslateProgress(done=done, total=total, message=message))

    def _search_batch(self, tags: list[str]) -> list[tuple[str, list[SearchHit]]]:
        batch: list[tuple[str, list[SearchHit]]] = []
        for tag in tags:
            try:
                hits = self.evidence.search(
                    tag,
                    max_results=10 if self.engine != "danbooru" else 8,
                )
            except Exception as exc:
                logger.warning(f"[TagTranslate] search failed tag={tag}: {exc}")
                hits = []
            if not hits:
                logger.warning(f"[TagTranslate] empty evidence tag={tag} engine={self.engine}")
            else:
                sources = sorted({getattr(hit, "source", "") or self.engine for hit in hits})
                logger.info(
                    f"[TagTranslate] evidence ready tag={tag} engine={self.engine} "
                    f"hits={len(hits)} sources={sources} first={hits[0].title!r}"
                )
            batch.append((tag, hits))
        return batch

    def _translate_batch(self, batch: list[tuple[str, list[SearchHit]]]) -> dict[str, str]:
        """Only tags with non-empty SERP evidence are sent to the LLM."""
        evidence_batch = [(origin, hits) for origin, hits in batch if hits]
        empty_tags = [origin for origin, hits in batch if not hits]
        if empty_tags:
            logger.warning(
                f"[TagTranslate] skip LLM for empty-evidence tags={empty_tags} engine={self.engine}"
            )
        if not evidence_batch:
            logger.warning("[TagTranslate] entire batch has no SERP evidence; LLM not called")
            return {}

        messages = build_messages(language=self.language, batch=evidence_batch)
        try:
            return parse_translation_items(self.llm.chat_content(messages))
        except Exception as batch_error:
            logger.warning(f"[TagTranslate] batch llm failed, fallback 1:1: {batch_error}")
            translations: dict[str, str] = {}
            for origin, hits in evidence_batch:
                try:
                    single = parse_translation_items(
                        self.llm.chat_content(
                            build_messages(language=self.language, batch=[(origin, hits)])
                        )
                    )
                    if origin in single:
                        translations[origin] = single[origin]
                except Exception as single_error:
                    logger.warning(f"[TagTranslate] single llm failed tag={origin}: {single_error}")
            return translations

    def _order_tags_parent_first(self, tags: list[str]) -> list[str]:
        """
        Expand missing parent character tags and place them before costume variants.
        Parents must be translated (and mergeable) before costume SERP runs.
        """
        requested = list(tags)
        seen: set[str] = set(requested)
        expanded: list[str] = []
        costumes: list[str] = []
        for tag in requested:
            parts = parse_tag_query(tag)
            if parts.costume and parts.parent_tag:
                parent_key = parts.parent_tag
                if parent_key not in seen:
                    parent_already_mapped = False
                    try:
                        from utils.config.qc import danbooru_cfg

                        mapped = danbooru_cfg.get_translate_map().get(
                            danbooru_cfg.canonicalize_term(parent_key)
                        )
                        parent_already_mapped = bool(
                            danbooru_cfg.canonicalize_term(str(mapped or ""))
                        )
                    except Exception:
                        parent_already_mapped = False
                    if not parent_already_mapped:
                        seen.add(parent_key)
                        expanded.append(parent_key)
                costumes.append(tag)
            else:
                expanded.append(tag)
        for tag in costumes:
            if tag not in expanded:
                expanded.append(tag)
        return expanded

    def run(self, tags: t.Iterable[str]) -> TagTranslateResult:
        if not self.provider.is_configured():
            raise ValueError("AI provider is not configured")
        flat_tags = self._order_tags_parent_first(
            [tag for chunk in chunk_tags(tags, self.batch_size) for tag in chunk]
        )
        chunks = chunk_tags(flat_tags, self.batch_size)
        total = len(flat_tags)
        self._emit(0, total, "start")
        result = TagTranslateResult()
        done = 0
        for chunk in chunks:
            batch = self._search_batch(chunk)
            translations = self._translate_batch(batch)
            if translations:
                result.translations.update(translations)
                try:
                    from utils.config.qc import danbooru_cfg

                    danbooru_cfg.merge_translate_map(translations)
                except Exception as merge_error:
                    logger.warning(
                        f"[TagTranslate] mid-run translate_map merge failed: {merge_error}"
                    )
            for origin, hits in batch:
                if not hits:
                    result.skipped_no_evidence.append(origin)
                    result.failed_tags.append(origin)
                else:
                    if origin not in translations:
                        result.failed_tags.append(origin)
                done += 1
                self._emit(done, total, origin)
        if result.skipped_no_evidence:
            logger.error(
                f"[TagTranslate] finished with no-evidence tags={result.skipped_no_evidence} "
                f"engine={self.engine}"
            )
        return result
