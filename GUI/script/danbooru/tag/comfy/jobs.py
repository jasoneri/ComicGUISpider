from __future__ import annotations

import time
from pathlib import Path

import httpx
from deploy import curr_os
from loguru import logger
from PySide6.QtCore import QEvent, QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, FluentIcon as FIF, FlowLayout, IndeterminateProgressRing, InfoBar,
    InfoBarPosition, ScrollArea, StrongBodyLabel, ToolButton, TransparentToolButton,
)
from qframelesswindow import FramelessDialog
from qframelesswindow.utils import startSystemMove

from GUI.core.theme import CustTheme, theme_mgr
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.sql.comfy_job_snapshots import (
    dismiss_job,
    get_snapshots,
    list_local_job_cards,
    snapshot_to_job_record,
    update_job_runtime,
)

from ...style import (
    DEFAULT_CARD_METRICS,
    DanbooruCardMetrics,
    DanbooruUiPalette,
    build_comfy_jobs_stylesheet,
)


_TERMINAL_STATUSES = {"completed", "failed"}
_STATUS_ALIASES = {
    "pending": "pending",
    "queued": "pending",
    "queue": "pending",
    "in_progress": "in_progress",
    "running": "in_progress",
    "executing": "in_progress",
    "processing": "in_progress",
    "completed": "completed",
    "success": "completed",
    "successful": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "failed",
    "canceled": "failed",
    "interrupted": "failed",
}

# 几何对齐 Danbooru 瀑布流（DanbooruCardMetrics + _derive_preview_size）：
# 列宽/高度上限来自 metrics，单卡高度随图比例变；禁止全员等大 168×220 砖块。
_CARD_CONTENT_MARGIN = 4
_ACTION_BUTTON_SIZE = QSize(30, 30)
_OVERLAY_MARGIN = 6
_OVERLAY_BUTTON_SPACING = 4
_BUSY_RING_SIZE = QSize(20, 20)
# Windows/Qt 小浮层 Enter/Leave 不可靠：不用整钮 opacity 依赖 hover。
# 深色 chip 常驻 + 实心 icon；默认来自 tt_gui 热调面板（scrim40 × op70，无阴影）。
_OVERLAY_ICON_COLORS = {
    "tags_attach": "#4ADE80",  # green-400 on dark chip
    "copy": "#E2E8F0",  # slate-200
    "del": "#F87171",  # red-400 on dark chip
}
_DEFAULT_OVERLAY_STYLE = {
    "scrim_rgba": (15, 23, 42, 0.40),
    "scrim_hover_rgba": (15, 23, 42, 0.50),
    "border_rgba": (255, 255, 255, 0.22),
    "button_opacity": 0.70,
    "shadow_blur": 0.0,
    "shadow_alpha": 0,
    "shadow_offset_y": 0.0,
}
# Probe/smoke import: chip alpha is baked into scrim via button_opacity.
_BUTTON_IDLE_OPACITY = float(_DEFAULT_OVERLAY_STYLE["button_opacity"])


def _rgba_css(rgba: tuple[float, ...]) -> str:
    red, green, blue = int(rgba[0]), int(rgba[1]), int(rgba[2])
    alpha = float(rgba[3]) if len(rgba) > 3 else 1.0
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def build_overlay_button_stylesheet(
    *,
    scrim_rgba: tuple[float, ...] = _DEFAULT_OVERLAY_STYLE["scrim_rgba"],
    scrim_hover_rgba: tuple[float, ...] = _DEFAULT_OVERLAY_STYLE["scrim_hover_rgba"],
    border_rgba: tuple[float, ...] = _DEFAULT_OVERLAY_STYLE["border_rgba"],
) -> str:
    """Probe / runtime 可覆写的浮层按钮 QSS（objectName 选择器）。"""
    scrim = _rgba_css(scrim_rgba)
    scrim_hover = _rgba_css(scrim_hover_rgba)
    border = _rgba_css(border_rgba)
    return (
        "QToolButton#ComfyJobTagsAttachBtn,"
        "QToolButton#ComfyJobCopyPromptBtn,"
        "QToolButton#ComfyJobDelBtn {"
        f"background: {scrim};"
        f"border: 1px solid {border};"
        "border-radius: 8px;"
        "padding: 0px;"
        "}"
        "QToolButton#ComfyJobTagsAttachBtn:hover,"
        "QToolButton#ComfyJobCopyPromptBtn:hover,"
        "QToolButton#ComfyJobDelBtn:hover,"
        "QToolButton#ComfyJobTagsAttachBtn:pressed,"
        "QToolButton#ComfyJobCopyPromptBtn:pressed,"
        "QToolButton#ComfyJobDelBtn:pressed {"
        f"background: {scrim_hover};"
        "}"
    )


def _current_theme_name() -> str:
    return "dark" if theme_mgr.get_theme() == CustTheme.DARK else "light"


def _normalize_job_status(raw_status: object) -> str:
    if isinstance(raw_status, dict):
        raw_status = raw_status.get("status") or raw_status.get("str") or raw_status.get("value")
    if not isinstance(raw_status, str) or not raw_status.strip():
        raise ValueError(f"Unknown ComfyUI job status: {raw_status!r}")
    normalized = _STATUS_ALIASES.get(raw_status.strip().casefold())
    if normalized is None:
        raise ValueError(f"Unknown ComfyUI job status: {raw_status!r}")
    return normalized


def _preview_key_from_output(preview: object) -> tuple | None:
    """Stable identity for one output image (dedupe + load cache).

    Prefer Comfy logical triple; fall back to absolute local_path so rows that
    only remember the filesystem path still load after Comfy restart.
    """
    if not isinstance(preview, dict):
        return None
    filename = preview.get("filename")
    if isinstance(filename, str) and filename.strip():
        return (
            filename.strip(),
            str(preview.get("subfolder", "") or ""),
            str(preview.get("type", "output") or "output"),
        )
    local_path = preview.get("local_path")
    if isinstance(local_path, str) and local_path.strip():
        return ("local", "", local_path.strip())
    return None


def extract_preview_output(job: dict) -> dict | None:
    """从 job 记录里抽出可打开的输出图引用。

    /api/jobs 与 ws completed 载荷字段不统一：有的直接给 preview_output，
    有的把 images 挂在 outputs / result 下。统一成一份 dict 再喂给 open/view。
    本地 SoR 行可能只带 local_path（绝对路径），同样合法。
    """
    direct = job.get("preview_output")
    if isinstance(direct, dict) and _preview_key_from_output(direct) is not None:
        return direct

    for images_key in ("images", "output_images"):
        images = job.get(images_key)
        if isinstance(images, list) and images and isinstance(images[0], dict):
            if _preview_key_from_output(images[0]) is not None:
                return images[0]

    outputs = job.get("outputs")
    if isinstance(outputs, dict):
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get("images")
            if isinstance(images, list) and images and isinstance(images[0], dict):
                if _preview_key_from_output(images[0]) is not None:
                    return images[0]
    if isinstance(outputs, list):
        for entry in outputs:
            if not isinstance(entry, dict):
                continue
            node_output = entry.get("output") if isinstance(entry.get("output"), dict) else entry
            images = node_output.get("images") if isinstance(node_output, dict) else None
            if isinstance(images, list) and images and isinstance(images[0], dict):
                if _preview_key_from_output(images[0]) is not None:
                    return images[0]
    return None


def _local_path_from_preview(preview: object) -> Path | None:
    """Absolute path stored on the preview dict, if present and well-formed."""
    if not isinstance(preview, dict):
        return None
    raw = preview.get("local_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return Path(raw.strip()).expanduser()
    except (TypeError, ValueError, OSError):
        return None


def dedupe_jobs_by_preview(jobs: dict[str, dict]) -> dict[str, dict]:
    """同一输出文件只留一条：本地目录一张图，UI 不能排多份幽灵卡。

    进行中的任务没有输出文件，按 job_id 保留；已完成且共享同一 filename 的
    只保留最新（或已在本地缓存的）那条。
    """
    kept: dict[str, dict] = {}
    preview_owner: dict[tuple, str] = {}
    for job_id, job in jobs.items():
        status = _normalize_job_status(job.get("status", "pending"))
        preview = extract_preview_output(job)
        preview_key = _preview_key_from_output(preview)
        if preview_key is None or status not in _TERMINAL_STATUSES:
            kept[job_id] = job
            continue
        existing_id = preview_owner.get(preview_key)
        if existing_id is None:
            preview_owner[preview_key] = job_id
            kept[job_id] = job
            continue
        # 后到的同图 job 丢弃；若现有是失败、新的是完成，则用完成替换。
        # 无论谁留下，本地登记的编辑器原文不能丢。
        existing_job = kept[existing_id]
        existing_status = _normalize_job_status(existing_job.get("status", "failed"))
        kept_prompt = str(
            existing_job.get("editor_prompt") or job.get("editor_prompt") or ""
        ).strip()
        if existing_status == "failed" and status == "completed":
            del kept[existing_id]
            preview_owner[preview_key] = job_id
            kept[job_id] = dict(job)
            if kept_prompt:
                kept[job_id]["editor_prompt"] = kept_prompt
        elif kept_prompt and not str(existing_job.get("editor_prompt") or "").strip():
            existing_job["editor_prompt"] = kept_prompt
    return kept


class _SnapshotBatchSignals(QObject):
    finished = Signal(object)  # dict[str, dict]
    failed = Signal(str)


class _SnapshotBatchRunnable(QRunnable):
    """Worker: one SQLite connection for many job_ids (never touch Qt widgets here)."""

    def __init__(self, job_ids: list[str], signals: _SnapshotBatchSignals):
        super().__init__()
        self._job_ids = list(job_ids)
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            rows = get_snapshots(self._job_ids)
            self._signals.finished.emit(rows)
        except Exception as error:
            logger.exception("Comfy snapshot batch load failed")
            self._signals.failed.emit(str(error))


class _JobRuntimePersistSignals(QObject):
    finished = Signal(object)  # dict | None
    failed = Signal(str)


class _JobRuntimePersistRunnable(QRunnable):
    """Worker: patch status/preview on an existing snapshot row (no Qt widgets)."""

    def __init__(
        self,
        job_id: str,
        *,
        status: str | None,
        preview_output: dict | None,
        signals: _JobRuntimePersistSignals,
    ):
        super().__init__()
        self._job_id = job_id
        self._status = status
        self._preview_output = preview_output
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            row = update_job_runtime(
                self._job_id,
                status=self._status,
                preview_output=self._preview_output,
            )
            self._signals.finished.emit(row)
        except Exception as error:
            logger.exception("Comfy job runtime persist failed job={}", self._job_id)
            self._signals.failed.emit(str(error))


class _JobDismissSignals(QObject):
    finished = Signal(str, bool)  # job_id, updated
    failed = Signal(str, str)  # job_id, message


class _JobDismissRunnable(QRunnable):
    """Worker: soft-delete one card row so refresh will not restore it."""

    def __init__(self, job_id: str, signals: _JobDismissSignals):
        super().__init__()
        self._job_id = job_id
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            updated = dismiss_job(self._job_id)
            self._signals.finished.emit(self._job_id, bool(updated))
        except Exception as error:
            logger.exception("Comfy job dismiss failed job={}", self._job_id)
            self._signals.failed.emit(self._job_id, str(error))


def _apply_snapshot_fields(job: dict, snapshot: dict) -> None:
    """Merge one SQLite snapshot row onto an in-memory job dict (UI thread)."""
    job["editor_prompt"] = str(snapshot.get("editor_prompt") or "")
    job["preset"] = str(snapshot.get("unet") or job.get("preset") or "turbo")
    job["snapshot_unet"] = snapshot.get("unet")
    job["snapshot_denoise"] = snapshot.get("denoise")
    job["snapshot_wd14"] = snapshot.get("wd14")
    tag_groups = snapshot.get("tag_groups")
    if tag_groups:
        job["tag_groups"] = tag_groups
    elif snapshot.get("tag_groups_json") is not None:
        from utils.sql.comfy_job_snapshots import decode_tag_groups

        job["tag_groups"] = decode_tag_groups(snapshot.get("tag_groups_json"))


def _move_output_to_del_dir(output_path: Path) -> Path:
    """Move an output file into the `.del` subdirectory beside it (never overwrite).

    保险回收而不是物理删除：同名文件已在 `.del` 中时追加数字后缀保留两者。
    """
    del_dir = output_path.parent.joinpath(".del")
    del_dir.mkdir(parents=True, exist_ok=True)
    target_path = del_dir.joinpath(output_path.name)
    counter = 1
    while target_path.exists():
        target_path = del_dir.joinpath(f"{output_path.stem} ({counter}){output_path.suffix}")
        counter += 1
    output_path.rename(target_path)
    return target_path


class ClickablePreviewLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ComfyJobCard(QFrame):
    """媒体覆盖卡：固定列宽 + 按图比例变高（对齐 Danbooru 瀑布流）；浮层动作。"""

    cancel_requested = Signal(str)
    clear_requested = Signal(str)
    preview_requested = Signal(str)
    prompt_attach_requested = Signal(str)
    prompt_copy_requested = Signal(str)

    def __init__(
        self,
        job_id: str,
        parent=None,
        *,
        metrics: DanbooruCardMetrics = DEFAULT_CARD_METRICS,
    ):
        super().__init__(parent)
        self.job_id = job_id
        self.metrics = metrics
        self._job: dict = {"id": job_id, "status": "pending"}
        self._preview_key: tuple | None = None
        self._loaded_preview_key: tuple | None = None
        # 404 / 文件已删：记失败 key，避免每次 _render_cards 再打 /view 刷 ERROR。
        self.failed_preview_key: tuple | None = None
        self._source_pixmap = QPixmap()
        self._preview_size = QSize(
            max(1, metrics.preview_content_width),
            max(1, metrics.preview_base_height),
        )
        self._overlay_style = dict(_DEFAULT_OVERLAY_STYLE)
        self._tags_shadow: QGraphicsDropShadowEffect | None = None
        self._copy_shadow: QGraphicsDropShadowEffect | None = None
        self._del_shadow: QGraphicsDropShadowEffect | None = None

        self.setObjectName("ComfyJobCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            _CARD_CONTENT_MARGIN,
            _CARD_CONTENT_MARGIN,
            _CARD_CONTENT_MARGIN,
            _CARD_CONTENT_MARGIN,
        )
        root.setSpacing(0)

        # 主体：预览尺寸由 metrics + 图比例推导，点击打开本机图片。
        self.preview_label = ClickablePreviewLabel(self)
        self.preview_label.setObjectName("ComfyJobPreviewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(False)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.preview_label.clicked.connect(lambda: self.preview_requested.emit(self.job_id))
        root.addWidget(self.preview_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # 浮层不进布局流：ring 居中，动作按钮钉在预览右上角（常驻 chip，不靠 hover）。
        self.busy_ring = IndeterminateProgressRing(self.preview_label, start=False)
        self.busy_ring.setFixedSize(_BUSY_RING_SIZE)
        self.busy_ring.setStrokeWidth(3)
        self.busy_ring.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.busy_ring.hide()

        # 创建顺序：copy 最先（浮层最左），再 attach，最后 del（最右）。
        self.copy_prompt_btn = ToolButton(self.preview_label)
        self.copy_prompt_btn.setObjectName("ComfyJobCopyPromptBtn")
        self.copy_prompt_btn.setIconSize(QSize(16, 16))
        self.copy_prompt_btn.setFixedSize(_ACTION_BUTTON_SIZE)
        self.copy_prompt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_prompt_btn.clicked.connect(
            lambda: self.prompt_copy_requested.emit(self.job_id)
        )
        self.copy_prompt_btn.hide()

        self.tags_attach_btn = ToolButton(self.preview_label)
        self.tags_attach_btn.setObjectName("ComfyJobTagsAttachBtn")
        self.tags_attach_btn.setIconSize(QSize(16, 16))
        self.tags_attach_btn.setFixedSize(_ACTION_BUTTON_SIZE)
        self.tags_attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tags_attach_btn.clicked.connect(
            lambda: self.prompt_attach_requested.emit(self.job_id)
        )
        self.tags_attach_btn.hide()

        self.del_btn = ToolButton(self.preview_label)
        self.del_btn.setObjectName("ComfyJobDelBtn")
        self.del_btn.setIconSize(QSize(16, 16))
        self.del_btn.setFixedSize(_ACTION_BUTTON_SIZE)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.clicked.connect(self._on_delete_clicked)
        self.del_btn.hide()

        self.apply_icon_colors()
        self.apply_overlay_style()
        self._sync_geometry()

    @property
    def preview_key(self) -> tuple | None:
        return self._preview_key

    @property
    def loaded_preview_key(self) -> tuple | None:
        return self._loaded_preview_key

    def apply_icon_colors(self) -> None:
        """暗底 chip 上的亮色 icon：tagsAttach 绿、copy 中性、del 红。"""
        self.tags_attach_btn.setIcon(
            CgsIcon.SCRIPT_TAG_ADD.icon(color=QColor(_OVERLAY_ICON_COLORS["tags_attach"]))
        )
        self.copy_prompt_btn.setIcon(
            FIF.COPY.icon(color=QColor(_OVERLAY_ICON_COLORS["copy"]))
        )
        self.del_btn.setIcon(
            FIF.DELETE.icon(color=QColor(_OVERLAY_ICON_COLORS["del"]))
        )

    def apply_overlay_style(self, **overrides) -> None:
        """应用/覆写浮层 chip 样式（tt_gui 探针可热调）。

        支持键：scrim_rgba, scrim_hover_rgba, border_rgba, button_opacity,
        shadow_blur, shadow_alpha, shadow_offset_y。
        """
        for key, value in overrides.items():
            if key not in self._overlay_style:
                raise KeyError(f"Unknown Comfy overlay style key: {key!r}")
            self._overlay_style[key] = value
        style = self._overlay_style
        # 子控件 windowOpacity 无效；整钮「透明度」乘进 scrim alpha（probe 滑条）。
        opacity = max(0.05, min(1.0, float(style["button_opacity"])))
        scrim = list(style["scrim_rgba"])
        scrim_hover = list(style["scrim_hover_rgba"])
        if len(scrim) >= 4:
            scrim[3] = max(0.05, min(1.0, float(scrim[3]) * opacity))
        if len(scrim_hover) >= 4:
            scrim_hover[3] = max(0.05, min(1.0, float(scrim_hover[3]) * opacity))
        button_qss = build_overlay_button_stylesheet(
            scrim_rgba=tuple(scrim),
            scrim_hover_rgba=tuple(scrim_hover),
            border_rgba=tuple(style["border_rgba"]),
        )
        self.tags_attach_btn.setStyleSheet(button_qss)
        self.copy_prompt_btn.setStyleSheet(button_qss)
        self.del_btn.setStyleSheet(button_qss)
        self._tags_shadow = self._ensure_button_shadow(self.tags_attach_btn, self._tags_shadow)
        self._copy_shadow = self._ensure_button_shadow(self.copy_prompt_btn, self._copy_shadow)
        self._del_shadow = self._ensure_button_shadow(self.del_btn, self._del_shadow)

    def _ensure_button_shadow(
        self,
        button: QWidget,
        existing: QGraphicsDropShadowEffect | None,
    ) -> QGraphicsDropShadowEffect:
        style = self._overlay_style
        shadow = existing if existing is not None else QGraphicsDropShadowEffect(button)
        shadow.setBlurRadius(float(style["shadow_blur"]))
        shadow.setOffset(0.0, float(style["shadow_offset_y"]))
        shadow.setColor(QColor(0, 0, 0, int(style["shadow_alpha"])))
        if existing is None:
            button.setGraphicsEffect(shadow)
        return shadow

    def apply_metrics(self, metrics: DanbooruCardMetrics) -> None:
        """与 Danbooru 网格 zoom 同源：列宽变、预览高度按图重算。"""
        self.metrics = metrics
        self._sync_geometry()
        if not self._source_pixmap.isNull():
            self._paint_preview_pixmap()

    def _source_preview_size(self) -> QSize:
        if not self._source_pixmap.isNull():
            return self._source_pixmap.size()
        return QSize(
            max(1, self.metrics.preview_content_width),
            max(1, self.metrics.preview_base_height),
        )

    def _derive_preview_size(self) -> QSize:
        """与 DanbooruCardWidget 同源：bounds=(content_w, max_h)，KeepAspectRatio。"""
        source_size = self._source_preview_size()
        bounds = QSize(
            max(1, self.metrics.preview_content_width),
            max(1, self.metrics.preview_max_height),
        )
        if source_size.width() <= 0 or source_size.height() <= 0:
            return QSize(bounds.width(), max(1, self.metrics.preview_base_height))
        fitted = source_size.scaled(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        return QSize(max(1, fitted.width()), max(1, fitted.height()))

    def sizeHint(self) -> QSize:
        layout = self.layout()
        margins = layout.contentsMargins() if layout is not None else None
        left = margins.left() if margins else _CARD_CONTENT_MARGIN
        right = margins.right() if margins else _CARD_CONTENT_MARGIN
        top = margins.top() if margins else _CARD_CONTENT_MARGIN
        bottom = margins.bottom() if margins else _CARD_CONTENT_MARGIN
        return QSize(
            left + self._preview_size.width() + right,
            top + self._preview_size.height() + bottom,
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _sync_geometry(self) -> None:
        self._preview_size = self._derive_preview_size()
        self.preview_label.setFixedSize(self._preview_size)
        # 卡壳 = 预览 + margins（同 Danbooru）；尺寸来自 sizeHint，非全局常数砖。
        self.setFixedSize(self.sizeHint())
        self._relocate_overlays()
        self.adjustSize()
        self.updateGeometry()

    def _paint_preview_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            return
        target = self._preview_size
        if target.width() < 8 or target.height() < 8:
            return
        # 与 Danbooru 一致：KeepAspectRatioByExpanding + 中心裁切，填满预览框。
        scaled = self._source_pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        source_x = max(0, (scaled.width() - target.width()) // 2)
        source_y = max(0, (scaled.height() - target.height()) // 2)
        cropped = scaled.copy(source_x, source_y, target.width(), target.height())
        self.preview_label.setPixmap(cropped)

    def _relocate_overlays(self) -> None:
        preview_size = self.preview_label.size()
        self.busy_ring.move(
            (preview_size.width() - self.busy_ring.width()) // 2,
            (preview_size.height() - self.busy_ring.height()) // 2,
        )
        # 从左到右：copy | tagsAttach | del（copy 最先创建，浮层最左）。
        del_x = preview_size.width() - _OVERLAY_MARGIN - self.del_btn.width()
        del_y = _OVERLAY_MARGIN
        self.del_btn.move(del_x, del_y)
        attach_x = del_x - self.tags_attach_btn.width() - _OVERLAY_BUTTON_SPACING
        self.tags_attach_btn.move(attach_x, del_y)
        copy_x = attach_x - self.copy_prompt_btn.width() - _OVERLAY_BUTTON_SPACING
        self.copy_prompt_btn.move(copy_x, del_y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relocate_overlays()

    def showEvent(self, event):
        super().showEvent(event)
        self._relocate_overlays()

    def update_job(self, job: dict) -> None:
        job_id = job.get("id")
        if job_id != self.job_id:
            raise ValueError(f"Comfy job card id mismatch: {job_id!r}")
        status = _normalize_job_status(job.get("status"))
        normalized_job = dict(job)
        normalized_job["status"] = status
        preview = extract_preview_output(normalized_job)
        if preview is not None:
            normalized_job["preview_output"] = preview
        self._job = normalized_job
        self._preview_key = _preview_key_from_output(preview)

        # 不展示「进行中 / 已完成」文案：进行中用居中 ring。
        # 终态必须始终露出 copy | tagsAttach | del 三钮（与创建顺序一致）。
        # 禁止用 has_prompt 藏钮：异步 hydrate / refresh 时 editor_prompt 可能短暂为空，
        # 藏掉会只剩 del（拆东墙）。无 prompt 时仍显示，点击路径 InfoBar / 异步补全。
        is_busy = status not in _TERMINAL_STATUSES
        if is_busy:
            self.busy_ring.show()
            self.busy_ring.start()
            self.tags_attach_btn.hide()
            self.copy_prompt_btn.hide()
            self.del_btn.hide()
            if self._source_pixmap.isNull():
                self.preview_label.clear()
                self.preview_label.setText("")
            # busy 无图：回到 base 占位高，避免空卡塌成一条。
            if self._source_pixmap.isNull():
                self._sync_geometry()
        else:
            self.busy_ring.stop()
            self.busy_ring.hide()
            self.copy_prompt_btn.show()
            self.copy_prompt_btn.setEnabled(True)
            self.tags_attach_btn.show()
            self.tags_attach_btn.setEnabled(True)
            self.del_btn.show()
            self.del_btn.setEnabled(True)
            self._relocate_overlays()
            if status == "failed" and self._loaded_preview_key is None:
                self.preview_label.setText(str(job.get("error") or "失败"))
                if self._source_pixmap.isNull():
                    self._sync_geometry()

    def set_preview_bytes(self, data: bytes, preview_key: tuple) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            raise ValueError(f"Comfy preview output is not a readable image: {self.job_id}")
        self._source_pixmap = pixmap
        self._loaded_preview_key = preview_key
        self.failed_preview_key = None
        self.preview_label.setText("")
        self._sync_geometry()
        self._paint_preview_pixmap()

    def mark_preview_unavailable(self, preview_key: tuple, reason: str) -> None:
        """Remember a missing output so re-render does not re-fetch the same 404."""
        self.failed_preview_key = preview_key
        self._loaded_preview_key = None
        self._source_pixmap = QPixmap()
        if not self.preview_label.pixmap() or self.preview_label.pixmap().isNull():
            self.preview_label.clear()
            self.preview_label.setText(reason.strip() or "图片缺失")
        self._sync_geometry()

    def clear_preview_failure(self) -> None:
        self.failed_preview_key = None

    def _on_delete_clicked(self) -> None:
        status = self._job.get("status")
        if status not in _TERMINAL_STATUSES:
            self.cancel_requested.emit(self.job_id)
        else:
            self.clear_requested.emit(self.job_id)


class ComfyJobsDialog(FramelessDialog):
    """ComfyUI 任务列表：媒体覆盖卡 + FlowLayout 流式排布，按输出图去重。

    CGS008: Qt parent MUST be the current TagExportPanel (``actions.open_comfy_jobs``
    passes ``parent=self._panel``). MUST NOT parent to DanbooruInterface / viewer.
    ``panel_getter`` resolves the live panel for tagsAttach / COPY after reopen.
    """

    def __init__(self, client, parent=None, *, panel_getter=None):
        super().__init__(parent)
        self.client = client
        self._panel_getter = panel_getter
        self._jobs: dict[str, dict] = {}
        self._cards: dict[str, ComfyJobCard] = {}
        # SQLite 快照内存缓存：UI 路径优先读这里，缺省再异步批量拉库。
        self._snapshot_cache: dict[str, dict] = {}
        self._snapshot_hydrate_generation = 0
        self._snapshot_thread_pool = QThreadPool.globalInstance()
        # 与 interface 瀑布流默认 zoom 同源；卡高由各图比例推导。
        self.card_metrics = DEFAULT_CARD_METRICS
        self.resize(720, 560)
        self.setWindowTitle("Comfy 任务")
        self.setObjectName("ComfyJobsDialog")
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 14)
        root.setSpacing(8)

        # Custom chrome replaces FramelessDialog titleBar; drag via startSystemMove
        # (setProperty("draggable") is not wired by Qt/qframelesswindow).
        self.header_shell = QFrame(self)
        self.header_shell.setObjectName("ComfyJobsHeaderShell")
        # Empty-state hides scroll; without Fixed vertical policy the QFrame expands
        # and steals the dialog body (header becomes a tall empty slab).
        self.header_shell.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.header_shell.installEventFilter(self)
        header = QHBoxLayout(self.header_shell)
        header.setContentsMargins(14, 6, 8, 6)
        header.setSpacing(4)
        self.header_title = StrongBodyLabel("Comfy 任务", self.header_shell)
        # Title must not steal press events so empty/title area can drag the dialog.
        self.header_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header.addWidget(self.header_title)
        header.addStretch(1)
        self.comfy_output_btn = TransparentToolButton(FIF.FOLDER, self.header_shell)
        self.comfy_output_btn.clicked.connect(self._open_output_directory)
        header.addWidget(self.comfy_output_btn)
        self.refresh_button = TransparentToolButton(FIF.SYNC, self.header_shell)
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        self.close_button = TransparentToolButton(self.header_shell)
        self.close_button.setIcon(QIcon(":/close.svg"))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        root.addWidget(self.header_shell, 0)

        self.error_label = BodyLabel("", self)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label, 0)

        self.empty_label = BodyLabel("暂无任务", self)
        self.empty_label.setObjectName("ComfyJobsEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.empty_label.hide()
        # stretch=1 so empty copy (or scroll when jobs exist) owns the body height.
        root.addWidget(self.empty_label, 1)

        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.enableTransparentBackground()
        self.cards_host = QWidget(self.scroll)
        self.cards_host.setObjectName("ComfyJobsCardsHost")
        self.cards_layout = FlowLayout(self.cards_host)
        self.cards_layout.setContentsMargins(2, 2, 10, 18)
        self.cards_layout.setHorizontalSpacing(12)
        self.cards_layout.setVerticalSpacing(12)
        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll, 1)

        client.job_started.connect(self._on_job_started)
        client.progress_updated.connect(self._on_progress)
        client.job_completed.connect(self._on_job_completed)
        client.job_failed.connect(self._on_job_failed)
        client.job_cancelled.connect(self._on_job_cancelled)

        self._theme_callback = self._apply_theme
        theme_mgr.subscribe(self._theme_callback)
        self.destroyed.connect(self._unsubscribe_theme)
        self._apply_theme(theme_mgr.currentTheme)
        self.refresh()

    def _unsubscribe_theme(self, *_args):
        theme_mgr.unsubscribe(self._theme_callback)

    def _apply_theme(self, _theme=None):
        self.setStyleSheet(build_comfy_jobs_stylesheet(DanbooruUiPalette.current()))
        for card in self._cards.values():
            card.apply_icon_colors()

    def _header_press_hits_button(self, position) -> bool:
        """True when the press lands on a header tool button (or its child)."""
        hit_widget = self.header_shell.childAt(position)
        while hit_widget is not None and hit_widget is not self.header_shell:
            if isinstance(hit_widget, QAbstractButton):
                return True
            hit_widget = hit_widget.parentWidget()
        return False

    def eventFilter(self, obj, event):
        # Mirror DanbooruViewer top_bar: left-press on non-button header chrome moves window.
        if obj is self.header_shell and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                press_pos = event.position().toPoint()
                if not self._header_press_hits_button(press_pos):
                    startSystemMove(self, event.globalPosition().toPoint())
                    return True
        return super().eventFilter(obj, event)

    def add_local_job(
        self,
        job_id: str,
        *,
        preset: str,
        editor_prompt: str = "",
        tag_groups=None,
    ) -> None:
        """登记本会话提交的任务；优先内存/入参，不在 UI 线程同步打 SQLite。

        权威行仍在 comfy_job_snapshots：提交路径异步 upsert 后写入 _snapshot_cache；
        缺 prompt 时由 _schedule_snapshot_hydrate 批量补全。
        tag_groups：CGS007 submit-time groups（Character/Artist/...），供 attach 直接用。
        """
        previous = self._jobs.get(job_id, {})
        cached = self._snapshot_cache.get(job_id) or {}
        stored_prompt = str(
            editor_prompt
            or previous.get("editor_prompt")
            or cached.get("editor_prompt")
            or ""
        ).strip()
        stored_unet = str(
            preset
            or previous.get("preset")
            or cached.get("unet")
            or "turbo"
        )
        stored_groups = (
            tag_groups
            or previous.get("tag_groups")
            or cached.get("tag_groups")
            or ()
        )
        self._jobs[job_id] = {
            **previous,
            "id": job_id,
            "status": previous.get("status") or "pending",
            "preset": stored_unet,
            "editor_prompt": stored_prompt,
            "tag_groups": stored_groups,
            "snapshot_unet": previous.get("snapshot_unet") or cached.get("unet") or stored_unet,
            "snapshot_denoise": previous.get("snapshot_denoise", cached.get("denoise")),
            "snapshot_wd14": previous.get("snapshot_wd14", cached.get("wd14")),
            "started_monotonic": previous.get("started_monotonic", time.monotonic()),
        }
        if stored_prompt:
            # 同进程提交：入参即权威，先填缓存，避免后续 attach 再同步读库。
            self._snapshot_cache[job_id] = {
                "job_id": job_id,
                "editor_prompt": stored_prompt,
                "unet": stored_unet,
                "denoise": previous.get("snapshot_denoise", cached.get("denoise")),
                "wd14": previous.get("snapshot_wd14", cached.get("wd14")),
                "tag_groups": stored_groups,
            }
        self._render_cards()
        if not stored_prompt:
            self._schedule_snapshot_hydrate((job_id,))

    def refresh(self) -> None:
        """Merge Comfy remote list with local SQLite card index.

        Local ``comfy_job_snapshots`` is the authority for which cards stay visible
        after ComfyUI / PC restart. Remote ``/api/jobs`` only updates live status
        and fills preview when still present. Dismissed rows stay gone; completed
        rows with a known-missing output file are dropped from the UI only (DB
        keep until user deletes or prune).
        """
        try:
            remote_jobs: list[dict] = []
            remote_error: Exception | None = None
            try:
                remote_jobs = self.client.list_jobs(
                    sort_by="created_at", sort_order="desc", limit=100
                )
            except Exception as error:
                # Comfy down / restarted empty is not fatal: still restore from SQLite.
                remote_error = error
                logger.warning("Comfy /api/jobs unavailable during refresh: {}", error)

            previous_jobs = dict(self._jobs)
            rebuilt_jobs: dict[str, dict] = {}
            for remote_job in remote_jobs:
                job_id = remote_job.get("id")
                if not isinstance(job_id, str) or not job_id:
                    raise ValueError("ComfyUI job record has no id.")
                rebuilt_jobs[job_id] = self._merged_job_record(
                    remote_job, previous_jobs.get(job_id, {})
                )

            # Keep in-flight local submits that /api/jobs has not listed yet.
            for job_id, local_job in previous_jobs.items():
                if job_id in rebuilt_jobs:
                    continue
                local_status = _normalize_job_status(local_job.get("status", "pending"))
                if local_status not in _TERMINAL_STATUSES:
                    rebuilt_jobs[job_id] = dict(local_job)

            # SQLite card index: restore completed/failed cards Comfy history lost.
            local_snapshots = list_local_job_cards(limit=100, include_dismissed=False)
            for snapshot in local_snapshots:
                if not isinstance(snapshot, dict):
                    continue
                job_id = str(snapshot.get("job_id") or "").strip()
                if not job_id:
                    continue
                self._snapshot_cache[job_id] = dict(snapshot)
                local_record = snapshot_to_job_record(snapshot)
                if job_id in rebuilt_jobs:
                    rebuilt_jobs[job_id] = self._merge_local_snapshot_into_job(
                        rebuilt_jobs[job_id], snapshot, local_record
                    )
                else:
                    # Prefer fresher in-memory row (this session) when SQLite lags.
                    previous = previous_jobs.get(job_id)
                    if previous is not None:
                        rebuilt_jobs[job_id] = self._merge_local_snapshot_into_job(
                            dict(previous), snapshot, local_record
                        )
                    else:
                        rebuilt_jobs[job_id] = local_record

            rebuilt_jobs = self._drop_completed_jobs_without_local_file(rebuilt_jobs)
            # 先用内存缓存同步填一截，完整 SQLite 批量走线程池（勿 N× get_snapshot 卡 UI）。
            self._apply_cached_snapshots(rebuilt_jobs)
            self._jobs = rebuilt_jobs
            for card in self._cards.values():
                card.clear_preview_failure()
            if remote_error is None:
                self.error_label.clear()
                self.error_label.hide()
            else:
                self.error_label.setText(
                    f"Comfy 暂不可用，已从本地恢复任务卡：{remote_error}"
                )
                self.error_label.show()
            self._render_cards()
            self._schedule_snapshot_hydrate(list(rebuilt_jobs.keys()))
            # Backfill preview/status for rows that still only have prompt metadata.
            self._schedule_runtime_backfill(rebuilt_jobs)
        except Exception as error:
            logger.exception("Comfy 任务列表刷新失败")
            self.error_label.setText(f"Comfy 任务列表刷新失败：{error}")
            self.error_label.show()

    @staticmethod
    def _merged_job_record(remote_job: dict, previous_job: dict) -> dict:
        job_id = remote_job["id"]
        merged_job = dict(previous_job)
        merged_job.update(remote_job)
        previous_status = previous_job.get("status")
        remote_status = _normalize_job_status(remote_job.get("status"))
        merged_job["status"] = remote_status
        status_rank = {"pending": 0, "in_progress": 1, "completed": 2, "failed": 2}
        if (
            previous_status in status_rank
            and remote_status in status_rank
            and status_rank[remote_status] < status_rank[previous_status]
        ):
            # Live websocket 可能比 /api/jobs 快一拍，不能用旧快照把完成打回排队。
            merged_job["status"] = previous_status
        preview = extract_preview_output(merged_job)
        if preview is not None:
            merged_job["preview_output"] = preview
        if _normalize_job_status(merged_job["status"]) in _TERMINAL_STATUSES:
            merged_job.pop("display_node", None)
            merged_job.pop("progress_current", None)
            merged_job.pop("progress_max", None)
        merged_job["id"] = job_id
        # Comfy 的 `prompt` 是提交时 workflow 图，不是编辑器原文：merge 时丢弃。
        merged_job.pop("prompt", None)
        # /api/jobs 不带快照；本地/SQLite 登记的必须跨 refresh 保留。
        if not str(merged_job.get("editor_prompt") or "").strip():
            local_prompt = str(previous_job.get("editor_prompt") or "").strip()
            if local_prompt:
                merged_job["editor_prompt"] = local_prompt
        if not merged_job.get("tag_groups") and previous_job.get("tag_groups"):
            merged_job["tag_groups"] = previous_job.get("tag_groups")
        for snapshot_key in ("snapshot_unet", "snapshot_denoise", "snapshot_wd14"):
            if merged_job.get(snapshot_key) is None and previous_job.get(snapshot_key) is not None:
                merged_job[snapshot_key] = previous_job.get(snapshot_key)
        return merged_job

    @staticmethod
    def _merge_local_snapshot_into_job(
        job: dict,
        snapshot: dict,
        local_record: dict,
    ) -> dict:
        """Fill missing prompt/preview/status from SQLite without downgrading live status."""
        merged = dict(job)
        _apply_snapshot_fields(merged, snapshot)
        if extract_preview_output(merged) is None:
            local_preview = extract_preview_output(local_record)
            if local_preview is not None:
                merged["preview_output"] = local_preview
        if "local_created_at" not in merged and local_record.get("local_created_at") is not None:
            merged["local_created_at"] = local_record.get("local_created_at")
        try:
            current_status = _normalize_job_status(merged.get("status", "pending"))
        except ValueError:
            current_status = "pending"
            merged["status"] = current_status
        local_status = _normalize_job_status(local_record.get("status", "completed"))
        status_rank = {"pending": 0, "in_progress": 1, "completed": 2, "failed": 2}
        if status_rank.get(local_status, 0) > status_rank.get(current_status, 0):
            # SQLite completed/failed beats a stale pending left after Comfy restart.
            merged["status"] = local_status
        if not merged.get("preset"):
            merged["preset"] = local_record.get("preset") or "turbo"
        merged["id"] = str(merged.get("id") or local_record.get("id") or "")
        return merged

    def _apply_cached_snapshots(self, jobs: dict[str, dict]) -> None:
        """UI 线程：仅合并已在 _snapshot_cache 的行（无 I/O）。

        Always fill missing editor_prompt / tag_groups / control fields from cache.
        Never skip prompt merge just because unet/denoise already exist.
        """
        for job_id, job in jobs.items():
            snapshot = self._snapshot_cache.get(job_id)
            if snapshot is None:
                continue
            if not str(job.get("editor_prompt") or "").strip():
                prompt = str(snapshot.get("editor_prompt") or "").strip()
                if prompt:
                    job["editor_prompt"] = prompt
            if job.get("snapshot_unet") is None and snapshot.get("unet") is not None:
                job["snapshot_unet"] = snapshot.get("unet")
                if not job.get("preset"):
                    job["preset"] = snapshot.get("unet")
            if job.get("snapshot_denoise") is None and snapshot.get("denoise") is not None:
                job["snapshot_denoise"] = snapshot.get("denoise")
            if job.get("snapshot_wd14") is None and snapshot.get("wd14") is not None:
                job["snapshot_wd14"] = snapshot.get("wd14")
            # Prompt 已有时仍要补 tag_groups，否则 attach 丢 Character 种子。
            if not job.get("tag_groups"):
                groups = snapshot.get("tag_groups")
                if groups:
                    job["tag_groups"] = groups
                elif snapshot.get("tag_groups_json"):
                    from utils.sql.comfy_job_snapshots import decode_tag_groups

                    job["tag_groups"] = decode_tag_groups(snapshot.get("tag_groups_json"))

    def remember_snapshot(self, snapshot: dict | None) -> None:
        """Controller 异步 upsert 成功后回填缓存（可从任意线程排队到 UI）。"""
        if not isinstance(snapshot, dict):
            return
        job_id = str(snapshot.get("job_id") or "").strip()
        if not job_id:
            return
        self._snapshot_cache[job_id] = dict(snapshot)
        job = self._jobs.get(job_id)
        if job is not None:
            _apply_snapshot_fields(job, snapshot)
            card = self._cards.get(job_id)
            if card is not None:
                card.update_job(job)

    def _schedule_snapshot_hydrate(self, job_ids) -> None:
        """后台批量 get_snapshots；完成后回主线程合并并局部 refresh cards。"""
        pending: list[str] = []
        for raw in job_ids or ():
            job_id = str(raw or "").strip()
            if not job_id:
                continue
            job = self._jobs.get(job_id)
            if job is None:
                continue
            if str(job.get("editor_prompt") or "").strip() and job_id in self._snapshot_cache:
                continue
            if job_id in self._snapshot_cache and str(
                self._snapshot_cache[job_id].get("editor_prompt") or ""
            ).strip():
                _apply_snapshot_fields(job, self._snapshot_cache[job_id])
                continue
            pending.append(job_id)
        if not pending:
            return
        self._snapshot_hydrate_generation += 1
        generation = self._snapshot_hydrate_generation
        signals = _SnapshotBatchSignals(self)

        def on_finished(rows: object) -> None:
            if generation != self._snapshot_hydrate_generation:
                return
            if not isinstance(rows, dict):
                return
            touched: list[str] = []
            for job_id, snapshot in rows.items():
                if not isinstance(snapshot, dict):
                    continue
                self._snapshot_cache[str(job_id)] = dict(snapshot)
                job = self._jobs.get(str(job_id))
                if job is None:
                    continue
                _apply_snapshot_fields(job, snapshot)
                touched.append(str(job_id))
            for job_id in touched:
                card = self._cards.get(job_id)
                if card is not None:
                    card.update_job(self._jobs[job_id])

        def on_failed(message: str) -> None:
            if generation != self._snapshot_hydrate_generation:
                return
            logger.warning("Comfy snapshot hydrate failed: {}", message)

        signals.finished.connect(on_finished)
        signals.failed.connect(on_failed)
        self._snapshot_thread_pool.start(_SnapshotBatchRunnable(pending, signals))

    def _resolve_local_preview_path(self, preview: dict) -> Path | None:
        """Prefer stored absolute local_path; else resolve via live Comfy output dir."""
        stored = _local_path_from_preview(preview)
        if stored is not None:
            try:
                if stored.is_file():
                    return stored.resolve()
            except OSError:
                pass
            # Stale absolute path: still try Comfy-relative resolution below.
        try:
            return self.client.output_file_path(preview)
        except (FileNotFoundError, RuntimeError, OSError, ValueError, TypeError):
            return None

    def _attach_local_path_to_preview(self, preview: dict | None) -> dict | None:
        """Stamp absolute local_path onto preview so SQLite survives Comfy restart."""
        if not isinstance(preview, dict):
            return None
        enriched = dict(preview)
        if _local_path_from_preview(enriched) is not None:
            stored = _local_path_from_preview(enriched)
            if stored is not None and stored.is_file():
                return enriched
        try:
            resolved = self.client.output_file_path(enriched)
        except (FileNotFoundError, RuntimeError, OSError, ValueError, TypeError):
            return enriched
        enriched["local_path"] = str(resolved)
        if not str(enriched.get("filename") or "").strip():
            enriched["filename"] = resolved.name
        return enriched

    def _local_preview_exists(self, preview: dict) -> bool | None:
        """True/False when resolvable; None when neither local_path nor Comfy dir works."""
        stored = _local_path_from_preview(preview)
        if stored is not None:
            try:
                if stored.is_file():
                    return True
                # Explicit path recorded but missing — known gone (do not need Comfy up).
                return False
            except OSError:
                return False
        try:
            return self.client.output_file_path(preview).is_file()
        except FileNotFoundError:
            return False
        except (RuntimeError, OSError, ValueError, TypeError):
            return None

    def _drop_completed_jobs_without_local_file(self, jobs: dict[str, dict]) -> dict[str, dict]:
        """Completed + known-missing output ⇒ drop UI row (local delete / external delete).

        When preview is unknown (None) or output dir cannot be resolved, keep the card:
        Comfy restart must still show history even if the image path is temporarily
        unavailable. Only drop when the file is positively missing.
        """
        kept: dict[str, dict] = {}
        for job_id, job in jobs.items():
            status = _normalize_job_status(job.get("status", "pending"))
            if status != "completed":
                kept[job_id] = job
                continue
            preview = extract_preview_output(job)
            if preview is None:
                # Legacy prompt-only snapshot: keep card so attach/COPY still work.
                kept[job_id] = job
                continue
            exists = self._local_preview_exists(preview)
            if exists is False:
                logger.debug("Comfy refresh dropped completed job without local file: {}", job_id)
                continue
            kept[job_id] = job
        return kept

    def _schedule_runtime_persist(
        self,
        job_id: str,
        *,
        status: str | None = None,
        preview_output: dict | None = None,
    ) -> None:
        """Async status/preview patch so cards survive Comfy restart."""
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return
        if status is None and preview_output is None:
            return
        signals = _JobRuntimePersistSignals(self)

        def on_finished(row: object) -> None:
            if isinstance(row, dict):
                self.remember_snapshot(row)

        def on_failed(message: str) -> None:
            logger.warning(
                "Comfy job runtime persist failed job={}: {}",
                normalized_job_id,
                message,
            )

        signals.finished.connect(on_finished)
        signals.failed.connect(on_failed)
        self._snapshot_thread_pool.start(
            _JobRuntimePersistRunnable(
                normalized_job_id,
                status=status,
                preview_output=preview_output,
                signals=signals,
            )
        )

    def _schedule_runtime_backfill(self, jobs: dict[str, dict]) -> None:
        """Write preview/status/local_path discovered from remote onto legacy snapshot rows."""
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            cached = self._snapshot_cache.get(job_id) or {}
            needs_status = not cached or cached.get("status") in (None, "")
            preview = extract_preview_output(job)
            # Stamp absolute path while Comfy process is still discoverable.
            if preview is not None and _local_path_from_preview(preview) is None:
                stamped = self._attach_local_path_to_preview(preview)
                if stamped is not None:
                    preview = stamped
                    job["preview_output"] = stamped
            cached_preview = cached.get("preview_output")
            cached_has_local = (
                isinstance(cached_preview, dict)
                and bool(str(cached_preview.get("local_path") or "").strip())
            )
            needs_preview = preview is not None and (
                not cached_preview or not cached_has_local
            )
            if not needs_status and not needs_preview:
                # Still refresh status when in-memory terminal differs from cache.
                try:
                    memory_status = _normalize_job_status(job.get("status", "pending"))
                except ValueError:
                    continue
                cached_status = str(cached.get("status") or "").strip()
                if cached_status == memory_status:
                    continue
                if memory_status not in _TERMINAL_STATUSES and cached_status:
                    continue
            try:
                status_value = _normalize_job_status(job.get("status", "completed"))
            except ValueError:
                status_value = "completed"
            self._schedule_runtime_persist(
                job_id,
                status=status_value,
                preview_output=preview if needs_preview else None,
            )

    def _schedule_dismiss_jobs(self, job_ids) -> None:
        """Soft-delete snapshot rows so the next refresh will not resurrect cards."""
        for raw in job_ids or ():
            job_id = str(raw or "").strip()
            if not job_id:
                continue
            self._snapshot_cache.pop(job_id, None)
            signals = _JobDismissSignals(self)

            def on_failed(failed_job_id: str, message: str) -> None:
                logger.warning(
                    "Comfy job dismiss failed job={}: {}",
                    failed_job_id,
                    message,
                )

            signals.failed.connect(on_failed)
            self._snapshot_thread_pool.start(_JobDismissRunnable(job_id, signals))

    def _update_empty_state(self) -> None:
        has_jobs = bool(self._cards)
        self.empty_label.setVisible(not has_jobs)
        self.scroll.setVisible(has_jobs)

    def _clear_flow(self) -> None:
        while self.cards_layout.count():
            widget = self.cards_layout.takeAt(0)
            if widget is not None:
                widget.setParent(None)

    def _render_cards(self) -> None:
        self._jobs = dedupe_jobs_by_preview(self._jobs)
        ordered_ids = list(self._jobs)

        stale_ids = set(self._cards).difference(ordered_ids)
        for job_id in stale_ids:
            self._remove_card(job_id)

        self._clear_flow()
        for job_id in ordered_ids:
            card = self._cards.get(job_id)
            if card is None:
                card = self._create_card(job_id)
            card.update_job(self._jobs[job_id])
            self._load_preview_if_needed(card, self._jobs[job_id])
            self.cards_layout.addWidget(card)
        self._update_empty_state()

    def _create_card(self, job_id: str) -> ComfyJobCard:
        card = ComfyJobCard(job_id, self.cards_host, metrics=self.card_metrics)
        card.cancel_requested.connect(self._cancel_job)
        card.clear_requested.connect(self._clear_job)
        card.preview_requested.connect(self._open_preview)
        card.prompt_attach_requested.connect(self._attach_job_to_panel)
        card.prompt_copy_requested.connect(self._copy_job_prompt)
        self._cards[job_id] = card
        return card

    def _resolve_panel(self):
        panel = self._panel_getter() if self._panel_getter is not None else None
        if panel is None:
            return None
        return panel

    def _resolve_snapshot_for_job(self, job_id: str) -> dict | None:
        """Prefer memory (job dict / cache); never block UI with SQLite on click path.

        MUST merge tag_groups from cache even when job already has editor_prompt.
        Early-return that dropped cache groups left Character unseeded on attach
        (uzaki hana → General while @artist still worked via structural @).
        """
        job = self._jobs.get(job_id) if isinstance(self._jobs.get(job_id), dict) else None
        cached = self._snapshot_cache.get(job_id)
        if not isinstance(cached, dict):
            cached = {}

        editor_prompt = ""
        if job is not None:
            editor_prompt = str(job.get("editor_prompt") or "").strip()
        if not editor_prompt:
            editor_prompt = str(cached.get("editor_prompt") or "").strip()
        if not editor_prompt:
            return None

        tag_groups = ()
        if job is not None and job.get("tag_groups"):
            tag_groups = job.get("tag_groups") or ()
        if not tag_groups and cached.get("tag_groups"):
            tag_groups = cached.get("tag_groups") or ()
        if not tag_groups and cached.get("tag_groups_json"):
            from utils.sql.comfy_job_snapshots import decode_tag_groups

            tag_groups = decode_tag_groups(cached.get("tag_groups_json"))

        unet = "turbo"
        denoise = None
        wd14 = None
        if job is not None:
            unet = job.get("snapshot_unet") or job.get("preset") or unet
            denoise = job.get("snapshot_denoise")
            wd14 = job.get("snapshot_wd14")
        if cached.get("unet"):
            unet = cached.get("unet") or unet
        if denoise is None and cached.get("denoise") is not None:
            denoise = cached.get("denoise")
        if wd14 is None and cached.get("wd14") is not None:
            wd14 = cached.get("wd14")

        return {
            "job_id": job_id,
            "editor_prompt": editor_prompt,
            "unet": unet,
            "denoise": denoise,
            "wd14": wd14,
            "tag_groups": tag_groups,
        }

    def _attach_job_to_panel(self, job_id: str) -> None:
        """缓存/job 快照 → AttachImg + 仅还原 comfy 控件；不覆盖 preview。

        缺缓存时异步 hydrate 再重试一次，避免 click 路径同步 SQLite。
        """
        snapshot = self._resolve_snapshot_for_job(job_id)
        if snapshot is None:
            signals = _SnapshotBatchSignals(self)

            def retry_attach(rows: object) -> None:
                if isinstance(rows, dict):
                    for key, value in rows.items():
                        if isinstance(value, dict):
                            self._snapshot_cache[str(key)] = dict(value)
                            job = self._jobs.get(str(key))
                            if job is not None:
                                _apply_snapshot_fields(job, value)
                if self._resolve_snapshot_for_job(job_id) is not None:
                    self._attach_job_to_panel(job_id)
                    return
                InfoBar.warning(
                    title="",
                    content="该任务没有本地快照（仅 CGS 提交的任务可附着）",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3500,
                    parent=self,
                )

            signals.finished.connect(retry_attach)
            self._snapshot_thread_pool.start(
                _SnapshotBatchRunnable([job_id], signals)
            )
            return

        editor_prompt = str(snapshot.get("editor_prompt") or "").strip()
        if not editor_prompt:
            InfoBar.warning(
                title="",
                content="该任务没有本地快照（仅 CGS 提交的任务可附着）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        job = self._jobs.get(job_id)
        if isinstance(job, dict):
            _apply_snapshot_fields(job, snapshot)

        panel = self._resolve_panel()
        attach_from_comfy = (
            getattr(panel, "attach_from_comfy", None) if panel is not None else None
        )
        if not callable(attach_from_comfy):
            InfoBar.error(
                title="",
                content="Tag 导出面板不可用，无法附着",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
            return

        card = self._cards.get(job_id)
        pic = QPixmap()
        if card is not None and not card._source_pixmap.isNull():
            pic = card._source_pixmap.copy()
        elif isinstance(job, dict):
            preview = extract_preview_output(job)
            if preview is not None:
                try:
                    pic_data = self._fetch_preview_bytes(preview)
                    loaded = QPixmap()
                    if loaded.loadFromData(pic_data):
                        pic = loaded
                except Exception as error:
                    logger.debug("Comfy attach preview fetch skipped: {} ({})", job_id, error)

        attach_from_comfy(
            pic=pic,
            editor_prompt=editor_prompt,
            snapshot=snapshot,
            job_id=job_id,
        )
        if hasattr(panel, "show") and hasattr(panel, "raise_"):
            panel.show()
            panel.raise_()
            panel.activateWindow()
        InfoBar.success(
            title="",
            content="已附着成图 tags，并还原生成设置（Prompt 预览未改动）",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _copy_job_prompt(self, job_id: str) -> None:
        """缓存/job editor_prompt → clipboard；缺缓存时异步 hydrate 再复制。"""
        snapshot = self._resolve_snapshot_for_job(job_id)
        if snapshot is None:
            signals = _SnapshotBatchSignals(self)

            def retry_copy(rows: object) -> None:
                if isinstance(rows, dict):
                    for key, value in rows.items():
                        if isinstance(value, dict):
                            self._snapshot_cache[str(key)] = dict(value)
                self._copy_job_prompt(job_id)

            signals.finished.connect(retry_copy)
            self._snapshot_thread_pool.start(
                _SnapshotBatchRunnable([job_id], signals)
            )
            return

        editor_prompt = str(snapshot.get("editor_prompt") or "")
        if not editor_prompt.strip():
            InfoBar.warning(
                title="",
                content="该任务没有可复制的 Prompt 快照",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            InfoBar.error(
                title="",
                content="系统剪贴板不可用",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        clipboard.setText(editor_prompt)
        InfoBar.success(
            title="",
            content="已复制任务 Prompt",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2200,
            parent=self,
        )

    def _load_preview_if_needed(self, card: ComfyJobCard, job: dict) -> None:
        preview = extract_preview_output(job)
        preview_key = _preview_key_from_output(preview)
        if preview_key is None or card.loaded_preview_key == preview_key:
            return
        if card.failed_preview_key == preview_key:
            return
        try:
            card.set_preview_bytes(self._fetch_preview_bytes(preview), preview_key)
        except FileNotFoundError as error:
            # 输出目录里文件已被清掉：常态，不 exception 刷栈。
            logger.debug("Comfy 预览文件不存在：{} ({})", card.job_id, error)
            card.mark_preview_unavailable(preview_key, "输出图片已不存在（可能已被清理）")
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code if error.response is not None else None
            if status_code == 404:
                logger.debug("Comfy 预览 /view 404：{} ({})", card.job_id, preview_key)
                card.mark_preview_unavailable(preview_key, "输出图片已不存在（Comfy 返回 404）")
                return
            logger.exception("Comfy 预览图加载失败：{}", card.job_id)
            card.mark_preview_unavailable(preview_key, f"无法加载输出图片：{error}")
        except Exception as error:
            logger.exception("Comfy 预览图加载失败：{}", card.job_id)
            card.mark_preview_unavailable(preview_key, f"无法加载输出图片：{error}")

    def _fetch_preview_bytes(self, preview: dict) -> bytes:
        """Prefer absolute local_path, then Comfy output dir, then /view HTTP."""
        local_path = self._resolve_local_preview_path(preview)
        if local_path is not None and local_path.is_file():
            return local_path.read_bytes()
        stored = _local_path_from_preview(preview)
        if stored is not None:
            # Recorded path is authoritative after Comfy restart; do not mask with /view.
            raise FileNotFoundError(f"Comfy preview local_path missing: {stored}")
        return self.client.fetch_output_bytes(preview)

    def _remove_card(self, job_id: str) -> None:
        card = self._cards.pop(job_id, None)
        if card is not None:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._jobs.pop(job_id, None)

    def _cancel_job(self, job_id: str) -> None:
        try:
            self.client.cancel(job_id)
        except Exception as error:
            logger.exception("Comfy 任务取消失败：{}", job_id)
            self.error_label.setText(f"Comfy 任务取消失败：{error}")
            self.error_label.show()
            return
        self._upsert_job(job_id, status="failed", error="已取消")

    def _clear_job(self, job_id: str) -> None:
        """Move local output image into `.del` (if any) and drop every card sharing that file."""
        job = self._jobs.get(job_id, {})
        preview = extract_preview_output(job)
        preview_key = _preview_key_from_output(preview)
        moved_path: Path | None = None
        delete_error: str | None = None
        if isinstance(preview, dict):
            try:
                output_path = self._resolve_local_preview_path(preview)
                if output_path is None:
                    stored = _local_path_from_preview(preview)
                    if stored is not None and not stored.exists():
                        pass  # Already gone — still clear UI records.
                    elif stored is not None:
                        raise FileNotFoundError(f"Comfy preview local_path missing: {stored}")
                    else:
                        # No stored path and Comfy dir unknown — still drop UI/DB row.
                        pass
                else:
                    moved_path = _move_output_to_del_dir(output_path)
            except FileNotFoundError:
                # Already gone — still clear UI records (symmetric with external delete).
                pass
            except (RuntimeError, OSError, ValueError, TypeError) as error:
                delete_error = str(error)
                logger.warning("Comfy 输出图移入 .del 失败：{} ({})", job_id, error)

        job_ids_to_drop = {job_id}
        if preview_key is not None:
            for other_id, other_job in list(self._jobs.items()):
                other_preview = extract_preview_output(other_job)
                if _preview_key_from_output(other_preview) == preview_key:
                    job_ids_to_drop.add(other_id)
        for drop_id in job_ids_to_drop:
            self._remove_card(drop_id)
        # Soft-delete SQLite rows so Comfy restart / refresh will not resurrect cards.
        self._schedule_dismiss_jobs(job_ids_to_drop)
        self._render_cards()

        if delete_error:
            self.error_label.setText(f"任务记录已移除，但移入 .del 失败：{delete_error}")
            self.error_label.show()
            return
        self.error_label.clear()
        self.error_label.hide()
        if moved_path is not None:
            InfoBar.success(
                title="",
                content=f"已移入 .del 并移除记录：{moved_path.name}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
        else:
            InfoBar.success(
                title="",
                content="已移除任务记录（本地输出图已不存在或无法定位）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )

    def _open_output_directory(self) -> None:
        try:
            curr_os.open_folder(self.client.output_directory())
        except (FileNotFoundError, RuntimeError, OSError) as error:
            logger.exception("Unable to open the ComfyUI output directory")
            self.error_label.setText(f"无法打开 Comfy 输出目录：{error}")
            self.error_label.show()
            InfoBar.error(
                title="",
                content=f"无法打开 Comfy 输出目录：{error}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def _open_preview(self, job_id: str) -> None:
        job = self._jobs.get(job_id, {})
        preview = extract_preview_output(job)
        if not isinstance(preview, dict):
            return
        try:
            local_path = self._resolve_local_preview_path(preview)
            if local_path is None or not local_path.is_file():
                raise FileNotFoundError(
                    f"Comfy preview file not found for job {job_id}"
                )
            curr_os.open_file(local_path)
        except Exception as error:
            logger.exception("Comfy 输出图片打开失败：{}", job_id)
            self.error_label.setText(f"无法打开输出图片：{error}")
            self.error_label.show()

    def _upsert_job(self, job_id: str, **fields) -> dict:
        job = self._jobs.setdefault(job_id, {"id": job_id})
        job.update(fields)
        self._render_cards()
        return job

    def _on_job_started(self, job_id: str) -> None:
        job = self._jobs.setdefault(job_id, {"id": job_id})
        self._upsert_job(
            job_id,
            status="in_progress",
            started_monotonic=job.get("started_monotonic", time.monotonic()),
        )
        self._schedule_runtime_persist(job_id, status="in_progress")

    def _on_progress(self, job_id: str, _current: int, _maximum: int, display_node: str) -> None:
        self._upsert_job(job_id, status="in_progress", display_node=display_node)

    def _on_job_completed(self, job_id: str, payload: object) -> None:
        job = self._jobs.setdefault(job_id, {"id": job_id})
        job["status"] = "completed"
        job.pop("display_node", None)
        job.pop("progress_current", None)
        job.pop("progress_max", None)
        preview = None
        if isinstance(payload, dict):
            preview = extract_preview_output(payload)
            if preview is None:
                images = payload.get("images") or []
                if images and isinstance(images[0], dict):
                    preview = images[0]
            # Stamp absolute path while Comfy is still up — SoR for next cold start.
            preview = self._attach_local_path_to_preview(preview)
            if preview is not None:
                job["preview_output"] = preview
        self._render_cards()
        self._schedule_runtime_persist(
            job_id,
            status="completed",
            preview_output=preview if isinstance(preview, dict) else None,
        )

    def _on_job_failed(self, job_id: str, error_text: str) -> None:
        self._upsert_job(job_id, status="failed", error=error_text)
        self._schedule_runtime_persist(job_id, status="failed")

    def _on_job_cancelled(self, job_id: str) -> None:
        self._upsert_job(job_id, status="failed", error="已取消")
        self._schedule_runtime_persist(job_id, status="failed")


__all__ = [
    "ComfyJobCard",
    "ComfyJobsDialog",
    "build_overlay_button_stylesheet",
    "dedupe_jobs_by_preview",
    "extract_preview_output",
]
