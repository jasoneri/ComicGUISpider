from __future__ import annotations

from dataclasses import dataclass, field
import typing as t


_DEFAULT_FAVORITE_PAYLOAD_KEY = "normal"
_DEFAULT_FAVORITE_GROUP_NAME = "Favorites"
_RESERVED_PAYLOAD_KEYS = frozenset({"History"})
RESERVED_GROUP_NAMES = frozenset({_DEFAULT_FAVORITE_PAYLOAD_KEY, _DEFAULT_FAVORITE_GROUP_NAME, *_RESERVED_PAYLOAD_KEYS})


def _dedupe_tags(tags: t.Iterable[str]) -> list[str]:
    deduped = []
    for raw_tag in tags:
        tag = str(raw_tag).strip()
        if tag and tag not in deduped:
            deduped.append(tag)
    return deduped


def _default_canonicalize_term(term: str) -> str:
    return " ".join((term or "").split())


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
        super().__init__(name=_DEFAULT_FAVORITE_GROUP_NAME, tags=list(tags), _display="默认收藏")


@dataclass(slots=True)
class FavoriteGroupsState:
    default_group: DefaultTagGroup = field(default_factory=DefaultTagGroup)
    custom_groups: list[TagGroup] = field(default_factory=list)
    canonicalize_term: t.Callable[[str], str] = field(
        default=_default_canonicalize_term,
        repr=False,
        compare=False,
    )

    @classmethod
    def from_payload(
        cls,
        payload: object,
        canonicalize_term: t.Callable[[str], str] | None = None,
    ) -> "FavoriteGroupsState":
        canonicalize = canonicalize_term or _default_canonicalize_term
        default_tags: list[str] = []
        custom_groups: list[TagGroup] = []
        if isinstance(payload, dict):
            for raw_name, raw_tags in payload.items():
                group_name = canonicalize(str(raw_name))
                if not group_name or group_name in _RESERVED_PAYLOAD_KEYS or not isinstance(raw_tags, list):
                    continue
                tags = _dedupe_tags(
                    normalized
                    for raw_tag in raw_tags
                    if (normalized := canonicalize(str(raw_tag)))
                )
                if group_name in {_DEFAULT_FAVORITE_PAYLOAD_KEY, _DEFAULT_FAVORITE_GROUP_NAME}:
                    default_tags.extend(tags)
                    continue
                custom_groups.append(TagGroup(group_name, tags))
        return cls(
            default_group=DefaultTagGroup(default_tags),
            custom_groups=custom_groups,
            canonicalize_term=canonicalize,
        )

    @property
    def default_tags(self) -> list[str]:
        return list(self.default_group.tags)

    @property
    def groups(self) -> list[TagGroup]:
        return [self.default_group, *self.custom_groups]

    def copy(self) -> "FavoriteGroupsState":
        return FavoriteGroupsState(
            default_group=DefaultTagGroup(self.default_group.tags),
            custom_groups=[TagGroup(group.name, group.tags) for group in self.custom_groups],
            canonicalize_term=self.canonicalize_term,
        )

    def all_terms(self) -> set[str]:
        return {tag for group in self.groups for tag in group.tags}

    def visible_groups(self) -> list[TagGroup]:
        return visible_usage_groups(self.groups)

    def to_payload(self) -> dict[str, list[str]]:
        payload = {_DEFAULT_FAVORITE_PAYLOAD_KEY: sorted(self.default_tags)}
        for group in self.custom_groups:
            payload[group.name] = list(group.tags)
        return payload

    def ensure_custom_group(self) -> str:
        if not self.custom_groups:
            self.custom_groups.append(TagGroup("custom1", []))
        return self.custom_groups[0].name

    def group_names(self) -> list[str]:
        return [group.name for group in self.custom_groups]

    def current_group_name(self, current_group: str | None = None) -> str:
        self.ensure_custom_group()
        return current_group if current_group in self.group_names() else self.group_names()[0]

    def _is_default_group_name(self, group_name: str) -> bool:
        return group_name in {_DEFAULT_FAVORITE_PAYLOAD_KEY, _DEFAULT_FAVORITE_GROUP_NAME}

    def group(self, group_name: str) -> TagGroup:
        canonical = self._canonicalize(group_name)
        if self._is_default_group_name(canonical):
            return self.default_group
        for group in self.custom_groups:
            if group.name == canonical:
                return group
        raise ValueError(f"收藏组不存在: {canonical}")

    def set_default_tags(self, tags: t.Iterable[str]):
        self.default_group.set_tags(sorted(self._normalize_terms(tags)))

    def contains(self, term: str) -> bool:
        canonical = self._canonicalize(term)
        if not canonical:
            return False
        return any(canonical in group.tags for group in self.groups)

    def remove_from_all(self, term: str) -> bool:
        canonical = self._canonicalize(term)
        if not canonical:
            return False
        changed = False
        for group in self.groups:
            if canonical not in group.tags:
                continue
            group.set_tags(current for current in group.tags if current != canonical)
            changed = True
        return changed

    def toggle(self, term: str) -> bool:
        canonical = self._canonicalize(term)
        if not canonical:
            return False
        if self.contains(canonical):
            self.remove_from_all(canonical)
            return False
        self.default_group.add_tags([canonical])
        self.default_group.set_tags(sorted(self.default_group.tags))
        return True

    def move_to_group(self, term: str, group_name: str):
        canonical = self._canonicalize(term)
        target_name = self._canonicalize(group_name)
        if not canonical or not target_name or target_name in RESERVED_GROUP_NAMES:
            return
        self.remove_from_all(canonical)
        self.group(target_name).add_tags([canonical])

    def create_custom_group(self, prefix: str = "custom") -> str:
        base_name = self._canonicalize(prefix) or "custom"
        index = 1
        while f"{base_name}{index}" in self.group_names():
            index += 1
        group_name = f"{base_name}{index}"
        self.custom_groups.append(TagGroup(group_name, []))
        return group_name

    def rename_custom_group(self, group_name: str, new_name: str) -> str:
        group = self.group(group_name)
        if group is self.default_group:
            raise ValueError("默认收藏组不可重命名")
        normalized = self._canonicalize(new_name)
        if not normalized:
            raise ValueError("收藏组名称不能为空")
        if normalized in RESERVED_GROUP_NAMES:
            raise ValueError(f"收藏组名称不能是 {normalized}")
        if normalized != group.name and normalized in self.group_names():
            raise ValueError(f"收藏组已存在: {normalized}")
        group.name = normalized
        return normalized

    def delete_custom_group(self, group_name: str) -> str:
        group = self.group(group_name)
        if group is self.default_group:
            raise ValueError("默认收藏组不可删除")
        self.custom_groups = [current for current in self.custom_groups if current.name != group.name]
        return self.ensure_custom_group()

    def remove_group_tag(self, group_name: str, term: str) -> bool:
        canonical = self._canonicalize(term)
        if not canonical:
            return False
        group = self.group(group_name)
        if canonical not in group.tags:
            return False
        group.set_tags(tag for tag in group.tags if tag != canonical)
        return True

    def move_default_tags_to_group(self, terms: t.Iterable[str], group_name: str):
        group = self.group(group_name)
        if group is self.default_group:
            return
        normalized_terms = self._normalize_terms(terms)
        if not normalized_terms:
            return
        selected = set(normalized_terms)
        group.add_tags(normalized_terms)
        self.set_default_tags(tag for tag in self.default_tags if tag not in selected)

    def move_group_tags_to_default(self, group_name: str, terms: t.Iterable[str]):
        group = self.group(group_name)
        if group is self.default_group:
            return
        normalized_terms = self._normalize_terms(terms)
        if not normalized_terms:
            return
        selected = set(normalized_terms)
        group.set_tags(tag for tag in group.tags if tag not in selected)
        self.set_default_tags([*self.default_tags, *normalized_terms])

    def move_groups_to_default(self, group_names: t.Iterable[str]) -> str:
        selected_names = {
            group.name
            for raw_name in group_names
            if (group := self.group(raw_name)) is not self.default_group
        }
        if not selected_names:
            return self.current_group_name()
        moved_tags: list[str] = []
        remaining_groups = []
        for group in self.custom_groups:
            if group.name in selected_names:
                moved_tags.extend(group.tags)
                continue
            remaining_groups.append(group)
        self.custom_groups = remaining_groups
        self.ensure_custom_group()
        self.set_default_tags([*self.default_tags, *moved_tags])
        return self.current_group_name()

    def _canonicalize(self, term: str) -> str:
        return self.canonicalize_term(str(term or ""))

    def _normalize_terms(self, tags: t.Iterable[str]) -> list[str]:
        return _dedupe_tags(
            normalized
            for raw_tag in tags
            if (normalized := self._canonicalize(raw_tag))
        )


def build_favorite_groups_state(
    payload: object,
    canonicalize_term: t.Callable[[str], str],
) -> FavoriteGroupsState:
    return FavoriteGroupsState.from_payload(payload, canonicalize_term=canonicalize_term)


def build_tag_groups(default_tags: t.Iterable[str], grouped_favorites: t.Iterable[tuple[str, t.Iterable[str]]]) -> list[TagGroup]:
    return FavoriteGroupsState(
        default_group=DefaultTagGroup(default_tags),
        custom_groups=[TagGroup(group_name, list(tags)) for group_name, tags in grouped_favorites],
    ).groups


def visible_usage_groups(groups: t.Iterable[TagGroup]) -> list[TagGroup]:
    return [group for group in groups if group.tags]
