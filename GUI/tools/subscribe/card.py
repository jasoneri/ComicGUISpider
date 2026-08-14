# -*- coding: utf-8 -*-
"""Subscribe waterfall card (ProgressClass ImageLabel cover + mangaCard DL status)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel, FluentIcon as FIF, ImageLabel, ToolButton

from utils import curr_os
from utils.core import TasksObj
from utils.share.preview_gen import resolve_local_cover_path
from utils.subscription.library import LocalLibraryStore
from variables import SPIDERS

from .common import (
    CARD_ACTION_ICON,
    CARD_ACTION_SIZE,
    CARD_CONTENT_MARGIN,
    CARD_OVERLAY_MARGIN,
    CARD_OVERLAY_SPACING,
    CARD_PREVIEW_BASE_HEIGHT,
    CARD_PREVIEW_CONTENT_WIDTH,
    CARD_PREVIEW_MAX_HEIGHT,
    OVERLAY_ICON_COLORS,
    resolve_local_path,
)


class SubscribeCoverLabel(ImageLabel):
    """qfluent ImageLabel API with scroll-safe paint.

    Upstream ImageLabel.paintEvent Smooth-scales the full source on every paint
    (severe lag with dozens of covers). We bake display-size pixels once.

    Critical: never use WA_OpaquePaintEvent without always filling the rect —
    that leaves uncleared scroll trails (stacked ghost cards in screenshots).
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._baked_pixmap = QPixmap()
        self._placeholder_color = QColor(39, 39, 42, 40)

    def setImage(self, image=None) -> None:
        """Keep ImageLabel.image for API compat; display via set_display_cover."""
        if image is None:
            self.image = QImage()
            self._baked_pixmap = QPixmap()
            self.update()
            return
        if isinstance(image, QPixmap):
            self.image = image.toImage() if not image.isNull() else QImage()
        elif isinstance(image, QImage):
            self.image = image
        elif isinstance(image, str):
            self.image = QImage(image)
        else:
            self.image = QImage()
        self._baked_pixmap = QPixmap()
        self.update()

    def set_display_cover(self, source: QPixmap | QImage, logical_size: QSize) -> bool:
        """Bake once to logical_size; paint path only draws the baked pixmap."""
        if source is None:
            return False
        if isinstance(source, QPixmap):
            if source.isNull():
                return False
            source_image = source.toImage()
        else:
            source_image = source
            if source_image is None or source_image.isNull():
                return False
        logical_width = max(1, int(logical_size.width()))
        logical_height = max(1, int(logical_size.height()))
        # Bake at logical size (device-pixel handled by Qt when drawing pixmap).
        baked = QPixmap.fromImage(
            source_image.scaled(
                logical_width,
                logical_height,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        if baked.isNull():
            return False
        self.image = baked.toImage()
        self._baked_pixmap = baked
        self.setFixedSize(logical_width, logical_height)
        self.update()
        return True

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        rect = QRectF(self.rect())
        radius = float(getattr(self, "topLeftRadius", 0) or 0)
        # Always fill first — prevents scroll trails / black holes.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._placeholder_color)
        if radius > 0.5:
            painter.drawRoundedRect(rect, radius, radius)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(rect, radius, radius)
            painter.setClipPath(clip_path)
        else:
            painter.drawRect(rect)
        if not self._baked_pixmap.isNull():
            painter.drawPixmap(self.rect(), self._baked_pixmap)


class SubscribeCard(QFrame):
    """Waterfall card: ImageLabel-family cover (ProgressClass size math) + manga DL status."""

    selected = Signal(str)  # card_key — SidePanel binds conf row to this card
    # Unsubscribe + remove local library favorite (ComfyJobCard del pattern).
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget, book, *, site_index: int, card_key: str):
        super().__init__(parent)
        self.setObjectName("SubscribeCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Do NOT set WA_OpaquePaintEvent: without a full-rect fill every paint,
        # Qt leaves previous scroll frames → stacked ghost cards (user screenshot).
        self.book = book
        self.site_index = int(site_index)
        self.card_key = str(card_key)
        self._selected = False
        self._local_path = resolve_local_path(book)
        self._site_url = str(
            getattr(book, "preview_url", None) or getattr(book, "url", None) or ""
        ).strip()
        self._cover_source = None
        self._preview_size = QSize(CARD_PREVIEW_CONTENT_WIDTH, CARD_PREVIEW_BASE_HEIGHT)
        self._subscribe_enabled = LocalLibraryStore.book_subscribe_enabled(book)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            CARD_CONTENT_MARGIN,
            CARD_CONTENT_MARGIN,
            CARD_CONTENT_MARGIN,
            CARD_CONTENT_MARGIN,
        )
        root.setSpacing(4)

        # ProgressClass sizing + ImageLabel family; paint is bake-once blit (see SubscribeCoverLabel).
        self.cover_label = SubscribeCoverLabel(self)
        self.cover_label.setObjectName("SubscribeCardCover")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setBorderRadius(9, 9, 9, 9)
        self.cover_label.setFixedSize(self._preview_size)

        self.folder_btn = ToolButton(self.cover_label)
        self.folder_btn.setObjectName("SubscribeCardFolderBtn")
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.setFixedSize(QSize(*CARD_ACTION_SIZE))
        self.folder_btn.setIconSize(QSize(*CARD_ACTION_ICON))
        self.folder_btn.setEnabled(bool(self._local_path))
        self.folder_btn.setToolTip("打开本地目录" if self._local_path else "本地目录不可用")
        self.folder_btn.clicked.connect(self._open_folder)

        self.link_btn = ToolButton(self.cover_label)
        self.link_btn.setObjectName("SubscribeCardLinkBtn")
        self.link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_btn.setFixedSize(QSize(*CARD_ACTION_SIZE))
        self.link_btn.setIconSize(QSize(*CARD_ACTION_ICON))
        self.link_btn.setEnabled(bool(self._site_url))
        self.link_btn.setToolTip("打开源站" if self._site_url else "源站链接不可用")
        self.link_btn.clicked.connect(self._open_site)

        # ComfyJobCard delBtn: red DELETE icon, top-right chip row (rightmost).
        self.del_btn = ToolButton(self.cover_label)
        self.del_btn.setObjectName("SubscribeCardDelBtn")
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setFixedSize(QSize(*CARD_ACTION_SIZE))
        self.del_btn.setIconSize(QSize(*CARD_ACTION_ICON))
        self.del_btn.setToolTip("取消订阅并移除本地收藏")
        self.del_btn.clicked.connect(self._on_delete_clicked)

        self._apply_action_chrome()

        title = LocalLibraryStore.book_title(book) or "-"
        self._title_full = str(title)
        self.title_label = BodyLabel(self._title_full, self)
        self.title_label.setObjectName("SubscribeCardTitle")
        self.title_label.setWordWrap(False)
        self.title_label.setToolTip(self._title_full)
        self.title_label.setFixedWidth(CARD_PREVIEW_CONTENT_WIDTH)
        self.title_label.setFixedHeight(22)
        self.title_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._apply_title_elide()

        # manga .book-card-body: title + optional meta only — no conf filler row.
        meta_bits = []
        if last_chapter := getattr(book, "last_chapter_name", None):
            meta_bits.append(str(last_chapter))
        if updated := getattr(book, "datetime_updated", None):
            meta_bits.append(str(updated))
        meta_text = " · ".join(bit for bit in meta_bits if str(bit).strip())
        self.meta_label = CaptionLabel(meta_text, self)
        self.meta_label.setObjectName("SubscribeCardMeta")
        self.meta_label.setWordWrap(False)
        self.meta_label.setFixedWidth(CARD_PREVIEW_CONTENT_WIDTH)
        self.meta_label.setVisible(bool(meta_text))

        # manga .book-card-status:empty { display:none } — only when DL scan hits.
        self._latest_ep_name = str(getattr(book, "last_chapter_name", "") or "").strip()
        self._dl_max = ""
        self.status_row = QWidget(self)
        self.status_row.setObjectName("SubscribeCardStatusRow")
        status_layout = QHBoxLayout(self.status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)
        self.dl_badge = QLabel("", self.status_row)
        self.dl_badge.setObjectName("SubscribeCardBadgeDl")
        self.dl_badge.setVisible(False)
        self.latest_badge = QLabel("", self.status_row)
        self.latest_badge.setObjectName("SubscribeCardBadgeLatest")
        self.latest_badge.setProperty("updateState", "idle")
        self.latest_badge.setVisible(False)
        status_layout.addWidget(self.dl_badge, 0)
        status_layout.addWidget(self.latest_badge, 1)
        status_layout.addStretch(0)
        self.status_row.setFixedWidth(CARD_PREVIEW_CONTENT_WIDTH)
        self.status_row.hide()

        root.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        root.addWidget(self.title_label)
        root.addWidget(self.meta_label)
        root.addWidget(self.status_row)
        self._apply_enabled_visual()
        self._sync_card_geometry()

    def _apply_action_chrome(self) -> None:
        """Solid icon tints only; chip chrome is SubscribeWindow theme QSS by objectName."""
        self.folder_btn.setIcon(FIF.FOLDER.icon(color=QColor(OVERLAY_ICON_COLORS["folder"])))
        self.link_btn.setIcon(FIF.LINK.icon(color=QColor(OVERLAY_ICON_COLORS["link"])))
        self.del_btn.setIcon(FIF.DELETE.icon(color=QColor(OVERLAY_ICON_COLORS["del"])))

    def _apply_title_elide(self) -> None:
        """Keep waterfall title one line; long series names must not grow the card."""
        full = str(getattr(self, "_title_full", "") or self.title_label.text() or "-")
        self.title_label.setToolTip(full)
        elided = self.title_label.fontMetrics().elidedText(
            full,
            Qt.TextElideMode.ElideRight,
            max(40, CARD_PREVIEW_CONTENT_WIDTH - 2),
        )
        self.title_label.setText(elided)

    def sizeHint(self) -> QSize:
        # Tight body like manga book-card: cover + title + optional meta + optional DL row.
        body_height = 22  # title line
        if not self.meta_label.isHidden() and str(self.meta_label.text() or "").strip():
            body_height += 16
        if not self.status_row.isHidden():
            body_height += 22
        return QSize(
            (CARD_CONTENT_MARGIN * 2) + self._preview_size.width(),
            (CARD_CONTENT_MARGIN * 2) + self._preview_size.height() + 4 + body_height,
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _sync_card_geometry(self) -> None:
        """Size title/meta/status to current cover width; fix outer card."""
        cover_width = max(1, self.cover_label.width())
        cover_height = max(1, self.cover_label.height())
        self._preview_size = QSize(cover_width, cover_height)
        self.title_label.setFixedWidth(cover_width)
        self.meta_label.setFixedWidth(cover_width)
        self.status_row.setFixedWidth(cover_width)
        self.setFixedSize(self.sizeHint())
        self._relocate_overlays()
        self.adjustSize()
        self.updateGeometry()

    def is_card_selected(self) -> bool:
        return bool(self._selected)

    def set_card_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def subscribe_enabled(self) -> bool:
        return bool(self._subscribe_enabled)

    def apply_subscribe_conf(self, *, enabled: bool | None = None) -> None:
        """Update in-memory book after library persist (schedule lives in SidePanel)."""
        if enabled is not None:
            self._subscribe_enabled = bool(enabled)
            setattr(self.book, "subscribe_enabled", self._subscribe_enabled)
        self._apply_enabled_visual()

    def _apply_enabled_visual(self) -> None:
        self.setProperty("paused", "false" if self._subscribe_enabled else "true")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self.childAt(event.position().toPoint())
            walk = hit
            while walk is not None and walk is not self:
                if isinstance(walk, QAbstractButton):
                    super().mousePressEvent(event)
                    return
                walk = walk.parentWidget()
            self.selected.emit(self.card_key)
        super().mousePressEvent(event)

    def apply_dl_scan_badge(self, *, dl_max: str, latest_ep_name: str | None = None) -> None:
        """Mirror preview_episode.js renderCardBadgeDl / renderCardBadgeLatest."""
        self._dl_max = str(dl_max or "").strip()
        if latest_ep_name is not None:
            self._latest_ep_name = str(latest_ep_name or "").strip()
        if not self._dl_max:
            self.dl_badge.clear()
            self.dl_badge.setVisible(False)
            self.latest_badge.clear()
            self.latest_badge.setVisible(False)
            self.status_row.hide()
            self._sync_card_geometry()
            return

        dl_text = f"DL: {self._dl_max}"
        self.dl_badge.setText(dl_text)
        self.dl_badge.setToolTip(dl_text)
        self.dl_badge.setVisible(True)

        latest = self._latest_ep_name
        if latest:
            # Same-ish comparison as manga status: local max vs remote name.
            if latest in self._dl_max or self._dl_max in latest:
                self.latest_badge.setText("✓")
                self.latest_badge.setProperty("updateState", "ok")
            else:
                self.latest_badge.setText(f"NEW: {latest}")
                self.latest_badge.setProperty("updateState", "new")
            self.latest_badge.setVisible(True)
            self.latest_badge.style().unpolish(self.latest_badge)
            self.latest_badge.style().polish(self.latest_badge)
        else:
            self.latest_badge.clear()
            self.latest_badge.setVisible(False)
        self.status_row.show()
        self._sync_card_geometry()

    def _relocate_overlays(self) -> None:
        # ComfyJobCard order: … folder, link, del (del rightmost).
        preview_size = self.cover_label.size()
        top_y = CARD_OVERLAY_MARGIN
        del_x = preview_size.width() - CARD_OVERLAY_MARGIN - self.del_btn.width()
        self.del_btn.move(del_x, top_y)
        link_x = del_x - self.link_btn.width() - CARD_OVERLAY_SPACING
        self.link_btn.move(link_x, top_y)
        folder_x = link_x - self.folder_btn.width() - CARD_OVERLAY_SPACING
        self.folder_btn.move(folder_x, top_y)
        self.folder_btn.raise_()
        self.link_btn.raise_()
        self.del_btn.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relocate_overlays()

    def _apply_cover_pixmap(self, pixmap: QPixmap) -> bool:
        """ProgressClass size math + one-time bake into SubscribeCoverLabel.

        Ratio → logical setFixedSize (like ProgressClass COVER_HEIGHT path).
        Pixels are baked once at display size; scroll paint only blits
        (upstream ImageLabel Smooth-scales every paint — that caused ghosting).
        """
        if pixmap is None or pixmap.isNull() or pixmap.height() <= 0 or pixmap.width() <= 0:
            return False
        # Orphaned cards must not become top-level paint targets.
        if self.isWindow() or self.parentWidget() is None:
            return False

        source_width = int(pixmap.width())
        source_height = int(pixmap.height())
        fitted = QSize(source_width, source_height).scaled(
            QSize(CARD_PREVIEW_CONTENT_WIDTH, CARD_PREVIEW_MAX_HEIGHT),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        display_width = max(1, int(fitted.width()))
        display_height = max(1, int(fitted.height()))
        display_size = QSize(display_width, display_height)

        if not self.cover_label.set_display_cover(pixmap, display_size):
            return False
        self._preview_size = display_size
        self._sync_card_geometry()
        return True

    def set_cover_pixmap(self, pixmap: QPixmap, *, source: str = "preview") -> bool:
        if not self._apply_cover_pixmap(pixmap):
            return False
        self._cover_source = source
        return True

    def try_load_local_cover(self) -> bool:
        local_cover = resolve_local_cover_path(self.book)
        if local_cover is not None:
            pixmap = QPixmap(str(local_cover))
            if self.set_cover_pixmap(pixmap, source="local"):
                return True
        cover = str(getattr(self.book, "img_preview", "") or "").strip()
        if not cover:
            return False
        if cover.startswith("file:"):
            path = cover.replace("file:///", "").replace("file://", "")
            pixmap = QPixmap(path)
            return self.set_cover_pixmap(pixmap, source="local")
        if cover.startswith(":/") or Path(cover).exists():
            pixmap = QPixmap(cover)
            return self.set_cover_pixmap(pixmap, source="local")
        return False

    def cover_url(self) -> str:
        return str(getattr(self.book, "img_preview", "") or "").strip()

    def needs_remote_cover(self) -> bool:
        if self._cover_source == "local":
            return False
        cover = self.cover_url()
        if cover.startswith("http://") or cover.startswith("https://"):
            return True
        # Empty cover still hydratable when book page URL is known (jestful legacy rows).
        return bool(self._site_url.startswith(("http://", "https://")))

    def to_cover_tasks_obj(self) -> TasksObj:
        cover = self.cover_url()
        title = LocalLibraryStore.book_title(self.book) or self.card_key
        return TasksObj(
            self.card_key,
            title,
            1,
            self._site_url or None,
            None,
            cover or None,
            source=str(SPIDERS.get(self.site_index) or ""),
        )

    def _open_folder(self) -> None:
        if self._local_path and Path(self._local_path).exists():
            curr_os.open_folder(self._local_path)

    def _open_site(self) -> None:
        if self._site_url:
            QDesktopServices.openUrl(QUrl(self._site_url))

    def _on_delete_clicked(self) -> None:
        self.delete_requested.emit(self.card_key)
