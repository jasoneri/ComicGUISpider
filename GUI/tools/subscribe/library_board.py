# -*- coding: utf-8 -*-
"""Library waterfall board — cards map, filter paint, dispose lifecycle."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, FlowLayout, ScrollArea

from utils.subscription.library import LocalLibraryStore

from .card import SubscribeCard
from .common import subscribe_site_indexes
from .cover_session import CoverSession

if TYPE_CHECKING:
    from .window import SubscribeWindow


class LibraryBoard(QWidget):
    """Main pane: empty state + FlowLayout cards + status chrome slots stay on host header."""

    def __init__(
        self,
        host: "SubscribeWindow",
        *,
        cover_session: CoverSession,
        on_card_selected: Callable[[str], None],
        on_card_delete_requested: Callable[[str], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._host = host
        self.cover_session = cover_session
        self._on_card_selected = on_card_selected
        self._on_card_delete_requested = on_card_delete_requested
        self.cards: list[SubscribeCard] = []
        self.cards_by_key: dict[str, SubscribeCard] = {}
        self.filter_site_index: int | None = None
        self.setObjectName("SubscribeMainPane")
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        self.empty_label = BodyLabel("暂无追更书目\n在预览勾选后点「加入订阅」", self)
        self.empty_label.setObjectName("SubscribeEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        main_layout.addWidget(self.empty_label)

        self.scroll = ScrollArea(self)
        self.scroll.setObjectName("SubscribeScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_host = QWidget(self.scroll)
        self.cards_host.setObjectName("SubscribeCardsHost")
        self.cards_layout = FlowLayout(self.cards_host, needAni=False)
        self.cards_layout.setContentsMargins(2, 2, 10, 18)
        self.cards_layout.setHorizontalSpacing(12)
        self.cards_layout.setVerticalSpacing(12)
        self.scroll.setWidget(self.cards_host)
        main_layout.addWidget(self.scroll, 1)

        self.status_bar = QWidget(self)
        self.status_bar.setObjectName("SubscribeStatusBar")
        self.status_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout = QVBoxLayout(self.status_bar)
        # placeholder — host replaces with real status strip after construct
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)
        main_layout.addWidget(self.status_bar, 0)

    def attach_status_bar(self, status_bar: QWidget) -> None:
        layout = self.layout()
        old = self.status_bar
        index = layout.indexOf(old)
        layout.removeWidget(old)
        old.deleteLater()
        self.status_bar = status_bar
        layout.insertWidget(index, status_bar, 0)

    def dispose_card_widget(self, card: SubscribeCard) -> None:
        if card is None:
            return
        card.hide()
        card.set_card_selected(False)
        self.cards_layout.removeWidget(card)
        card.deleteLater()

    def clear_cards(self) -> None:
        self.cover_session.invalidate_covers()
        cards = list(self.cards)
        self.cards.clear()
        self.cards_by_key.clear()
        for card in cards:
            self.dispose_card_widget(card)
        while self.cards_layout.count():
            leftover = self.cards_layout.takeAt(0)
            if leftover is None:
                continue
            leftover.hide()
            leftover.deleteLater()

    def remove_card(self, card_key: str) -> SubscribeCard | None:
        key = str(card_key or "")
        card = self.cards_by_key.get(key)
        if card is None:
            return None
        self.cover_session.forget_card(key)
        if card in self.cards:
            self.cards.remove(card)
        self.cards_by_key.pop(key, None)
        self.dispose_card_widget(card)
        return card

    def set_selection_visual(self, card_key: str | None) -> None:
        key = str(card_key or "")
        for other_key, card in self.cards_by_key.items():
            card.set_card_selected(bool(key) and other_key == key)

    def refresh(
        self,
        *,
        library: LocalLibraryStore,
        selected_card_key: str | None,
        count_label: CaptionLabel,
    ) -> str | None:
        """Rebuild cards from library. Returns selected key still present, else None."""
        self.clear_cards()
        allowed = subscribe_site_indexes()
        filter_site = self.filter_site_index
        rows = []
        for site_index, book in library.iter_all_books():
            site_index = int(site_index)
            if site_index not in allowed:
                continue
            if filter_site is not None and site_index != int(filter_site):
                continue
            rows.append((site_index, book))
        total_allowed = sum(
            1
            for site_index, _book in library.iter_all_books()
            if int(site_index) in allowed
        )
        count = len(rows)
        if filter_site is None or count == total_allowed:
            count_label.setText(f"{count} 部")
        else:
            count_label.setText(f"{count}/{total_allowed} 部")
        if not rows:
            if filter_site is None:
                self.empty_label.setText("暂无追更书目\n在预览勾选后点「加入订阅」")
            else:
                self.empty_label.setText("当前站点筛选下无书目\n可切换站点或选「全部」")
            self.empty_label.show()
            self.scroll.hide()
            return None
        self.empty_label.hide()
        self.scroll.show()
        for site_index, book in rows:
            card_key = f"{site_index}:{LocalLibraryStore.book_unique_url(book) or id(book)}"
            card = SubscribeCard(self.cards_host, book, site_index=site_index, card_key=card_key)
            card.selected.connect(self._on_card_selected)
            card.delete_requested.connect(self._on_card_delete_requested)
            self.cards.append(card)
            self.cards_by_key[card_key] = card
            self.cards_layout.addWidget(card)
            self.cover_session.apply_cover_for_card(card)
        if selected_card_key and selected_card_key in self.cards_by_key:
            return selected_card_key
        return None

    def show_empty_after_delete(self, count_label: CaptionLabel) -> None:
        if not self.cards:
            self.empty_label.show()
            self.scroll.hide()
            count_label.setText("0 部")
        else:
            count_label.setText(f"{len(self.cards)} 部")
