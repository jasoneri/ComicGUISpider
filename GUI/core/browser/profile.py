from __future__ import annotations

from pathlib import Path

from PySide6.QtWebEngineCore import QWebEngineProfile

from utils.config import conf_dir


BROWSER_WINDOW_PROFILE_STORAGE_NAME = "cgs-browser-window"
_BROWSER_WINDOW_PROFILE_DIR_NAME = "browser_window_webengine"


def browser_window_profile_paths(*, base_dir: Path | None = None) -> tuple[Path, Path]:
    root_dir = Path(base_dir or conf_dir).joinpath(_BROWSER_WINDOW_PROFILE_DIR_NAME)
    storage_dir = root_dir.joinpath("storage")
    cache_dir = root_dir.joinpath("cache")
    storage_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir, cache_dir


def create_browser_window_profile(
    parent=None, *, base_dir: Path | None = None, persistent: bool = True,
) -> QWebEngineProfile:
    if not persistent:
        profile = QWebEngineProfile(parent)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        return profile
    storage_dir, cache_dir = browser_window_profile_paths(base_dir=base_dir)
    profile = QWebEngineProfile(BROWSER_WINDOW_PROFILE_STORAGE_NAME, parent)
    profile.setPersistentStoragePath(str(storage_dir))
    profile.setCachePath(str(cache_dir))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    return profile
