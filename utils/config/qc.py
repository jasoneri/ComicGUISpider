import json
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
        qconfig.save()
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
    RESERVED_SEARCH_KEYS = frozenset({"History", "Favorites"})

    searchHistory = ConfigItem("Search", "History", [], restart=False)
    searchFavorites = ConfigItem("Search", "Favorites", [], restart=False)
    view_ratio = RangeConfigItem("Viewer", "ViewRatio", _default_danbooru_view_ratio(), RangeValidator(30, 75), restart=False)

    @staticmethod
    def canonicalize_term(term: str) -> str:
        return " ".join((term or "").split())

    def _load_payload(self):
        try:
            with open(self.file, encoding="utf-8") as fp:
                return json.load(fp)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Danbooru 配置文件损坏: {self.file}") from exc

    def _write_payload(self, payload):
        payload.update({key: value for key, value in super().toDict().items() if key != "Search"})
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=4)

    def save(self):
        payload = self._load_payload()
        search = payload.get("Search")
        if not isinstance(search, dict):
            search = {}
        search["History"] = self.get_history()
        search["Favorites"] = sorted(self.get_favorites())
        payload["Search"] = search
        self._write_payload(payload)

    def get_grouped_favorites(self) -> list[tuple[str, list[str]]]:
        search = self._load_payload().get("Search")
        if not isinstance(search, dict):
            return []
        groups: list[tuple[str, list[str]]] = []
        for raw_name, raw_tags in search.items():
            group_name = self.canonicalize_term(str(raw_name))
            if not group_name or group_name in self.RESERVED_SEARCH_KEYS or not isinstance(raw_tags, list):
                continue
            tags = []
            for raw_tag in raw_tags:
                tag = self.canonicalize_term(str(raw_tag))
                if tag and tag not in tags:
                    tags.append(tag)
            groups.append((group_name, tags))
        return groups

    def save_grouped_favorites(self, default_tags: list[str], groups: list[tuple[str, list[str]]]):
        payload = self._load_payload()
        self.searchFavorites.value = sorted({
            normalized
            for tag in default_tags
            if (normalized := self.canonicalize_term(tag))
        })
        payload["Search"] = {
            "History": self.get_history(),
            "Favorites": list(self.searchFavorites.value),
            **{
                self.canonicalize_term(raw_name): list(dict.fromkeys(
                    normalized for raw_tag in raw_tags
                    if (normalized := self.canonicalize_term(str(raw_tag)))
                )) for raw_name, raw_tags in groups
            },
        }
        self._write_payload(payload)

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
        return set(self.searchFavorites.value)

    def is_favorite(self, term: str) -> bool:
        return self.canonicalize_term(term) in self.get_favorites()

    def add_favorite(self, term: str):
        canonical = self.canonicalize_term(term)
        if not canonical:
            return self.get_favorites()
        favorites = self.get_favorites()
        favorites.add(canonical)
        self.searchFavorites.value = sorted(favorites)
        self.save()
        return self.get_favorites()

    def remove_favorite(self, term: str):
        canonical = self.canonicalize_term(term)
        favorites = self.get_favorites()
        favorites.discard(canonical)
        self.searchFavorites.value = sorted(favorites)
        self.save()
        return self.get_favorites()

    def toggle_favorite(self, term: str) -> bool:
        canonical = self.canonicalize_term(term)
        if not canonical:
            return False
        favorites = self.get_favorites()
        is_favorited = canonical not in favorites
        if is_favorited:
            favorites.add(canonical)
        else:
            favorites.discard(canonical)
        self.searchFavorites.value = sorted(favorites)
        self.save()
        return is_favorited


danbooru_cfg = DanbooruConfig()
qconfig.load(_qconfig_path("qc_danbooru.json"), danbooru_cfg)
