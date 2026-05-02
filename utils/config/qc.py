import shutil

from qfluentwidgets import QConfig, ConfigItem, RangeConfigItem, RangeValidator, qconfig

from utils.config import ScriptConf, conf_dir, qconfig_dir
from utils.network.doh import normalize_doh_url


def _qconfig_path(name: str):
    target = qconfig_dir.joinpath(name)
    legacy = conf_dir.joinpath(name)
    if legacy.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(target))
    return target


def _default_danbooru_view_ratio() -> int:
    danbooru_config = getattr(ScriptConf(iname="img"), "danbooru", {}) or {}
    return int(danbooru_config.get("view_ratio") or 65)


class CgsConfig(QConfig):
    proxyHistory = ConfigItem("Proxy", "History", ["127.0.0.1:10809"], restart=False)
    dohUrl = ConfigItem("DoH", "Url", "", restart=False)
    dohHistory = ConfigItem("DoH", "History", [], restart=False)

    def get_doh_url(self) -> str:
        raw_value = str(self.dohUrl.value or "").strip()
        return normalize_doh_url(raw_value) if raw_value else ""

    def get_doh_history(self) -> list[str]:
        history = []
        for item in list(self.dohHistory.value or []):
            try:
                text = str(item or "").strip()
                normalized = normalize_doh_url(text)
            except ValueError:
                continue
            if normalized not in history:
                history.append(normalized)
        return history

    def set_doh_url(self, value: object) -> str:
        raw_value = str(value or "").strip()
        normalized = normalize_doh_url(raw_value) if raw_value else ""
        self.dohUrl.value = normalized
        if normalized:
            history = [item for item in self.get_doh_history() if item != normalized]
            history.insert(0, normalized)
            self.dohHistory.value = history[:20]
        self.save()
        return normalized


cgs_cfg = CgsConfig()
qconfig.load(_qconfig_path("qc.json"), cgs_cfg)


class CbgConfig(QConfig):
    scanRoot = ConfigItem("Scan", "Root", "", restart=False)
    includePrevious = ConfigItem("Random", "IncludePrevious", True, restart=False)
    randomCount = ConfigItem("Random", "Count", 10, restart=False)
    generatedPaths = ConfigItem("History", "GeneratedPaths", [], restart=False)


cbg_cfg = CbgConfig()
qconfig.load(_qconfig_path("qc_cbg.json"), cbg_cfg)


class KemonoConfig(QConfig):
    """Kemono配置管理，包含过滤和收藏功能"""
    filterText = ConfigItem("Filter", "FilterText", "", restart=False)
    favoriteAuthors = ConfigItem("Favorites", "Authors", [], restart=False)

    def is_favorite(self, author_id):
        """检查是否已收藏"""
        return author_id in self.favoriteAuthors.value

    def toggle_favorite(self, author_id):
        """切换收藏状态，返回新状态"""
        favorites = self.favoriteAuthors.value.copy()
        if author_id in favorites:
            favorites.remove(author_id)
            is_favorited = False
        else:
            favorites.append(author_id)
            is_favorited = True

        self.favoriteAuthors.value = favorites
        self.save()
        return is_favorited

    def is_favorited(self, author_id):
        """检查是否已收藏"""
        return author_id in self.favoriteAuthors.value

    def get_favorites(self):
        """获取所有收藏"""
        return self.favoriteAuthors.value


kemono_cfg = KemonoConfig()
qconfig.load(_qconfig_path("qc_kemono.json"), kemono_cfg)


class DanbooruConfig(QConfig):
    DEFAULT_FAVORITE_GROUP = "normal"
    RESERVED_SEARCH_KEYS = frozenset({"History", "Favorites", DEFAULT_FAVORITE_GROUP})

    searchHistory = ConfigItem("Search", "History", [], restart=False)
    searchFavorites = ConfigItem("Search", "Favorites", {}, restart=False)
    view_ratio = RangeConfigItem("Viewer", "ViewRatio", _default_danbooru_view_ratio(), RangeValidator(30, 85), restart=False)

    @staticmethod
    def canonicalize_term(term: str) -> str:
        return " ".join((term or "").split())

    def _favorite_groups(self) -> dict[str, list[str]]:
        if isinstance(self.searchFavorites.value, list):
            self.searchFavorites.value = {}
        return self.searchFavorites.value

    def _normalize_tags(self, tags) -> list[str]:
        return list(dict.fromkeys(normalized for raw_tag in tags if (normalized := self.canonicalize_term(str(raw_tag)))))

    def toDict(self, serialize=True):
        self._favorite_groups()
        return super().toDict(serialize=serialize)

    def get_grouped_favorites(self) -> list[tuple[str, list[str]]]:
        groups = []
        for raw_name, raw_tags in self._favorite_groups().items():
            group_name = self.canonicalize_term(str(raw_name))
            if not group_name or group_name == self.DEFAULT_FAVORITE_GROUP:
                continue
            groups.append((group_name, self._normalize_tags(raw_tags)))
        return groups

    def save_grouped_favorites(self, groups_output: dict[str, list[str]]):
        groups = {}
        for raw_name, raw_tags in groups_output.items():
            group_name = self.canonicalize_term(str(raw_name))
            if not group_name or group_name == "History":
                continue
            output_name = self.DEFAULT_FAVORITE_GROUP if group_name == "Favorites" else group_name
            tags = self._normalize_tags(raw_tags)
            groups[output_name] = sorted(tags) if output_name == self.DEFAULT_FAVORITE_GROUP else tags
        self.searchFavorites.value = groups
        self.save()

    def get_view_ratio_percent(self) -> int:
        return int(self.view_ratio.value)

    def get_view_ratio(self) -> float:
        return self.get_view_ratio_percent() / 100

    def get_history(self):
        return list(self.searchHistory.value)

    def add_history(self, term: str):
        canonical = self.canonicalize_term(term)
        if not canonical:
            return []
        history = [item for item in self.searchHistory.value if item != canonical]
        history.insert(0, canonical)
        self.searchHistory.value = history[:50]
        self.save()
        return self.get_history()

    def get_favorites(self):
        return set(self._normalize_tags(self._favorite_groups().get(self.DEFAULT_FAVORITE_GROUP, [])))

    def is_favorite(self, term: str) -> bool:
        return self.canonicalize_term(term) in self.get_favorites()

    def add_favorite(self, term: str):
        canonical = self.canonicalize_term(term)
        if not canonical:
            return self.get_favorites()
        groups = self._favorite_groups()
        favorites = self.get_favorites()
        favorites.add(canonical)
        groups[self.DEFAULT_FAVORITE_GROUP] = sorted(favorites)
        self.save()
        return self.get_favorites()

    def remove_favorite(self, term: str):
        canonical = self.canonicalize_term(term)
        groups = self._favorite_groups()
        favorites = self.get_favorites()
        favorites.discard(canonical)
        groups[self.DEFAULT_FAVORITE_GROUP] = sorted(favorites)
        self.save()
        return self.get_favorites()

    def toggle_favorite(self, term: str) -> bool:
        canonical = self.canonicalize_term(term)
        if not canonical:
            return False
        groups = self._favorite_groups()
        favorites = self.get_favorites()
        is_favorited = canonical not in favorites
        if is_favorited:
            favorites.add(canonical)
        else:
            favorites.discard(canonical)
        groups[self.DEFAULT_FAVORITE_GROUP] = sorted(favorites)
        self.save()
        return is_favorited

    def move_favorite_to_group(self, term: str, group_name: str):
        canonical = self.canonicalize_term(term)
        if not canonical or not group_name or group_name == self.DEFAULT_FAVORITE_GROUP:
            return
        groups = self._favorite_groups()
        groups[self.DEFAULT_FAVORITE_GROUP] = [t for t in groups.get(self.DEFAULT_FAVORITE_GROUP, []) if t != canonical]
        target = list(groups.get(group_name, []))
        if canonical not in target:
            target.append(canonical)
            groups[group_name] = target
        self.save()


danbooru_cfg = DanbooruConfig()
qconfig.load(_qconfig_path("qc_danbooru.json"), danbooru_cfg)
danbooru_cfg._favorite_groups()
