from __future__ import annotations

from dataclasses import dataclass, field
import typing as t


def _dedupe_tags(tags: t.Iterable[str]) -> list[str]:
    deduped = []
    for raw_tag in tags:
        tag = str(raw_tag).strip()
        if tag and tag not in deduped:
            deduped.append(tag)
    return deduped


@dataclass(slots=True)
class TagGroup:
    name: str
    tags: list[str] = field(default_factory=list)
    _display: str | None = field(default=None, repr=False)

    def __post_init__(self):
        self.tags = _dedupe_tags(self.tags)

    @property
    def display(self) -> str:
        return self._display or self.name

    @property
    def output(self) -> dict[str, list[str]]:
        return {self.name: list(self.tags)}

    def set_tags(self, tags: t.Iterable[str]):
        self.tags = _dedupe_tags(tags)

    def add_tags(self, tags: t.Iterable[str]):
        existing = set(self.tags)
        for tag in _dedupe_tags(tags):
            if tag in existing:
                continue
            self.tags.append(tag)
            existing.add(tag)


class DefaultTagGroup(TagGroup):
    def __init__(self, tags: t.Iterable[str] = ()):
        super().__init__(name="Favorites", tags=list(tags), _display="默认收藏")


def build_tag_groups(
    default_tags: t.Iterable[str],
    grouped_favorites: t.Iterable[tuple[str, t.Iterable[str]]],
) -> list[TagGroup]:
    groups: list[TagGroup] = [DefaultTagGroup(default_tags)]
    groups.extend(TagGroup(group_name, list(tags)) for group_name, tags in grouped_favorites)
    return groups


def visible_usage_groups(groups: t.Iterable[TagGroup]) -> list[TagGroup]:
    return [group for group in groups if group.tags]
