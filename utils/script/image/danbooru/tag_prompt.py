from __future__ import annotations

from .models import DanbooruPost


# Display / selection / identity-line order -- must match viewer keypad Num1/2/3.
TAG_GROUP_ORDER: tuple[str, ...] = (
    "Character",
    "Artist",
    "Copyright",
    "General",
    "Meta",
)
PROMPT_BODY_GROUPS: frozenset[str] = frozenset({"General", "Meta"})
IDENTITY_GROUPS: tuple[str, ...] = ("Character", "Artist", "Copyright")
DEFAULT_CHECKED_GROUPS: frozenset[str] = frozenset({"General"})

NOISE_TAG_BLACKLIST: frozenset[str] = frozenset(
    {
        "highres",
        "absurdres",
        "incredibly_absurdres",
        "translated",
        "partially_translated",
        "check_translation",
        "commentary",
        "commentary_request",
        "artist_name",
        "signature",
        "watermark",
        "username",
        "twitter_username",
        "jpeg_artifacts",
        "scan",
        "image_sample",
        "duplicate",
    }
)

_GROUP_ATTR: dict[str, str] = {
    "Character": "tag_string_character",
    "Artist": "tag_string_artist",
    "Copyright": "tag_string_copyright",
    "General": "tag_string_general",
    "Meta": "tag_string_meta",
}
_IDENTITY_LABEL: dict[str, str] = {
    "Character": "character",
    "Artist": "artist",
    "Copyright": "copyright",
}


class TagPrompt:
    def __init__(self, post: DanbooruPost):
        self.post = post
        groups: list[tuple[str, tuple[str, ...]]] = []
        for label in TAG_GROUP_ORDER:
            tags = tuple(tag for tag in str(getattr(post, _GROUP_ATTR[label], "") or "").split(" ") if tag)
            if tags:
                groups.append((label, tags))
        self.groups = tuple(groups)
        self._selected: set[str] = set()
        self.restore_defaults()

    def is_selected(self, tag: str) -> bool:
        return tag in self._selected

    def set_selected(self, tag: str, selected: bool):
        if selected:
            self._selected.add(tag)
        else:
            self._selected.discard(tag)

    def restore_defaults(self):
        self._selected = {
            tag
            for label, tags in self.groups
            if label in DEFAULT_CHECKED_GROUPS
            for tag in tags
            if tag not in NOISE_TAG_BLACKLIST
        }

    def select_all(self):
        self._selected = {tag for _, tags in self.groups for tag in tags}

    def clear_selection(self):
        self._selected.clear()

    def prompt_body(self) -> str:
        selected: list[str] = []
        seen: set[str] = set()
        for label, tags in self.groups:
            if label not in PROMPT_BODY_GROUPS:
                continue
            for tag in tags:
                if tag not in self._selected or tag in NOISE_TAG_BLACKLIST or tag in seen:
                    continue
                selected.append(tag)
                seen.add(tag)
        return ", ".join(selected)

    def identity(self) -> dict[str, list[str]]:
        return {
            _IDENTITY_LABEL[label]: [tag for tag in tags if tag in self._selected and tag not in NOISE_TAG_BLACKLIST]
            for label, tags in self.groups
            if label in IDENTITY_GROUPS and any(tag in self._selected and tag not in NOISE_TAG_BLACKLIST for tag in tags)
        }

    def prompt_text(self) -> str:
        body = self.prompt_body()
        identity_lines = [f"{label}: {', '.join(tags)}" for label, tags in self.identity().items()]
        if not identity_lines:
            return body
        if not body:
            return "\n".join(identity_lines)
        return body + "\n\n" + "\n".join(identity_lines)
