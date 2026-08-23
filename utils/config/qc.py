import shutil

from qfluentwidgets import QConfig, ConfigItem, RangeConfigItem, RangeValidator, qconfig

from utils.config import ScriptConf, conf_dir, qconfig_dir
from utils.network.doh_policy import normalize_doh_url


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
    searchHistory = ConfigItem("Search", "History", [], restart=False)
    scriptWinRect = ConfigItem("ScriptWindow", "Rect", [], restart=False)
    subscribeWinRect = ConfigItem("SubscribeWindow", "Rect", [], restart=False)
    # Active subscription binding profile (subscription_{name}.yml); tray + GUI share this.
    activeSubscriptionCustomname = ConfigItem("Subscription", "ActiveCustomname", "default", restart=False)
    # Global catch-up (后巡查) cadence for tray Schedule — off|3h|12h|daily|2d.
    subscriptionCatchupPreset = ConfigItem("Subscription", "CatchupPreset", "off", restart=False)
    hiddenSiteChoices = ConfigItem("MainWindow", "HiddenSiteChoices", [], restart=False)
    doh: "CgsConfig.DoH"
    search: "CgsConfig.Search"
    site_choices: "CgsConfig.SiteChoices"

    class SiteChoices:
        def __init__(self, cfg: "CgsConfig"):
            self._cfg = cfg

        @staticmethod
        def _normalize(value: object, valid_indexes) -> list[int]:
            valid = {int(index) for index in valid_indexes}
            normalized = []
            for raw_index in list(value or []):
                index = int(raw_index)
                if index in valid and index not in normalized:
                    normalized.append(index)
            return sorted(normalized)

        def hidden(self, valid_indexes) -> set[int]:
            normalized = self._normalize(self._cfg.hiddenSiteChoices.value, valid_indexes)
            if normalized != self._cfg.hiddenSiteChoices.value:
                self._cfg.hiddenSiteChoices.value = normalized
            return set(normalized)

        def set_hidden(self, site_index: int, is_hidden: bool, valid_indexes) -> set[int]:
            valid = {int(index) for index in valid_indexes}
            index = int(site_index)
            if index not in valid:
                raise ValueError(f"invalid site index: {site_index}")
            hidden = self.hidden(valid)
            if is_hidden:
                hidden.add(index)
            else:
                hidden.discard(index)
            self._cfg.hiddenSiteChoices.value = sorted(hidden)
            self._cfg.save()
            return hidden

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

    class Search:
        """Main-window search keyword history (site-agnostic MRU)."""

        MAX_HISTORY = 35

        def __init__(self, cfg: "CgsConfig"):
            self._cfg = cfg

        @staticmethod
        def canonicalize(term: object) -> str:
            return " ".join(str(term or "").split())

        def get_history(self) -> list[str]:
            history = []
            for item in list(self._cfg.searchHistory.value or []):
                normalized = self.canonicalize(item)
                if normalized and normalized not in history:
                    history.append(normalized)
            return history

        def add_history(self, term: object) -> list[str]:
            canonical = self.canonicalize(term)
            if not canonical or canonical.lower().startswith("dc:"):
                return self.get_history()
            history = [item for item in self.get_history() if item != canonical]
            history.insert(0, canonical)
            self._cfg.searchHistory.value = history[: self.MAX_HISTORY]
            self._cfg.save()
            return self.get_history()


cgs_cfg = CgsConfig()
qconfig.load(_qconfig_path("qc.json"), cgs_cfg)
cgs_cfg.site_choices = CgsConfig.SiteChoices(cgs_cfg)
cgs_cfg.doh = CgsConfig.DoH(cgs_cfg)
cgs_cfg.search = CgsConfig.Search(cgs_cfg)


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
    LEGACY_DEFAULT_FAVORITE_GROUP = "Favorites"
    RESERVED_SEARCH_KEYS = frozenset({"History", LEGACY_DEFAULT_FAVORITE_GROUP, DEFAULT_FAVORITE_GROUP})

    searchHistory = ConfigItem("Search", "History", [], restart=False)
    searchExtra = ConfigItem("Search", "SearchExtra", [], restart=False)
    searchFavorites = ConfigItem("Search", "Favorites", {}, restart=False)
    searchFavoritesTranslateMap = ConfigItem("Search", "FavoritesTranslateMap", {}, restart=False)
    view_ratio = RangeConfigItem("Viewer", "ViewRatio", _default_danbooru_view_ratio(), RangeValidator(30, 85), restart=False)
    player = ConfigItem("Viewer", "Player", {}, restart=False)
    zoom_index = ConfigItem("Viewer", "ZoomIndex", 2, restart=False)
    # Tag 导出面板屏幕几何 [x, y, width, height]；空列表表示尚未记忆，走默认尺寸。
    tagExportPanelRect = ConfigItem("TagExportPanel", "Rect", [], restart=False)
    # Tag 导出面板 Comfy 生成设置：UNET 预设键、图内补全开关、重绘强度，随面板开合记忆。
    tagExportComfyUnet = ConfigItem("TagExportPanel", "ComfyUnet", "turbo", restart=False)
    tagExportWd14Enabled = ConfigItem("TagExportPanel", "Wd14Enabled", False, restart=False)
    tagExportDenoise = RangeConfigItem("TagExportPanel", "Denoise", 100, RangeValidator(10, 100), restart=False)
    # Fav-chip group → PromptDoc section (body/character/artist/series). Preference bag only;
    # never Search/Favorites content — see danbooru-global-push-pattern panel-pref boundary.
    tagExportFavGroupSections = ConfigItem("TagExportPanel", "FavGroupSections", {}, restart=False)

    @staticmethod
    def canonicalize_term(term: str) -> str:
        return " ".join((term or "").split())

    def _normalize_search_favorites_payload(self, payload: object) -> dict[str, list[str]]:
        if not isinstance(payload, dict):
            return {}

        normalized_payload = {}
        for raw_name, raw_tags in payload.items():
            group_name = self.canonicalize_term(str(raw_name))
            if not group_name or group_name == "History":
                continue
            if group_name == self.LEGACY_DEFAULT_FAVORITE_GROUP:
                group_name = self.DEFAULT_FAVORITE_GROUP
            if not isinstance(raw_tags, list):
                continue

            tags = []
            seen_tags = set()
            for raw_tag in raw_tags:
                tag = self.canonicalize_term(str(raw_tag))
                if not tag or tag in seen_tags:
                    continue
                seen_tags.add(tag)
                tags.append(tag)
            normalized_payload[group_name] = tags
        return normalized_payload

    def _normalize_search_favorites_value(self) -> dict[str, list[str]]:
        normalized_payload = self._normalize_search_favorites_payload(self.searchFavorites.value)
        if normalized_payload != self.searchFavorites.value:
            self.searchFavorites.value = normalized_payload
        return normalized_payload

    def _normalize_translate_map_payload(self, payload: object) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        normalized_payload: dict[str, str] = {}
        for raw_origin, raw_translated in payload.items():
            origin = self.canonicalize_term(str(raw_origin))
            translated = self.canonicalize_term(str(raw_translated))
            if not origin or not translated:
                continue
            normalized_payload[origin] = translated
        return normalized_payload

    def get_translate_map(self) -> dict[str, str]:
        normalized_payload = self._normalize_translate_map_payload(self.searchFavoritesTranslateMap.value)
        if normalized_payload != self.searchFavoritesTranslateMap.value:
            self.searchFavoritesTranslateMap.value = normalized_payload
        return dict(normalized_payload)

    def save_translate_map(self, payload: object) -> dict[str, str]:
        normalized_payload = self._normalize_translate_map_payload(payload)
        if normalized_payload != self.searchFavoritesTranslateMap.value:
            self.searchFavoritesTranslateMap.value = normalized_payload
            self.save()
        return dict(normalized_payload)

    def merge_translate_map(self, translations: object) -> dict[str, str]:
        """Background-safe merge: keep existing map entries, overwrite only provided keys."""
        merged = self.get_translate_map()
        if isinstance(translations, dict):
            for raw_origin, raw_translated in translations.items():
                origin = self.canonicalize_term(str(raw_origin))
                translated = self.canonicalize_term(str(raw_translated))
                if not origin or not translated:
                    continue
                merged[origin] = translated
        return self.save_translate_map(merged)

    def drop_translate_keys(self, tags: object) -> dict[str, str]:
        current_map = self.get_translate_map()
        if not current_map:
            return current_map
        drop_keys = {
            canonical
            for raw_tag in (tags or [])
            if (canonical := self.canonicalize_term(str(raw_tag)))
        }
        if not drop_keys:
            return current_map
        next_map = {
            origin: translated
            for origin, translated in current_map.items()
            if origin not in drop_keys
        }
        return self.save_translate_map(next_map)

    def display_tag(self, origin: str) -> str:
        canonical = self.canonicalize_term(origin)
        if not canonical:
            return ""
        return self.get_translate_map().get(canonical) or canonical

    def toDict(self, serialize=True):
        self._normalize_search_favorites_value()
        self.get_translate_map()
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

    def get_tag_export_panel_rect(self) -> list[int]:
        raw_rect = self.tagExportPanelRect.value
        if not isinstance(raw_rect, list) or len(raw_rect) < 4:
            return []
        try:
            return [int(value) for value in raw_rect[:4]]
        except (TypeError, ValueError):
            return []

    def save_tag_export_panel_rect(self, x: int, y: int, width: int, height: int) -> list[int]:
        rect = [int(x), int(y), int(width), int(height)]
        if rect != self.tagExportPanelRect.value:
            self.tagExportPanelRect.value = list(rect)
            self.save()
        return list(rect)

    def get_tag_export_comfy_unet(self) -> str:
        """返回存储的 UNET 预设键；预设键合法性由调用方按注册表校验。"""
        return str(self.tagExportComfyUnet.value or "")

    def save_tag_export_comfy_unet(self, preset_name: str) -> str:
        preset_name = str(preset_name or "")
        if preset_name != self.tagExportComfyUnet.value:
            self.tagExportComfyUnet.value = preset_name
            self.save()
        return preset_name

    def get_tag_export_wd14_enabled(self) -> bool:
        return bool(self.tagExportWd14Enabled.value)

    def save_tag_export_wd14_enabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if enabled != self.tagExportWd14Enabled.value:
            self.tagExportWd14Enabled.value = enabled
            self.save()
        return enabled

    def get_tag_export_denoise(self) -> int:
        return int(self.tagExportDenoise.value)

    def save_tag_export_denoise(self, value: int) -> int:
        value = max(10, min(100, int(value)))
        if value != self.tagExportDenoise.value:
            self.tagExportDenoise.value = value
            self.save()
        return value

    _TAG_EXPORT_FAV_SECTIONS = frozenset({"body", "character", "artist", "series"})

    def get_tag_export_fav_group_sections(self) -> dict[str, str]:
        """Panel preference bag: favorite group name → insertion section.

        Dumb read only — no favorites invalidate / no tab push.
        """
        raw_mapping = self.tagExportFavGroupSections.value
        if not isinstance(raw_mapping, dict):
            return {}
        normalized: dict[str, str] = {}
        for raw_group_name, raw_section in raw_mapping.items():
            group_name = str(raw_group_name or "").strip()
            section = str(raw_section or "").strip()
            if not group_name or section not in self._TAG_EXPORT_FAV_SECTIONS:
                continue
            normalized[group_name] = section
        return normalized

    def save_tag_export_fav_group_sections(self, mapping: dict[str, str] | None) -> dict[str, str]:
        """Persist fav-group section map under TagExportPanel; never touches Search/Favorites."""
        normalized: dict[str, str] = {}
        if isinstance(mapping, dict):
            for raw_group_name, raw_section in mapping.items():
                group_name = str(raw_group_name or "").strip()
                section = str(raw_section or "").strip()
                if not group_name or section not in self._TAG_EXPORT_FAV_SECTIONS:
                    continue
                normalized[group_name] = section
        if normalized != self.tagExportFavGroupSections.value:
            self.tagExportFavGroupSections.value = dict(normalized)
            self.save()
        return dict(normalized)

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
        def __init__(self, cfg: "DanbooruConfig"):
            self._cfg = cfg

        @property
        def payload(self) -> dict[str, list[str]]:
            normalized_payload = self._cfg._normalize_search_favorites_value()
            return {group_name: list(tags) for group_name, tags in normalized_payload.items()}

        def save_payload(self, payload: object) -> dict[str, list[str]]:
            normalized_payload = self._cfg._normalize_search_favorites_payload(payload)
            if normalized_payload != self._cfg.searchFavorites.value:
                self._cfg.searchFavorites.value = normalized_payload
            else:
                self._cfg.searchFavorites.value = {group_name: list(tags) for group_name, tags in normalized_payload.items()}
            self._cfg.save()
            return {group_name: list(tags) for group_name, tags in normalized_payload.items()}


danbooru_cfg = DanbooruConfig()
qconfig.load(_qconfig_path("qc_danbooru.json"), danbooru_cfg)
danbooru_cfg.fav = DanbooruConfig.Favorites(danbooru_cfg)
danbooru_cfg._normalize_search_favorites_value()
