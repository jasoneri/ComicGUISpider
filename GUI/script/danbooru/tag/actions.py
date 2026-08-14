from __future__ import annotations

import random
import typing as t
import uuid
from pathlib import Path

from loguru import logger
from PySide6 import QtCore
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.manager.async_task import summarize_error_message
from GUI.uic.qfluent.components import CustomInfoBar
from utils import temp_p
from utils.script import conf as script_conf
from utils.script.ai.capabilities.anima_prompt import AnimaPromptPipeline
from utils.script.ai.kernel import AiProviderConfigSession
from utils.script.image.anima import danbooru_anima as _comfy_workflow
from utils.script.image.anima.comfy_client import (
    COMFY_UNET_PRESETS,
    ComfyJobClient,
    build_workflow,
    configured_comfy_host,
)
from utils.sql.comfy_job_snapshots import upsert_snapshot
from variables import CGS_DOC

from .comfy.jobs import ComfyJobsDialog
from .export import TagExportPanel

# Submit-path snapshot write must not block the UI thread (WAL + prune).

if t.TYPE_CHECKING:
    from ..interface import DanbooruInterface
    from ..viewer import DanbooruImageViewer

_COMFY_NL_TASK_ID = "danbooru_comfy_prompt_merge"
# Product docs anchor for Tag Export → Comfy setup (Desktop / ANIMA / WD14).
_COMFY_DOCS_URL = f"{CGS_DOC}/script/danbooru#comfyui"
_COMFY_DOCS_LINK_NAME = "Comfy 配置说明"


class _SnapshotUpsertSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _SnapshotUpsertRunnable(QRunnable):
    def __init__(
        self,
        *,
        job_id: str,
        editor_prompt: str,
        unet: str,
        denoise: int,
        wd14: bool,
        tag_groups: object,
        signals: _SnapshotUpsertSignals,
    ):
        super().__init__()
        self._job_id = job_id
        self._editor_prompt = editor_prompt
        self._unet = unet
        self._denoise = denoise
        self._wd14 = wd14
        self._tag_groups = tag_groups
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            row = upsert_snapshot(
                self._job_id,
                editor_prompt=self._editor_prompt,
                unet=self._unet,
                denoise=self._denoise,
                wd14=self._wd14,
                tag_groups=self._tag_groups,
                status="pending",
            )
            self._signals.finished.emit(row)
        except Exception as error:
            logger.exception("comfy_job_snapshots upsert failed job={}", self._job_id)
            self._signals.failed.emit(str(error))


class DanbooruTagActionController(QtCore.QObject):
    def __init__(
        self,
        gui,
        parent: "DanbooruInterface",
        *,
        browser_opener: t.Callable[[str, str | None], None] | None = None,
        job_sender: t.Callable[..., None] | None = None,
    ):
        super().__init__(parent)
        if gui is None:
            raise ValueError("DanbooruTagActionController requires gui")
        if parent is None:
            raise ValueError("DanbooruTagActionController requires parent interface")
        self.gui = gui
        self.interface = parent
        self._browser_opener = browser_opener
        self._job_sender = job_sender
        self._panel: TagExportPanel | None = None
        self._viewer: "DanbooruImageViewer | None" = None
        self._send_in_flight = False
        self._comfy_nl_in_flight = False
        # Cache must not share the method name `_comfy_client`; otherwise the
        # attribute shadows the method and `self._comfy_client()` becomes
        # `None()` on first open.
        self._comfy_job_client: ComfyJobClient | None = None
        self._comfy_jobs_dialog = None
        self._comfy_jobs: dict[str, str] = {}
        # 启动即保证 attach 钮隐藏（viewer 初始态 / 无面板）。
        self._sync_export_attach_btn_visible()

    def open_export_panel(self, viewer: "DanbooruImageViewer"):
        self._viewer = viewer
        if viewer.post is None:
            self._show_info(InfoBar.warning, "当前没有可导出的 post", 2500)
            self._sync_export_attach_btn_visible()
            return
        # 先卸 viewer 全局置顶，再出面板：panel/jobs 与 topmost viewer 同场时，
        # HWND_TOPMOST 会压住任务窗。ComfyJobsDialog parent=TagExportPanel（CGS008），
        # 不是 interface；仍须卸顶以免 pin 后盖住面板与 jobs。
        self._release_viewer_topmost(viewer)
        if self._panel is not None:
            self._panel.close()
            self._panel = None
            self._sync_export_attach_btn_visible()
        current_pic = None
        image_label = getattr(viewer, "image_label", None)
        if image_label is not None:
            pixmap = image_label.pixmap()
            if pixmap is not None and not pixmap.isNull():
                current_pic = pixmap
        panel = TagExportPanel(viewer.post, parent=viewer, current_img_pic=current_pic)
        comfy_host = configured_comfy_host()
        if comfy_host:
            panel.set_wd14_status(*_comfy_workflow.wd14_status(host=comfy_host))
        else:
            panel.set_wd14_status(False, "未配置 Comfy host（Script Settings → ComfyUI）")
        panel.copy_requested.connect(lambda: self._on_copy(panel))
        panel.imgpalace_requested.connect(lambda: self._on_imgpalace(panel))
        panel.comfy_nl_requested.connect(lambda: self._on_comfy_nl(panel))
        panel.comfy_requested.connect(self._on_comfy)
        panel.comfy_jobs_requested.connect(self.open_comfy_jobs)
        # 捕获具体面板：旧面板的 destroyed 可能晚于新面板赋值到达。
        panel.destroyed.connect(lambda *_: self._on_panel_destroyed(panel))
        # QDialog.close 常只 hide 不 destroy；finished/close 路径也要藏 attach 钮。
        if hasattr(panel, "finished"):
            panel.finished.connect(lambda *_: self._on_panel_closed(panel))
        self._panel = panel
        panel.show()
        panel.raise_()
        panel.activateWindow()
        self._sync_export_attach_btn_visible()
        # jobs 若已开着，卸顶后补一次 raise，避免仍压在旧 z 序下面。
        self._raise_comfy_jobs_if_visible()

    def attach_from_viewer(self, viewer: "DanbooruImageViewer") -> None:
        """把 viewer 当前 post 设为唯一 AttachImg（覆盖）；不新建面板、不换 CurrentImg。"""
        panel = self._panel
        if panel is None or not panel.isVisible():
            self._show_info(InfoBar.warning, "请先打开 Tag 导出面板再附着", 2500)
            return
        if viewer is None or viewer.post is None:
            self._show_info(InfoBar.warning, "当前没有可附着的 post", 2500, owner=panel)
            return
        pic = None
        image_label = getattr(viewer, "image_label", None)
        if image_label is not None:
            pixmap = image_label.pixmap()
            if pixmap is not None and not pixmap.isNull():
                pic = pixmap
        panel.attach_from_viewer_post(viewer.post, pic=pic)
        panel.show()
        panel.raise_()
        panel.activateWindow()
        self._show_info(InfoBar.success, "已附着当前图到 Attached-tags", 2200, owner=panel)

    def _sync_export_attach_btn_visible(self) -> None:
        """仅 TagExportPanel 存活且可见时展示 export_attach_btn；初始/关闭后必隐藏。"""
        viewers: list = []
        if self._viewer is not None:
            viewers.append(self._viewer)
        interface_viewer = getattr(self.interface, "image_viewer", None)
        if interface_viewer is not None and interface_viewer not in viewers:
            viewers.append(interface_viewer)
        panel = self._panel
        panel_open = False
        if panel is not None:
            try:
                panel_open = bool(panel.isVisible())
            except RuntimeError:
                # C++ 侧已销毁而 Python 包装仍在。
                panel_open = False
                if self._panel is panel:
                    self._panel = None
        for viewer in viewers:
            attach_btn = getattr(viewer, "export_attach_btn", None)
            if attach_btn is None:
                continue
            attach_btn.setVisible(panel_open)

    @staticmethod
    def _release_viewer_topmost(viewer: "DanbooruImageViewer") -> None:
        """Tag 导出 / Comfy 任务出场时强制取消 viewer 置顶。

        与 BrowserWindow 在 clip/ags 收尾里 `topHintBox.click()` 同一思路：
        走 topHintBox 可见态 + keep_top_hint，保证按钮勾选、Qt flag、Win32
        HWND_TOPMOST 三者一致。不自动恢复——置顶是用户显式 pin，会话内
        工具链优先可读。
        """
        top_hint_box = getattr(viewer, "topHintBox", None)
        if top_hint_box is None:
            keep_top_hint = getattr(viewer, "keep_top_hint", None)
            if callable(keep_top_hint):
                keep_top_hint(False)
            return
        if not top_hint_box.isChecked():
            return
        # click() 走 toggled 槽 keep_top_hint，与手动点 pin 同路径。
        top_hint_box.click()

    def _raise_comfy_jobs_if_visible(self) -> None:
        dialog = self._comfy_jobs_dialog
        if dialog is None or not dialog.isVisible():
            return
        dialog.raise_()

    def _on_panel_closed(self, closed_panel, *_args) -> None:
        """面板 close/finished：立即按 isVisible 同步 attach 钮（未必 destroy）。"""
        if self._panel is closed_panel:
            self._sync_export_attach_btn_visible()

    def _on_panel_destroyed(self, destroyed_panel, *_args):
        # 只清自己负责的那个引用，避免旧面板迟到 destroyed 误伤新面板，
        # 否则 tagsAttach 的 panel_getter 会误判「当前面板不可用」。
        if self._panel is destroyed_panel:
            self._panel = None
            self._sync_export_attach_btn_visible()
            # 勿清空 _viewer：jobs dialog 仍可能需要卸顶 / attach 按钮同步。

    def _show_info(
        self,
        factory,
        content: str,
        duration: int = 3000,
        *,
        owner: QWidget | None = None,
    ):
        # Panel actions belong to the panel surface, not the interface behind it.
        parent = owner or self._panel or self._viewer or self.interface.image_viewer
        return factory(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=parent,
        )

    def _show_comfy_setup_error(self, content: str, *, owner: QWidget | None = None):
        """Comfy generate/run failures: error + link to online setup docs."""
        parent = owner or self._panel or self._viewer or self.interface.image_viewer
        return CustomInfoBar.show(
            title="",
            content=content,
            parent=parent,
            url=_COMFY_DOCS_URL,
            url_name=_COMFY_DOCS_LINK_NAME,
            _type="ERROR",
            position=InfoBarPosition.TOP,
            duration=8000,
        )

    @staticmethod
    def _checkpoint_panel(panel: TagExportPanel) -> None:
        """Fan-in: export actions only request checkpoint; panel owns qconfig bags."""
        panel.checkpoint_panel_prefs()

    def _on_copy(self, panel: TagExportPanel):
        # prompt_text() dirty 时读 preview；clean 时读 TagPrompt 打包。与按钮 enable 同源。
        try:
            text = panel.prompt_text()
            if not str(text or "").strip():
                self._show_info(InfoBar.warning, "预览为空，无可复制内容", 2500, owner=panel)
                return
            clipboard = QApplication.clipboard()
            if clipboard is None:
                raise RuntimeError("QApplication.clipboard() is unavailable")
            clipboard.setText(text)
            self._show_info(InfoBar.success, "Prompt 已复制", 2000, owner=panel)
        finally:
            # SECTION 与导出是否成功无关；空预览 early-return 仍落盘（PRD R8）。
            self._checkpoint_panel(panel)

    def _on_imgpalace(self, panel: TagExportPanel):
        if self._send_in_flight:
            return
        # imgpalace_btn 已按 General body 非空 enable；槽内不再重复空选门控。
        body = panel.prompt_body_text()
        text = panel.prompt_text()
        self._send_in_flight = True
        panel.imgpalace_btn.setEnabled(False)
        try:
            if self._browser_opener is not None:
                self._browser_opener("raw-image", None)
            else:
                self._show_info(
                    InfoBar.warning,
                    "imgPalace 尚未就绪，请先配置 jsoneriPalaces",
                    3500,
                    owner=panel,
                )
            if self._job_sender is not None:
                self._job_sender(
                    post=panel.prompt.post,
                    tags_prompt=body,
                    identity=panel.prompt.identity(),
                    clipboard_text=text,
                    action=panel.selected_action_payload(),
                )
            else:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(text)
                self._show_info(
                    InfoBar.success,
                    "Prompt 已复制；提交到 imgPalace 尚未启用",
                    3500,
                    owner=panel,
                )
        finally:
            self._send_in_flight = False
            panel.imgpalace_btn.setEnabled(bool(panel.prompt_body_text().strip()))
            self._checkpoint_panel(panel)

    def _on_comfy_nl(self, panel: TagExportPanel):
        if self._send_in_flight or self._comfy_nl_in_flight:
            return
        # comfy_nl_btn 已按 instruction 非空 enable；AI 行可见性已保证 provider 配置。
        instruction = panel.comfy_nl_instruction()
        tag_context = panel.comfy_prompt_text()
        if not tag_context.strip():
            self._show_info(InfoBar.warning, "请先填写 Prompt", 2500, owner=panel)
            return

        provider = AiProviderConfigSession.instance().provider
        preset = panel.selected_comfy_unet()
        known = panel.comfy_known

        def task_func(*, progress_callback=None):
            pipeline = AnimaPromptPipeline(
                provider,
                proxies=getattr(script_conf, "proxies", None) or [],
            )
            return pipeline.run(
                tag_context=tag_context,
                nl_instruction=instruction,
                preset=preset,
                known=known,
            )

        def on_success(result):
            self._comfy_nl_in_flight = False
            if self._panel is not panel:
                return
            panel.set_comfy_nl_busy(False)
            # 质检门在 pipeline 里，且只有一道：不可用响应直接 raise 走 on_error，
            # 原 Prompt 自然不会被覆写。这里再验一次是把同一判定写两份，
            # 迟早两边漂移；也会把 pipeline 已做的规范化推倒重做。
            panel.replace_preview_text(result.text)
            if result.violations:
                logger.warning(f"AI 合并结果仍有格式违规（已规范化）：{result.violations}")
            self._show_info(InfoBar.success, "AI 已合并 Prompt", 2500, owner=panel)

        def on_error(message: str):
            self._comfy_nl_in_flight = False
            if self._panel is panel:
                panel.set_comfy_nl_busy(False)
            summary = summarize_error_message(message)
            self._show_info(
                InfoBar.error,
                f"AI Prompt 合并失败: {summary}",
                5000,
                owner=panel,
            )

        self._comfy_nl_in_flight = True
        panel.set_comfy_nl_busy(True)
        started = self.interface.task_mgr.execute_simple_task(
            task_func,
            success_callback=on_success,
            error_callback=on_error,
            tooltip_title="AI Prompt 合并中",
            tooltip_content="正在根据自然语言修改编辑器内容",
            show_success_info=False,
            show_error_info=False,
            task_id=_COMFY_NL_TASK_ID,
        )
        if not started:
            self._comfy_nl_in_flight = False
            panel.set_comfy_nl_busy(False)
        return started

    def _comfy_client(self) -> ComfyJobClient:
        """一个 controller 一份 ComfyJobClient，懒建后复用。

        每次提交新建就换了 client_id，而 ComfyUI 的事件是按 client_id 定向推送的，
        旧任务的进度/完成事件会全部收不到——任务永远停在「执行中」。
        Host 来自 conf；空 host 禁止静默 8188（配置即能力）。
        """
        host = configured_comfy_host()
        if not host:
            raise RuntimeError("Comfy host 未配置：请在 Script Settings → ComfyUI 填写 host")
        if self._comfy_job_client is not None:
            current_host = str(getattr(self._comfy_job_client, "_host", "") or "").rstrip("/")
            if current_host != host.rstrip("/"):
                self._comfy_job_client.close()
                self._comfy_job_client = None
                if self._comfy_jobs_dialog is not None:
                    self._comfy_jobs_dialog.close()
                    self._comfy_jobs_dialog = None
        if self._comfy_job_client is None:
            client = ComfyJobClient(host=host, parent=self)
            client.progress_updated.connect(self._on_comfy_progress)
            client.job_completed.connect(self._on_comfy_completed)
            client.job_failed.connect(self._on_comfy_failed)
            client.job_cancelled.connect(self._on_comfy_cancelled)
            self._comfy_job_client = client
        return self._comfy_job_client

    def open_comfy_jobs(self):
        """队列与历史进独立弹窗：面板已有 6 排控件，不能再往纵列上堆（PRD §4 版面约束）。

        comfy_row 可见性已保证 host 配置；此处不再二次 InfoBar 门控（§3.4.1）。
        出场前再卸一次 viewer 置顶，避免用户 pin 后把任务窗盖住。

        CGS007 / CGS008: ComfyJobsDialog parent MUST be ``self._panel`` (TagExportPanel).
        MUST NOT use interface / viewer. Agents keep rewriting this to interface — forbidden.
        """
        viewer = self._viewer or getattr(self.interface, "image_viewer", None)
        if viewer is not None:
            self._release_viewer_topmost(viewer)
        if self._comfy_jobs_dialog is None:
            # parent=TagExportPanel only (CGS008). panel_getter still resolves current panel
            # for tagsAttach after reopen; do not "fix" parent back to interface.
            self._comfy_jobs_dialog = ComfyJobsDialog(
                self._comfy_client(),
                parent=self._panel,
                panel_getter=lambda: self._panel,
            )
            self._comfy_jobs_dialog.destroyed.connect(self._on_comfy_jobs_dialog_destroyed)
            # 提交时 dialog 可能还没开：从 SQLite 快照灌进已有本地 job（唯一 SoR）。
            for job_id, preset in self._comfy_jobs.items():
                self._comfy_jobs_dialog.add_local_job(job_id, preset=preset)
        self._comfy_jobs_dialog.show()
        self._comfy_jobs_dialog.raise_()
        self._comfy_jobs_dialog.activateWindow()

    def _on_comfy_jobs_dialog_destroyed(self, *_args):
        self._comfy_jobs_dialog = None

    def _on_comfy(self, preset: str):
        """编辑器原文 → 本机 ComfyUI (ANIMA)，走常驻客户端（PRD Q9）。

        不再 QProcess 拉子进程：进度事件是 ws 定向推送、绑 client_id，
        一次性子进程既收不到也没处转发，用户只能看到一句「已提交」。
        也不再用 _send_in_flight 当互斥锁——连点两次就该排两条队（R20）。

        comfy_row 可见 + generate 按钮 enable 已保证 host 配置与 prompt 非空；
        槽内只保留 prompt 违规校验与提交本身（§3.4.1）。
        """
        panel = self._panel
        if panel is None:
            return
        prompt = panel.comfy_prompt_text()
        violations = panel.comfy_prompt_violations()
        errors = [token for token, reason in violations if reason == "model-ref"]
        if errors:
            self._show_info(
                InfoBar.error,
                "Prompt contains an unsupported model reference",
                3500,
                owner=panel,
            )
            self._checkpoint_panel(panel)
            return
        if violations:
            self._show_info(InfoBar.warning, "Prompt contains format warnings", 2500, owner=panel)

        settings = COMFY_UNET_PRESETS[preset]
        denoise = panel.selected_denoise()
        wd14 = panel.wd14_enabled()
        # 一张源图两种用途（WD14 读 tag / 重绘起始 latent），故只导出一次。
        # CGS007 §2.1: CurrentImg only; AttachImg is tags-only (never LoadImage pixels).
        source_image = (
            self._export_current_img_image(panel) if (wd14 or denoise < 1.0) else None
        )
        try:
            # comfy_row 可见已保证 host 配置；空 host 由 _comfy_client 抛 RuntimeError。
            host = configured_comfy_host()
            workflow = build_workflow(
                prompt,
                random.randint(0, 2 ** 32 - 1),
                896, 1152,
                settings["model"], settings["steps"],
                cfg=settings["cfg"], sampler=settings["sampler"],
                scheduler=settings["scheduler"], denoise=denoise,
                negative=settings["negative"],
                source_image=source_image, wd14=wd14,
                host=host,
            )
            job_id = self._comfy_client().submit(workflow)
        except Exception as error:
            logger.exception("ANIMA 提交失败")
            self._show_comfy_setup_error(
                f"ANIMA 提交失败：{error}（完整堆栈见日志）",
                owner=panel,
            )
            # SECTION 与提交成败无关，失败路径也落盘（PRD R8）。
            self._checkpoint_panel(panel)
            return
        finally:
            # 源图只是上传用的中转，workflow 里存的是上传后的引用名，本地这份即可回收。
            if source_image:
                Path(source_image).unlink(missing_ok=True)
        self._comfy_jobs[job_id] = preset
        denoise_percent = panel.denoise_slider.value()
        # CGS007: submit-time groups SoT for Comfy attach (Character/Artist/...).
        tag_groups = panel.snapshot_tag_groups()
        # UI 立刻登记卡；SQLite 异步落盘，成功后回填 dialog 缓存。
        if self._comfy_jobs_dialog is not None:
            self._comfy_jobs_dialog.add_local_job(
                job_id,
                preset=preset,
                editor_prompt=prompt,
                tag_groups=tag_groups,
            )
        self._async_upsert_comfy_snapshot(
            job_id,
            editor_prompt=prompt,
            unet=preset,
            denoise=denoise_percent,
            wd14=wd14,
            tag_groups=tag_groups,
        )
        panel.set_comfy_progress(node=f"排队中 · {preset}")
        self._show_info(
            InfoBar.success,
            f"ANIMA [{preset}] 已提交，进度见按钮与任务面板",
            2500,
            owner=panel,
        )
        self._checkpoint_panel(panel)

    def _async_upsert_comfy_snapshot(
        self,
        job_id: str,
        *,
        editor_prompt: str,
        unet: str,
        denoise: int,
        wd14: bool,
        tag_groups: object = None,
    ) -> None:
        """WAL write + prune off UI thread; remember_snapshot on success."""
        signals = _SnapshotUpsertSignals(self)

        def on_finished(row: object) -> None:
            dialog = self._comfy_jobs_dialog
            if dialog is not None and isinstance(row, dict):
                remember = getattr(dialog, "remember_snapshot", None)
                if callable(remember):
                    remember(row)

        def on_failed(message: str) -> None:
            logger.warning("async comfy snapshot upsert failed: {}", message)

        signals.finished.connect(on_finished)
        signals.failed.connect(on_failed)
        QThreadPool.globalInstance().start(
            _SnapshotUpsertRunnable(
                job_id=job_id,
                editor_prompt=editor_prompt,
                unet=unet,
                denoise=denoise,
                wd14=wd14,
                tag_groups=tag_groups,
                signals=signals,
            )
        )

    def _on_comfy_progress(self, job_id: str, value: int, maximum: int, node: str):
        panel = self._panel
        if panel is None or job_id not in self._comfy_jobs:
            return
        panel.set_comfy_progress(value, maximum, node)

    def _on_comfy_completed(self, job_id: str, result: object):
        preset = self._comfy_jobs.pop(job_id, None)
        if preset is None:
            return
        panel = self._panel
        if panel is None:
            return
        self._restore_comfy_button(panel)
        payload = result if isinstance(result, dict) else {}
        tags = ", ".join(payload.get("tags") or [])
        if tags:
            added = panel.merge_wd14_tags(tags)
            self._show_info(
                InfoBar.success,
                f"WD14 补全了 {added} 个 tag，已回灌编辑器",
                4000,
                owner=panel,
            )
        else:
            images = payload.get("images") or []
            self._show_info(
                InfoBar.success,
                f"ANIMA [{preset}] 出图完成，{len(images)} 张",
                3000,
                owner=panel,
            )

    def _on_comfy_failed(self, job_id: str, message: str):
        preset = self._comfy_jobs.pop(job_id, None)
        if preset is None:
            return
        logger.error(f"ANIMA 出图失败 job={job_id} preset={preset}\n{message}")
        panel = self._panel
        if panel is None:
            return
        self._restore_comfy_button(panel)
        tail = message.strip().splitlines()[0] if message.strip() else "未知错误"
        self._show_comfy_setup_error(
            f"ANIMA 出图失败：{tail}（完整堆栈见日志）",
            owner=panel,
        )

    def _on_comfy_cancelled(self, job_id: str):
        preset = self._comfy_jobs.pop(job_id, None)
        if preset is None:
            return
        panel = self._panel
        if panel is None:
            return
        self._restore_comfy_button(panel)
        self._show_info(InfoBar.warning, f"ANIMA [{preset}] 已取消", 3000, owner=panel)

    def _restore_comfy_button(self, panel):
        """还有任务在跑就别急着复位，否则并发两条时第一条完成会把第二条的进度抹掉。"""
        if not self._comfy_jobs:
            panel.clear_comfy_progress()
            return
        active_job_id = next(iter(self._comfy_jobs))
        active_job = self._comfy_client().job_state(active_job_id)
        panel.set_comfy_progress(
            active_job.get("progress_current", 0),
            active_job.get("progress_max", 0),
            active_job.get("display_node", "执行中"),
        )

    def _export_current_img_image(self, panel: TagExportPanel) -> str:
        """Dump session CurrentImg frozen pixmap to PNG for Comfy source_image.

        Source is panel.currentImg.pic only (frozen at panel open) — not the live
        viewer surface and not AttachImg. Used for WD14 and img2img LoadImage.
        """
        pixmap = panel.currentImg.pic
        if pixmap is None or pixmap.isNull():
            raise RuntimeError(
                "CurrentImg 没有可用图像，无法导出 Comfy source_image（WD14 / img2img）"
            )
        path = temp_p.joinpath("anima", f"wd14_src_{uuid.uuid4().hex}.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not pixmap.save(str(path), "PNG"):
            raise RuntimeError(f"Comfy source_image 写入失败: {path}")
        return str(path)
