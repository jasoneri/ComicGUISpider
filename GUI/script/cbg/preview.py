"""CBG 预览加载策略层

职责边界：
- PreviewLoader: 后台线程中解码单个图片
- PreviewScheduler: 管理加载队列、可见性检测、线程调度
- 不直接操作 GUI 组件，通过回调通知视图层
"""
from __future__ import annotations

import typing as t
from pathlib import Path

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QRect, QRunnable, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QScrollArea

if t.TYPE_CHECKING:
    from GUI.script.cbg import CbgCardWidget


class PreviewLoader(QRunnable):
    """后台线程中解码单个预览图片"""

    def __init__(self, card: CbgCardWidget, target_size: QSize):
        super().__init__()
        self.card = card
        self.path = card.path
        self.target_size = target_size
        self.setAutoDelete(True)

    def run(self) -> None:
        reader = QImageReader(str(self.path))
        if not reader.canRead():
            return
        reader.setAutoTransform(True)
        source_size = reader.size()
        if source_size.isValid():
            reader.setScaledSize(source_size.scaled(self.target_size, Qt.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        QMetaObject.invokeMethod(
            self.card, "_set_preview_from_loader", Qt.QueuedConnection, Q_ARG(QPixmap, pixmap)
        )


class PreviewScheduler(QObject):
    """预览加载调度器

    职责：
    - 管理待加载队列
    - 检测卡片可见性
    - 调度后台线程加载
    - 限制并发加载数量
    """

    def __init__(self, scroll_area: QScrollArea, max_concurrent: int = 20):
        super().__init__()
        self.scroll_area = scroll_area
        self.max_concurrent = max_concurrent
        self.pending_cards: list[CbgCardWidget] = []
        self.loading_cards: set[Path] = set()
        self.loaded_cards: set[Path] = set()
        self.thread_pool = QThreadPool.globalInstance()

    def register_card(self, card: CbgCardWidget) -> None:
        """注册卡片到待加载队列"""
        if card.path in self.loaded_cards or card.path in self.loading_cards:
            return
        self.pending_cards.append(card)

    def load_visible_cards(self) -> None:
        """加载当前可见的卡片预览"""
        if not self.pending_cards:
            return

        viewport_rect = self.scroll_area.viewport().rect()
        loaded_count = 0

        remaining_cards = []
        for card in self.pending_cards:
            if loaded_count >= self.max_concurrent:
                remaining_cards.append(card)
                continue

            if card.path in self.loading_cards or card.path in self.loaded_cards:
                continue

            if self._is_card_visible(card, viewport_rect):
                self._schedule_load(card)
                loaded_count += 1
            else:
                remaining_cards.append(card)

        self.pending_cards = remaining_cards

    def _is_card_visible(self, card: CbgCardWidget, viewport_rect: QRect) -> bool:
        """判断卡片是否在可见区域"""
        if not card.isVisible():
            return False
        card_pos = card.mapTo(self.scroll_area.viewport(), card.rect().topLeft())
        card_rect = QRect(card_pos, card.size())
        return viewport_rect.intersects(card_rect)

    def _schedule_load(self, card: CbgCardWidget) -> None:
        """调度后台线程加载预览"""
        self.loading_cards.add(card.path)
        loader = PreviewLoader(card, card._preview_target_size())
        loader.setAutoDelete(True)
        self.thread_pool.start(loader)

    def mark_loaded(self, path: Path) -> None:
        """标记卡片已加载完成"""
        self.loading_cards.discard(path)
        self.loaded_cards.add(path)

    def clear(self) -> None:
        """清空所有状态"""
        self.pending_cards.clear()
        self.loading_cards.clear()
        self.loaded_cards.clear()
