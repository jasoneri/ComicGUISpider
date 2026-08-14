"""CGS007 TagGroups state machine — single path for all five group labels.

Design (state + pure transitions, no Qt):

    EMPTY
      | capture_submit(panel_prompt, lexicon)
      v
    SNAPSHOT  ----persist---->  tag_groups_json + editor_prompt
      | load_snapshot(row)
      v
    RESOLVED  ----as_groups()---->  AttachImg.groups / chips

    LEGACY_FLAT (no tag_groups_json)
      | classify_flat(editor_prompt, lexicon)
      v
    RESOLVED

Why a state object (not ad-hoc Character/Artist patches):
- TAG_GROUP_ORDER is five labels; every transition MUST fill the same buckets.
- Artist needs @ / underscore / space aliases; Character the same; Copyright/Meta too.
- One lexicon + one classifier stops "fix Character, lose Artist" regressions.

Pattern refs: pure transition functions + immutable value object (FSM without framework).
"""
from __future__ import annotations

import typing as t
from dataclasses import dataclass, field

from utils.script.image.anima import anima_spec
from utils.script.image.anima.prompt_doc import is_model_ref, split_prompt
from utils.script.image.danbooru.tag_prompt import TAG_GROUP_ORDER, TagPrompt

# PromptDoc section name -> TagPrompt group label (full set, no partial maps).
_SECTION_TO_LABEL: dict[str, str] = {
    "character": "Character",
    "artist": "Artist",
    "series": "Copyright",
    "body": "General",
    "subject": "General",
    "prefix": "Meta",
}

_LABEL_TO_SECTION: dict[str, str] = {
    "Character": "character",
    "Artist": "artist",
    "Copyright": "series",
    "General": "body",
    "Meta": "prefix",
}


def _empty_buckets() -> dict[str, list[str]]:
    return {label: [] for label in TAG_GROUP_ORDER}


def _normalize_label(label: object) -> str | None:
    text = str(label or "").strip()
    if text in TAG_GROUP_ORDER:
        return text
    # Tolerate section names if a caller passes PromptDoc-style keys.
    return _SECTION_TO_LABEL.get(text)


def _strip_escape_backslashes(text: str) -> str:
    """Remove ANIMA paren escapes: ``\\(`` / ``\\)`` → bare ``(`` / ``)``."""
    return str(text or "").replace("\\(", "(").replace("\\)", ")")


def _token_aliases(tag: object) -> tuple[str, ...]:
    """All lookup keys for one surface tag (raw / lower / ANIMA normalize / @ / paren forms).

    Danbooru chips use ``miyako_(swimsuit)_(blue_archive)``; editor_prompt uses
    ``miyako \\(swimsuit\\) \\(blue archive\\)``. Both MUST share alias keys.
    """
    raw = str(tag or "").strip()
    if not raw:
        return ()
    aliases: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        key = str(value or "").strip()
        if not key or key in seen:
            return
        seen.add(key)
        aliases.append(key)

    def add_family(token: str) -> None:
        if not token:
            return
        add(token)
        add(token.lower())
        unescaped = _strip_escape_backslashes(token)
        add(unescaped)
        add(unescaped.lower())
        # space ↔ underscore on both escaped and bare-paren surfaces
        for form in (token, unescaped):
            add(form.replace(" ", "_"))
            add(form.replace("_", " "))
            add(form.lower().replace(" ", "_"))
            add(form.lower().replace("_", " "))
        normalized = anima_spec.normalize_tag(unescaped)
        add(normalized)
        add(normalized.replace(" ", "_"))
        add(_strip_escape_backslashes(normalized))

    add_family(raw)
    bare = raw[1:] if raw.startswith("@") else raw
    add_family(bare)
    # Artist / identity often appear with or without @ in editor_prompt.
    add_family(f"@{bare}")
    normalized_bare = anima_spec.normalize_tag(_strip_escape_backslashes(bare))
    add_family(f"@{normalized_bare}")
    return tuple(aliases)


class TagLexicon:
    """Alias index: any surface form → TAG_GROUP_ORDER label.

    Register every known group fully (not Character-only). First registration wins
    so CurrentImg categories stay authoritative over later weaker sources.
    """

    __slots__ = ("_label_by_alias",)

    def __init__(self) -> None:
        self._label_by_alias: dict[str, str] = {}

    @classmethod
    def build(
        cls,
        *group_sources: object,
        extra_known: dict[str, str] | None = None,
    ) -> "TagLexicon":
        lexicon = cls()
        for source in group_sources:
            lexicon.register_groups(source)
        if extra_known:
            for key, section_or_label in extra_known.items():
                label = _normalize_label(section_or_label) or _SECTION_TO_LABEL.get(
                    str(section_or_label or "").strip()
                )
                if label:
                    lexicon.register_tag(key, label)
        return lexicon

    def register_groups(self, groups: object) -> None:
        if not groups:
            return
        if isinstance(groups, TagPrompt):
            pairs = groups.groups
        else:
            pairs = groups
        for entry in pairs or ():
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            label = _normalize_label(entry[0])
            tags = entry[1]
            if not label or not isinstance(tags, (list, tuple)):
                continue
            for tag in tags:
                self.register_tag(tag, label)

    def register_tag(self, tag: object, label: str) -> None:
        resolved = _normalize_label(label)
        if not resolved:
            return
        for alias in _token_aliases(tag):
            self._label_by_alias.setdefault(alias, resolved)

    def classify_token(self, token: object) -> str | None:
        raw = str(token or "").strip()
        if not raw:
            return None
        for alias in _token_aliases(raw):
            label = self._label_by_alias.get(alias)
            if label:
                return label
        # Structural fallbacks (no CurrentImg hit): keep identity out of General when obvious.
        if raw.startswith("@") or is_model_ref(raw):
            if raw.startswith("@"):
                return "Artist"
            return None
        key = anima_spec.normalize_tag(raw)
        if anima_spec.is_prefix_tag(key):
            return "Meta"
        if anima_spec.is_subject_count_tag(key):
            return "General"
        return None


@dataclass(frozen=True)
class TagGroupsState:
    """Immutable resolved groups for all five labels (empty buckets allowed)."""

    buckets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    origin: str = "empty"  # empty | snapshot | flat | viewer | selected

    def __post_init__(self) -> None:
        normalized: dict[str, tuple[str, ...]] = {}
        source = self.buckets or {}
        for label in TAG_GROUP_ORDER:
            tags = source.get(label) or ()
            cleaned: list[str] = []
            seen: set[str] = set()
            for tag in tags:
                token = str(tag or "").strip()
                if not token:
                    continue
                # Dedupe by normalized bare form; keep first surface spelling.
                bare = token[1:] if token.startswith("@") else token
                dedupe_key = anima_spec.normalize_tag(bare)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                cleaned.append(token)
            normalized[label] = tuple(cleaned)
        object.__setattr__(self, "buckets", normalized)

    # --- queries ---

    def as_groups(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """TagPrompt.groups shape: only non-empty labels, TAG_GROUP_ORDER order."""
        return tuple(
            (label, self.buckets[label])
            for label in TAG_GROUP_ORDER
            if self.buckets.get(label)
        )

    def labels(self) -> tuple[str, ...]:
        return tuple(label for label, tags in self.as_groups())

    def is_empty(self) -> bool:
        return not self.as_groups()

    # --- transitions (pure) ---

    @classmethod
    def empty(cls) -> "TagGroupsState":
        return cls(buckets={label: () for label in TAG_GROUP_ORDER}, origin="empty")

    @classmethod
    def from_pairs(
        cls,
        pairs: object,
        *,
        origin: str = "snapshot",
    ) -> "TagGroupsState":
        buckets = _empty_buckets()
        if not pairs:
            return cls(buckets={key: tuple(value) for key, value in buckets.items()}, origin=origin)
        for entry in pairs:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            label = _normalize_label(entry[0])
            tags = entry[1]
            if not label or not isinstance(tags, (list, tuple)):
                continue
            for tag in tags:
                token = str(tag or "").strip()
                if token:
                    buckets[label].append(token)
        return cls(
            buckets={key: tuple(value) for key, value in buckets.items()},
            origin=origin,
        )

    @classmethod
    def from_selected_chips(cls, prompt: TagPrompt) -> "TagGroupsState":
        """Selected chip state only (does not scan dirty preview text)."""
        buckets = _empty_buckets()
        for label, tags in prompt.groups:
            for tag in tags:
                if prompt.is_selected(tag):
                    buckets[label].append(str(tag))
        return cls(
            buckets={key: tuple(value) for key, value in buckets.items()},
            origin="selected",
        )

    @classmethod
    def from_viewer_post(cls, post) -> "TagGroupsState":
        return cls.from_pairs(TagPrompt(post).groups, origin="viewer")

    @classmethod
    def from_flat_prompt(
        cls,
        editor_prompt: str,
        *,
        lexicon: TagLexicon,
    ) -> "TagGroupsState":
        """Classify every comma token into one of the five labels via lexicon."""
        buckets = _empty_buckets()
        for raw in split_prompt(editor_prompt):
            token = str(raw or "").strip()
            if not token:
                continue
            label = lexicon.classify_token(token)
            if label is None:
                label = "General"
            buckets[label].append(token)
        return cls(
            buckets={key: tuple(value) for key, value in buckets.items()},
            origin="flat",
        )

    @classmethod
    def capture_for_submit(
        cls,
        *,
        editor_prompt: str,
        prompt: TagPrompt,
        extra_known: dict[str, str] | None = None,
    ) -> "TagGroupsState":
        """Submit transition: membership = editor_prompt tokens only.

        Lexicon = full CurrentImg groups (all five labels) + comfy_known aliases.
        Must NOT snapshot "selected chips only" — that drops Artist when dirty preview
        still carries @artist, and drops Character when only General chips stay on.
        Surface spelling follows the prompt token (including leading @).
        """
        lexicon = TagLexicon.build(prompt.groups, extra_known=extra_known)
        flat = cls.from_flat_prompt(editor_prompt, lexicon=lexicon)
        return cls(
            buckets=flat.buckets,
            origin="snapshot",
        )

    @classmethod
    def merge_prefer_first(
        cls,
        primary: "TagGroupsState",
        secondary: "TagGroupsState",
        *,
        origin: str,
    ) -> "TagGroupsState":
        """Union buckets; each normalized token appears under exactly one label.

        Primary source wins both surface spelling and label when the same token
        would otherwise land in two groups (e.g. selected Character vs flat General).
        """
        buckets = _empty_buckets()
        claimed: set[str] = set()
        for source in (primary, secondary):
            for label in TAG_GROUP_ORDER:
                for tag in source.buckets.get(label) or ():
                    bare = tag[1:] if str(tag).startswith("@") else tag
                    key = anima_spec.normalize_tag(bare)
                    if key in claimed:
                        continue
                    claimed.add(key)
                    buckets[label].append(tag)
        return cls(
            buckets={key: tuple(value) for key, value in buckets.items()},
            origin=origin,
        )

    @classmethod
    def resolve_for_attach(
        cls,
        *,
        snapshot: dict | None,
        editor_prompt: str,
        lexicon: TagLexicon,
    ) -> "TagGroupsState":
        """Attach transition — identity labels are non-negotiable.

        Algorithm (no shortcuts):
        1. text = snapshot.editor_prompt or editor_prompt
        2. lexicon = panel lexicon ∪ stored **identity/meta** aliases
           (never seed General — poisoned rows dump Character there)
        3. flat = classify every token in text
        4. stored_identity = Character/Artist/Copyright/Meta buckets from snapshot
           (only tokens that still appear in text)
        5. merge_prefer_first(stored_identity, flat)
           → trusted identity wins; flat fills General/Meta gaps

        Character has no ``@`` structural marker (unlike Artist). Without step 4–5,
        a cold attach whose panel lexicon misses the token lands Character in General
        forever (uzaki hana regression) even when submit-time tag_groups had it right.
        """
        _IDENTITY_META = frozenset({"Character", "Artist", "Copyright", "Meta"})

        text = str(editor_prompt or "")
        stored_pairs = ()
        if isinstance(snapshot, dict):
            snap_prompt = str(snapshot.get("editor_prompt") or "").strip()
            if snap_prompt:
                text = snap_prompt
            stored_pairs = snapshot.get("tag_groups") or ()

        if not str(text or "").strip():
            text = str(editor_prompt or "")

        working = lexicon
        identity_seed_pairs = tuple(
            (label, tags)
            for label, tags in (stored_pairs or ())
            if _normalize_label(label) in _IDENTITY_META and tags
        )
        if identity_seed_pairs:
            working = TagLexicon.build()
            working._label_by_alias = dict(lexicon._label_by_alias)
            working.register_groups(identity_seed_pairs)

        flat = cls.from_flat_prompt(text, lexicon=working)

        # Restrict stored identity tokens to those still present in the prompt text.
        prompt_keys: set[str] = set()
        for raw in split_prompt(text):
            token = str(raw or "").strip()
            if not token:
                continue
            bare = token[1:] if token.startswith("@") else token
            prompt_keys.add(anima_spec.normalize_tag(_strip_escape_backslashes(bare)))

        trusted_buckets = _empty_buckets()
        for label, tags in identity_seed_pairs:
            resolved_label = _normalize_label(label)
            if not resolved_label:
                continue
            for tag in tags:
                token = str(tag or "").strip()
                if not token:
                    continue
                bare = token[1:] if token.startswith("@") else token
                key = anima_spec.normalize_tag(_strip_escape_backslashes(bare))
                if key in prompt_keys:
                    trusted_buckets[resolved_label].append(token)
        trusted = cls(
            buckets={key: tuple(value) for key, value in trusted_buckets.items()},
            origin="snapshot",
        )
        if trusted.is_empty():
            return flat
        return cls.merge_prefer_first(trusted, flat, origin="snapshot")

    def to_section_known(self) -> dict[str, str]:
        """PromptDoc known map (normalized + aliases) for highlighters / insert helpers."""
        known: dict[str, str] = {}
        for label, tags in self.as_groups():
            section = _LABEL_TO_SECTION[label]
            for tag in tags:
                for alias in _token_aliases(tag):
                    known.setdefault(alias, section)
        return known


def lexicon_for_panel(panel) -> TagLexicon:
    """Build lexicon from a TagExportPanel-like object (duck-typed)."""
    prompt = getattr(panel, "prompt", None)
    groups = getattr(prompt, "groups", ()) if prompt is not None else ()
    extra = getattr(panel, "comfy_known", None) or {}
    return TagLexicon.build(groups, extra_known=extra)


__all__ = [
    "TagGroupsState",
    "TagLexicon",
    "lexicon_for_panel",
]
