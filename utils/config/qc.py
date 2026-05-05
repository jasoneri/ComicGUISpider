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
    doh: "CgsConfig.DoH"

    class DoH:
        def __init__(self, cfg: "CgsConfig"):
            self._cfg = cfg

        @staticmethod
        def _normalize(value: object) -> str:
            raw_value = str(value or "").strip()
            return normalize_doh_url(raw_value) if raw_value else ""

        def get_url(self) -> str:
            return self._normalize(self._cfg.dohUrl.value)

        def get_history(self) -> list[str]:
            history = []
            for item in list(self._cfg.dohHistory.value or []):
                try:
                    normalized = self._normalize(item)
                except ValueError:
                    continue
                if normalized and normalized not in history:
                    history.append(normalized)
            return history

        def set_url(self, value: object) -> str:
            normalized = self._normalize(value)
            self._cfg.dohUrl.value = normalized
            if normalized:
                history = [item for item in self.get_history() if item != normalized]
                history.insert(0, normalized)
                self._cfg.dohHistory.value = history[:20]
            self._cfg.save()
            return normalized


cgs_cfg = CgsConfig()
qconfig.load(_qconfig_path("qc.json"), cgs_cfg)
cgs_cfg.doh = CgsConfig.DoH(cgs_cfg)


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
    fav: "KemonoConfig.Favorites"

    class Favorites:
        def __init__(self, cfg: "KemonoConfig"):
            self._cfg = cfg

        def in_(self, author_id: str) -> bool:
            return author_id in self.get_favorites()

        def faved_(self, author_id: str) -> bool:
            return self.in_(author_id)

        def toggle_favorite(self, author_id: str) -> bool:
            favorites = self.get_favorites()
            if author_id in favorites:
                favorites.remove(author_id)
                is_favorited = False
            else:
                favorites.append(author_id)
                is_favorited = True
            self._cfg.favoriteAuthors.value = favorites
            self._cfg.save()
            return is_favorited

        def get_favorites(self) -> list[str]:
            return list(self._cfg.favoriteAuthors.value or [])


kemono_cfg = KemonoConfig()
qconfig.load(_qconfig_path("qc_kemono.json"), kemono_cfg)
kemono_cfg.fav = KemonoConfig.Favorites(kemono_cfg)


class DanbooruConfig(QConfig):
    DEFAULT_FAVORITE_GROUP = "normal"
    RESERVED_SEARCH_KEYS = frozenset({"History", "Favorites", DEFAULT_FAVORITE_GROUP})

    searchHistory = ConfigItem("Search", "History", [], restart=False)
    searchExtra = ConfigItem("Search", "SearchExtra", [], restart=False)
    searchFavorites = ConfigItem("Search", "Favorites", {}, restart=False)
    view_ratio = RangeConfigItem("Viewer", "ViewRatio", _default_danbooru_view_ratio(), RangeValidator(30, 85), restart=False)
    player = ConfigItem("Viewer", "Player", {}, restart=False)

    @staticmethod
    def canonicalize_term(term: str) -> str:
        return " ".join((term or "").split())

    def toDict(self, serialize=True):
        self.fav.groups()
        return super().toDict(serialize=serialize)

    def get_view_ratio_percent(self) -> int:
        return int(self.view_ratio.value)

    def get_view_ratio(self) -> float:
        return self.get_view_ratio_percent() / 100

    def get_player(self) -> dict:
        player = self.player.value if isinstance(self.player.value, dict) else {}
        muted = player.get("muted", True)
        volume = player.get("volume", 30)
        normalized = {
            "muted": muted if isinstance(muted, bool) else True,
            "volume": max(0, min(100, volume if isinstance(volume, int) else 30)),
        }
        if normalized != self.player.value:
            self.player.value = dict(normalized)
        return dict(normalized)

    def save_player(self, *, muted=None, volume=None) -> dict:
        player = self.get_player()
        if muted is not None:
            player["muted"] = bool(muted)
        if volume is not None:
            player["volume"] = max(0, min(100, int(volume)))
        if player != self.player.value:
            self.player.value = dict(player)
            self.save()
        return dict(player)

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

    def get_search_extra(self):
        return list(self.searchExtra.value)

    def add_search_extra(self, term: str):
        canonical = self.canonicalize_term(term)
        if not canonical:
            return
        extras = [item for item in self.searchExtra.value if item != canonical]
        extras.insert(0, canonical)
        self.searchExtra.value = extras[:30]
        self.save()

    class Favorites:
        DEFAULT_FAVORITE_GROUP = "normal"

        def __init__(self, cfg: "DanbooruConfig"):
            self._cfg = cfg

        def groups(self) -> dict[str, list[str]]:
            if isinstance(self._cfg.searchFavorites.value, list):
                self._cfg.searchFavorites.value = {}
            return self._cfg.searchFavorites.value

        def _normalize_tags(self, tags) -> list[str]:
            return list(dict.fromkeys(normalized for raw_tag in tags if (normalized := self._cfg.canonicalize_term(str(raw_tag)))))

        def get(self) -> set[str]:
            return set(self._normalize_tags(self.groups().get(self.DEFAULT_FAVORITE_GROUP, [])))

        def is_(self, term: str) -> bool:
            return self._cfg.canonicalize_term(term) in self.get()

        def add(self, term: str) -> set[str]:
            canonical = self._cfg.canonicalize_term(term)
            if not canonical:
                return self.get()
            groups = self.groups()
            favorites = self.get()
            favorites.add(canonical)
            groups[self.DEFAULT_FAVORITE_GROUP] = sorted(favorites)
            self._cfg.save()
            return self.get()

        def remove(self, term: str) -> set[str]:
            canonical = self._cfg.canonicalize_term(term)
            groups = self.groups()
            favorites = self.get()
            favorites.discard(canonical)
            groups[self.DEFAULT_FAVORITE_GROUP] = sorted(favorites)
            self._cfg.save()
            return self.get()

        def toggle(self, term: str) -> bool:
            canonical = self._cfg.canonicalize_term(term)
            if not canonical:
                return False
            groups = self.groups()
            favorites = self.get()
            is_favorited = canonical not in favorites
            if is_favorited:
                favorites.add(canonical)
            else:
                favorites.discard(canonical)
            groups[self.DEFAULT_FAVORITE_GROUP] = sorted(favorites)
            self._cfg.save()
            return is_favorited

        def move_to_group(self, term: str, group_name: str):
            canonical = self._cfg.canonicalize_term(term)
            if not canonical or not group_name or group_name == self.DEFAULT_FAVORITE_GROUP:
                return
            groups = self.groups()
            groups[self.DEFAULT_FAVORITE_GROUP] = [t for t in groups.get(self.DEFAULT_FAVORITE_GROUP, []) if t != canonical]
            target = list(groups.get(group_name, []))
            if canonical not in target:
                target.append(canonical)
                groups[group_name] = target
            self._cfg.save()

        def get_grouped(self) -> list[tuple[str, list[str]]]:
            groups = []
            for raw_name, raw_tags in self.groups().items():
                group_name = self._cfg.canonicalize_term(str(raw_name))
                if not group_name or group_name == self.DEFAULT_FAVORITE_GROUP:
                    continue
                groups.append((group_name, self._normalize_tags(raw_tags)))
            return groups

        def save_grouped(self, groups_output: dict[str, list[str]]):
            groups = {}
            for raw_name, raw_tags in groups_output.items():
                group_name = self._cfg.canonicalize_term(str(raw_name))
                if not group_name or group_name == "History":
                    continue
                output_name = self.DEFAULT_FAVORITE_GROUP if group_name == "Favorites" else group_name
                tags = self._normalize_tags(raw_tags)
                groups[output_name] = sorted(tags) if output_name == self.DEFAULT_FAVORITE_GROUP else tags
            self._cfg.searchFavorites.value = groups
            self._cfg.save()


danbooru_cfg = DanbooruConfig()
qconfig.load(_qconfig_path("qc_danbooru.json"), danbooru_cfg)
danbooru_cfg.fav = DanbooruConfig.Favorites(danbooru_cfg)
danbooru_cfg.fav.groups()
