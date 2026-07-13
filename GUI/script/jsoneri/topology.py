from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QWidget

from .dashboard import TopologyNodeViewModel


class JsoneriPalacesTopologyCanvas(QWidget):
    service_selected = Signal(str)
    service_open_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: tuple[TopologyNodeViewModel, ...] = ()
        self._selected_service_name = ""
        self._state_message = ""
        self._node_rects: dict[str, QRectF] = {}
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.setObjectName("JsoneriPalacesTopologyCanvas")

    def set_view_model(self, nodes: tuple[TopologyNodeViewModel, ...], *, selected_service_name: str, state_message: str) -> None:
        self._nodes = nodes
        self._selected_service_name = selected_service_name
        self._state_message = state_message
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._node_rects = {}
        canvas = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        self._paint_background(painter, canvas)
        if not self._nodes:
            self._paint_empty_state(painter, canvas)
            return
        node_rects = self._layout_nodes(canvas, len(self._nodes))
        self._paint_links(painter, canvas, node_rects)
        for node, rect in zip(self._nodes, node_rects):
            self._node_rects[node.service_name] = rect
            self._paint_node(painter, node, rect, node.service_name == self._selected_service_name)

    def mousePressEvent(self, event) -> None:
        service_name = self._service_at(event.position())
        if service_name:
            self.service_selected.emit(service_name)
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        service_name = self._service_at(event.position())
        if service_name:
            self.service_open_requested.emit(service_name)
            return
        super().mouseDoubleClickEvent(event)

    def _paint_background(self, painter: QPainter, canvas: QRectF) -> None:
        border = self.palette().color(QPalette.ColorRole.Mid)
        border.setAlpha(72)
        fill = self.palette().color(QPalette.ColorRole.AlternateBase)
        fill.setAlpha(36)
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(canvas, 8, 8)

    def _paint_empty_state(self, painter: QPainter, canvas: QRectF) -> None:
        painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
        painter.drawText(canvas, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._state_message or "No services to display.")

    def _layout_nodes(self, canvas: QRectF, count: int) -> list[QRectF]:
        columns = max(1, min(3, math.ceil(math.sqrt(count))))
        rows = math.ceil(count / columns)
        gap = 16
        cell_width = max(170.0, (canvas.width() - gap * (columns + 1)) / columns)
        cell_height = max(110.0, (canvas.height() - gap * (rows + 1)) / rows)
        node_width = min(220.0, cell_width)
        node_height = min(118.0, cell_height)
        rects = []
        for index in range(count):
            row = index // columns
            column = index % columns
            cell_x = canvas.left() + gap + column * (cell_width + gap)
            cell_y = canvas.top() + gap + row * (cell_height + gap)
            rects.append(QRectF(cell_x + (cell_width - node_width) / 2, cell_y + (cell_height - node_height) / 2, node_width, node_height))
        return rects

    def _paint_links(self, painter: QPainter, canvas: QRectF, node_rects: list[QRectF]) -> None:
        if len(node_rects) < 2:
            return
        center = QPointF(canvas.center().x(), canvas.top() + 18)
        link_color = self.palette().color(QPalette.ColorRole.Mid)
        link_color.setAlpha(54)
        painter.setPen(QPen(link_color, 1))
        for rect in node_rects:
            path = QPainterPath(center)
            path.cubicTo(center.x(), rect.center().y(), rect.center().x(), center.y(), rect.center().x(), rect.top())
            painter.drawPath(path)

    def _paint_node(self, painter: QPainter, node: TopologyNodeViewModel, rect: QRectF, selected: bool) -> None:
        border_color = QColor(node.color)
        fill_color = self.palette().color(QPalette.ColorRole.Base)
        fill_color.setAlpha(232)
        painter.setPen(QPen(border_color, 2 if selected else 1))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(rect, 8, 8)

        marker = QRectF(rect.left() + 14, rect.top() + 14, 14, 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(border_color)
        painter.drawEllipse(marker)

        text_color = self.palette().color(QPalette.ColorRole.Text)
        muted_text_color = self.palette().color(QPalette.ColorRole.Mid)
        painter.setPen(text_color)
        title_rect = QRectF(rect.left() + 36, rect.top() + 8, rect.width() - 48, 28)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine, node.label)

        painter.setPen(muted_text_color)
        painter.drawText(QRectF(rect.left() + 14, rect.top() + 42, rect.width() - 28, 22), Qt.AlignmentFlag.AlignLeft, node.status_label)
        painter.drawText(QRectF(rect.left() + 14, rect.top() + 66, rect.width() - 28, 22), Qt.AlignmentFlag.AlignLeft, node.available_ratio)
        painter.drawText(QRectF(rect.left() + 14, rect.top() + 90, rect.width() - 28, 22), Qt.AlignmentFlag.AlignLeft, node.freshness_label)

    def _service_at(self, point: QPointF) -> str:
        for service_name, rect in self._node_rects.items():
            if rect.contains(point):
                return service_name
        return ""
