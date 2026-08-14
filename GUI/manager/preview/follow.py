from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    ListWidget,
    MessageBoxBase,
    PushButton,
    SubtitleLabel,
)

from utils.subscription import (
    FEATURE_KIND_ARTIST,
    FEATURE_KIND_TAG,
    FeatureEntry,
    SubscriptionStore,
)
from utils.subscription.check_state import BookCheckState, CheckStateStore, recalculate
from utils.subscription.library import LocalLibraryStore


class FollowFeatureDialog(MessageBoxBase):

    def __init__(self, seeds, parent):
        super().__init__(parent)
        self.title_label = SubtitleLabel("追踪作者 / 标签", self)
        self.viewLayout.addWidget(self.title_label)
        self.seed_list = ListWidget(self)
        for site, kind, value in seeds:
            item = QListWidgetItem(f"{kind}: {value}  ({site})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, (site, kind, value))
            self.seed_list.addItem(item)
        self.viewLayout.addWidget(self.seed_list)
        self.widget.setMinimumWidth(360)
        self.yesButton.setText("追踪所选")
        self.cancelButton.setText("取消")

    def checked_seeds(self) -> list[tuple[str, str, str]]:
        seeds = []
        for row in range(self.seed_list.count()):
            item = self.seed_list.item(row)
            if item.checkState() == Qt.Checked:
                seeds.append(item.data(Qt.UserRole))
        return seeds


class FollowController:
    """Post-library-add helpers: first-check toast + optional feature seeds."""

    def __init__(self, mgr, *, store=None, check_state_store=None):
        self.mgr = mgr
        self.gui = mgr.gui
        self.store = store or SubscriptionStore()
        self.check_state_store = check_state_store or CheckStateStore()
        self._pending_first_check = set()

    def reset(self):
        self._pending_first_check.clear()

    def after_library_added(self, book_key, book):
        if self._episode_chain_available(book):
            self._pending_first_check.add(str(book_key))
            self.mgr._active.start_fetch_episodes(str(book_key))
            return
        self._toast_followed_plain(book)

    def _episode_chain_available(self, book) -> bool:
        if self.mgr.is_manga:
            return True
        if self.mgr.is_fix:
            from GUI.manager.preview.fix import FixPreviewFeature
            return FixPreviewFeature.is_episode_card(book)
        return False

    def on_first_check_episodes(self, book_key, episodes, downloaded_count):
        if book_key not in self._pending_first_check:
            return
        self._pending_first_check.discard(book_key)
        book = self.mgr.books_cache.get(book_key)
        if book is None:
            return
        behind = max(0, len(episodes) - int(downloaded_count))
        title = str(getattr(book, "name", "") or "")
        suffix = f"落后 {behind} 章" if behind > 0 else "已是最新"
        self._show_success(f"已加入本地收藏：{title}，{suffix}")
        self._seed_check_state(book, found_new=behind > 0)

    def on_first_check_failed(self, book_key):
        if book_key not in self._pending_first_check:
            return
        self._pending_first_check.discard(book_key)
        book = self.mgr.books_cache.get(book_key)
        if book is not None:
            self._toast_followed_plain(book)

    def _toast_followed_plain(self, book):
        title = str(getattr(book, "name", "") or "")
        seeds = self._single_book_feature_seeds(book)
        if seeds:
            bar = self._show_success(f"已加入本地收藏：{title}", duration=6000)
            if bar is not None:
                enhance_btn = PushButton("追踪作者/标签…", bar)
                enhance_btn.clicked.connect(lambda _checked=False, b=book: self.open_feature_dialog(b))
                bar.addWidget(enhance_btn)
        else:
            self._show_success(f"已加入本地收藏：{title}")

    def _seed_check_state(self, book, *, found_new):
        site = LocalLibraryStore.book_site(book, site_index=self.mgr.site_index)
        url = LocalLibraryStore.book_unique_url(book)
        key = f"{site}:{url}"
        states = self.check_state_store.load()
        prior = states.get(key) or BookCheckState(key=key)
        states[key] = recalculate(prior, found_new=found_new, now=datetime.now(timezone.utc))
        self.check_state_store.save(states)

    def open_feature_dialog(self, book):
        seeds = self._single_book_feature_seeds(book)
        if not seeds:
            self._show_info("该书没有可追踪的作者/标签")
            return
        dialog = FollowFeatureDialog(seeds, self._toast_parent().window())
        if not dialog.exec():
            return
        checked = dialog.checked_seeds()
        if not checked:
            return
        cfg = self.store.load()
        existing = {(feature.site, feature.kind, feature.value) for feature in cfg.features}
        added = 0
        for site, kind, value in checked:
            if (site, kind, value) in existing:
                continue
            entry = FeatureEntry(site=site, kind=kind, value=value, enabled=True)
            entry.validate()
            cfg.features.append(entry)
            existing.add((site, kind, value))
            added += 1
        if added:
            self.store.save(cfg)
        self._show_success(f"已追踪 {added} 个作者/标签特征")

    @staticmethod
    def _single_book_feature_seeds(book) -> list[tuple[str, str, str]]:
        if not hasattr(book, "id_and_md5"):
            return []
        site = str(getattr(book, "source", "") or "").strip()
        seeds: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        artist = str(getattr(book, "artist", "") or "").strip()
        if artist:
            seed = (site, FEATURE_KIND_ARTIST, artist)
            seen.add(seed)
            seeds.append(seed)
        for tag in getattr(book, "tags", None) or []:
            tag_value = str(tag or "").strip()
            if not tag_value:
                continue
            seed = (site, FEATURE_KIND_TAG, tag_value)
            if seed not in seen:
                seen.add(seed)
                seeds.append(seed)
        return seeds

    def _toast_parent(self):
        browser = getattr(self.gui, "BrowserWindow", None)
        return browser.view if browser else self.gui

    def _show_success(self, message, *, duration=3500):
        return InfoBar.success(
            title="", content=message, orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=duration, parent=self._toast_parent(),
        )

    def _show_info(self, message):
        return InfoBar.info(
            title="", content=message, orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=2500, parent=self._toast_parent(),
        )
