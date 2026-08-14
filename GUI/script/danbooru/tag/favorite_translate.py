from __future__ import annotations

import typing as t

from PySide6 import QtCore
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from shiboken6 import isValid as qt_object_is_valid
from qfluentwidgets import (
    ComboBox, FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, PrimaryToolButton,
    StrongBodyLabel, TeachingTipTailPosition, TogglePushButton, ToolButton, TransparentToolButton,
)

from GUI.manager.async_task import summarize_error_message
from GUI.uic.qfluent.components import CustomTeachingTip
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.config.qc import danbooru_cfg
from utils.script import conf as script_conf
from utils.script.ai.capabilities.tag_translate import TagTranslatePipeline
from utils.script.ai.kernel import AiProviderConfigSession

if t.TYPE_CHECKING:
    from ..interface import DanbooruInterface
    from .favorites import DanbooruFavoriteManagerDialog

_TRANSLATE_TASK_ID = "danbooru_favorite_tag_translate"


class GroupChoicePanel(QWidget):
    COLUMNS = 3
    selection_changed = Signal(list)

    def __init__(self, group_names: list[str], selected_names: set[str], parent=None):
        super().__init__(parent)
        self.group_buttons: dict[str, TogglePushButton] = {}
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for offset, group_name in enumerate(group_names):
            button = TogglePushButton(self)
            button.setText(group_name)
            button.setToolTip(group_name)
            button.setCheckable(True)
            button.setChecked(group_name in selected_names)
            button.setMinimumWidth(100)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.toggled.connect(lambda *_args: self._emit_selection_changed())
            grid.addWidget(button, offset // self.COLUMNS, offset % self.COLUMNS)
            self.group_buttons[group_name] = button
        layout.addWidget(grid_host)

    def selected_group_names(self) -> list[str]:
        return [name for name, button in self.group_buttons.items() if button.isChecked()]

    def all_groups_selected(self) -> bool:
        return bool(self.group_buttons) and all(
            button.isChecked()
            for button in self.group_buttons.values()
        )

    def set_all_groups_selected(self, selected: bool):
        for button in self.group_buttons.values():
            button.setChecked(selected)
        self._emit_selection_changed()

    def _emit_selection_changed(self):
        self.selection_changed.emit(self.selected_group_names())


class FavoriteTagTranslateController(QtCore.QObject):
    """Host-side feature owner: progress chrome + background tag translate task."""

    def __init__(self, interface: "DanbooruInterface"):
        super().__init__(interface)
        self.interface = interface

    def begin(
        self,
        tags: list[str],
        *,
        engine: str = "danbooru",
        language: str = "zh",
        success_callback=None,
        error_callback=None,
    ) -> bool:
        session = AiProviderConfigSession.instance()
        if not session.is_configured():
            raise ValueError("AI provider is not configured")
        provider = session.provider
        tag_snapshot = [tag for tag in tags if str(tag or "").strip()]
        if not tag_snapshot:
            raise ValueError("empty tags")

        def task_func(*, progress_callback=None):
            def on_progress(progress):
                if progress_callback is None:
                    return
                total = max(1, int(progress.total or 0))
                done = max(0, int(progress.done or 0))
                percent = min(100, int((done * 100) / total))
                progress_callback(f"{percent}% ({done}/{total}) {progress.message or ''}".strip())

            pipeline = TagTranslatePipeline(
                provider,
                engine=engine,
                language=language,
                proxies=getattr(script_conf, "proxies", None) or [],
                batch_size=5,
                on_progress=on_progress,
            )
            return pipeline.run(tag_snapshot)

        def on_progress(message: str):
            text = str(message or "")
            done = 0
            total = len(tag_snapshot)
            if "(" in text and "/" in text and ")" in text:
                try:
                    fraction = text.split("(", 1)[1].split(")", 1)[0]
                    done_text, total_text = fraction.split("/", 1)
                    done = int(done_text)
                    total = int(total_text)
                except (ValueError, IndexError):
                    pass
            self._show_progress(done, total)

        def on_success(result):
            self._hide_progress()
            translations = dict(getattr(result, "translations", None) or {})
            failed = list(getattr(result, "failed_tags", None) or [])
            skipped = list(getattr(result, "skipped_no_evidence", None) or [])
            if translations:
                danbooru_cfg.merge_translate_map(translations)
            # Translate map is global completer display data; push via favorites dirty path
            # (zoom-pattern: active-only rebuild, hidden tabs resync on activation).
            self.interface._invalidate_favorites()
            ok_count = len(translations)
            fail_count = len(failed)
            skip_count = len(skipped)
            content = f"标签翻译完成: 成功 {ok_count}/{len(tag_snapshot)}"
            if fail_count:
                content = f"{content}, 失败 {fail_count}"
            if skip_count:
                content = f"{content}, 无证据跳过 {skip_count}"
            factory = InfoBar.success if ok_count else InfoBar.warning
            self.interface._show_info(factory, content, duration=5000)
            if callable(success_callback):
                success_callback(result)

        def on_error(message: str):
            self._hide_progress()
            summary = summarize_error_message(message)
            self.interface._show_info(InfoBar.error, f"标签翻译失败: {summary}", duration=5000)
            if callable(error_callback):
                error_callback(summary)

        self._show_progress(0, len(tag_snapshot))
        return self.interface.task_mgr.execute_simple_task(
            task_func,
            success_callback=on_success,
            error_callback=on_error,
            progress_callback=on_progress,
            tooltip_title="标签翻译中",
            tooltip_content="搜索引擎 + LLM",
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=_TRANSLATE_TASK_ID,
        )

    def _show_progress(self, done: int = 0, total: int = 0):
        host = self.interface
        host.favMgrBtn.hide()
        host.favTranslateRingHost.show()
        if total > 0:
            percent = min(100, int((done * 100) / total))
            host.favTranslateRing.setValue(percent)
        else:
            host.favTranslateRing.setValue(0)
        tip = f"翻译中 {done}/{total}" if total else "翻译中"
        host.favTranslateRingHost.setToolTip(tip)
        host.favTranslateRing.setToolTip(tip)
        host.favTranslateIndeterminateRing.setToolTip(tip)
        if not host.favTranslateIndeterminateRing.isVisible():
            host.favTranslateIndeterminateRing.show()
        host.favTranslateIndeterminateRing.start()

    def _hide_progress(self):
        host = self.interface
        host.favTranslateIndeterminateRing.stop()
        host.favTranslateIndeterminateRing.hide()
        host.favTranslateRingHost.hide()
        host.favTranslateRing.setValue(0)
        host.favTranslateRingHost.setToolTip("")
        host.favTranslateRing.setToolTip("")
        host.favTranslateIndeterminateRing.setToolTip("")
        host.favMgrBtn.show()


class FavoriteTagTranslateDialogSession(QtCore.QObject):
    """Dialog-side feature owner: translate chrome, editor, group pick, run launch."""

    def __init__(self, dialog: "DanbooruFavoriteManagerDialog"):
        super().__init__(dialog)
        self.dialog = dialog
        self.cache: dict[str, str] = dict(danbooru_cfg.get_translate_map())
        self.active_groups: set[str] = set(dialog._groups_state.group_names())
        self._group_choice_tip = None
        self._running = False
        self.active_editor_origin: str | None = None
        self._ai_provider_session = AiProviderConfigSession.instance()
        self._build_chrome()
        self._wire()
        self._ai_provider_session.state_changed.connect(self._on_ai_provider_state_changed)
        self.dialog.destroyed.connect(self._detach_ai_provider_session)
        self.sync_entry_visibility()

    def _build_chrome(self):
        dialog = self.dialog
        self.translateBtnGroup = QWidget(dialog.custom_frame)
        group_layout = QHBoxLayout(self.translateBtnGroup)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(6)
        self.translateBtn = TransparentToolButton(CgsIcon.SCRIPT_TRANSLATE_AI, self.translateBtnGroup)
        self.translateBtn.setToolTip("展开标签翻译")
        self.groupSelectBtn = ToolButton(FIF.MENU, self.translateBtnGroup)
        self.groupSelectBtn.setToolTip("选择要翻译的收藏组")
        self.groupSelectBtn.hide()
        self.searchSiteBox = ComboBox(self.translateBtnGroup)
        self.searchSiteBox.addItem("Danbooru Wiki", userData="danbooru")
        self.searchSiteBox.addItem("萌娘百科", userData="moegirl")
        self.searchSiteBox.addItem("百度", userData="baidu")
        self.searchSiteBox.addItem("Google", userData="google")
        self.searchSiteBox.addItem("Bing", userData="bing")
        self.searchSiteBox.setMinimumWidth(108)
        self.searchSiteBox.hide()
        self.languageBox = ComboBox(self.translateBtnGroup)
        self.languageBox.addItem("中文", userData="zh")
        self.languageBox.addItem("日本語", userData="ja")
        self.languageBox.setMinimumWidth(88)
        self.languageBox.hide()
        self.runTranslateBtn = PrimaryToolButton(CgsIcon.SCRIPT_RUN, self.translateBtnGroup)
        self.runTranslateBtn.setToolTip("开始翻译")
        self.runTranslateBtn.hide()
        group_layout.addWidget(self.translateBtn)
        group_layout.addWidget(self.groupSelectBtn)
        group_layout.addWidget(self.searchSiteBox)
        group_layout.addWidget(self.languageBox)
        group_layout.addWidget(self.runTranslateBtn)
        self.translateBtnGroup.hide()

        self.oriTagStrongLabel = StrongBodyLabel("origin:", dialog.custom_frame)
        self.oriTagLabel = StrongBodyLabel("-", dialog.custom_frame)
        self.oriTagLabel.setMinimumWidth(120)
        self.translatedTagLabel = StrongBodyLabel("display:", dialog.custom_frame)
        self.translatedTagInput = LineEdit(dialog.custom_frame)
        self.translatedTagInput.setClearButtonEnabled(True)
        self.translatedTagInput.setPlaceholderText("显示名")
        self.translateSvBtn = ToolButton(CgsIcon.SCRIPT_GENERATE, dialog.custom_frame)
        self.translateSvBtn.setToolTip("保存当前显示名到缓存")

    def _wire(self):
        self.translateBtn.clicked.connect(self.expand_controls)
        self.groupSelectBtn.clicked.connect(self.show_group_choice_tip)
        self.runTranslateBtn.clicked.connect(self.run_translate)
        self.translateSvBtn.clicked.connect(self.save_active_translation)

    def install_into_dialog(self):
        dialog = self.dialog
        dialog.titleHeadRow.addWidget(self.translateBtnGroup)
        dialog.translateEditRow.addWidget(self.oriTagStrongLabel)
        dialog.translateEditRow.addWidget(self.oriTagLabel, 1)
        dialog.translateEditRow.addWidget(self.translatedTagLabel)
        dialog.translateEditRow.addWidget(self.translatedTagInput, 1)
        dialog.translateEditRow.addWidget(self.translateSvBtn)

    def display_tag(self, origin: str) -> str:
        canonical = danbooru_cfg.canonicalize_term(origin)
        if not canonical:
            return ""
        return self.cache.get(canonical) or canonical

    def drop_cache_keys(self, tags: t.Iterable[str], *, force: bool = False):
        living_tags = set() if force else self.dialog._groups_state.all_terms()
        dropped: list[str] = []
        for raw_tag in tags:
            canonical = danbooru_cfg.canonicalize_term(str(raw_tag))
            if not canonical:
                continue
            if force or canonical not in living_tags:
                self.cache.pop(canonical, None)
                dropped.append(canonical)
        if dropped:
            danbooru_cfg.drop_translate_keys(dropped)

    def _on_ai_provider_state_changed(self, _previous, _current):
        self.sync_entry_visibility()

    def _detach_ai_provider_session(self, *_args):
        session = getattr(self, "_ai_provider_session", None)
        if session is None:
            return
        try:
            session.state_changed.disconnect(self._on_ai_provider_state_changed)
        except (RuntimeError, TypeError):
            pass

    def sync_entry_visibility(self):
        """LLM provider presence = translate chrome visibility（与 comfy_nl_row 同状态机）。"""
        session = getattr(self, "_ai_provider_session", None)
        configured = session.is_configured() if session is not None else False
        self.translateBtnGroup.setVisible(configured)
        if not configured:
            self.translateBtn.show()
            self.groupSelectBtn.hide()
            self.searchSiteBox.hide()
            self.languageBox.hide()
            self.runTranslateBtn.hide()
            if self._group_choice_tip is not None:
                self._group_choice_tip.close()
                self._group_choice_tip = None

    def expand_controls(self):
        self.translateBtn.hide()
        self.groupSelectBtn.show()
        self.searchSiteBox.show()
        self.languageBox.show()
        self.runTranslateBtn.show()
        available = set(self.dialog._groups_state.group_names())
        if not self.active_groups:
            self.active_groups = set(available)
        else:
            self.active_groups &= available
            if not self.active_groups:
                self.active_groups = set(available)

    def apply_group_selection(self, selected_names: t.Iterable[str], *, fallback_all: bool = False):
        available = set(self.dialog._groups_state.group_names())
        selected = {
            name
            for raw_name in selected_names
            if (name := str(raw_name or "").strip()) and name in available
        }
        if selected:
            self.active_groups = selected
            return selected
        if fallback_all:
            self.active_groups = set(available)
            return set(available)
        self.active_groups = set()
        return set()

    def sync_groups_from_open_tip(self):
        tip = self._group_choice_tip
        if tip is None or not qt_object_is_valid(tip):
            return
        panel = getattr(tip, "_translate_group_panel", None)
        if panel is None or not qt_object_is_valid(panel):
            return
        self.apply_group_selection(panel.selected_group_names(), fallback_all=False)

    def show_group_choice_tip(self):
        dialog = self.dialog
        if self._group_choice_tip is not None:
            self._group_choice_tip.close()
            self._group_choice_tip = None
        group_names = dialog._groups_state.group_names()
        if not group_names:
            return InfoBar.warning(
                title="", content="暂无自定义收藏组",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=dialog,
            )
        selected = set(self.active_groups) & set(group_names)
        if not selected:
            selected = set(group_names)
            self.active_groups = set(selected)
        panel = GroupChoicePanel(group_names, selected, dialog)
        select_all_button = TransparentToolButton(FIF.CHECKBOX, dialog)
        select_all_button.clicked.connect(lambda: panel.set_all_groups_selected(not panel.all_groups_selected()))
        tip = CustomTeachingTip.create(
            [panel],
            target=self.groupSelectBtn,
            parent=dialog,
            closeButtonBelows=(select_all_button,),
            tailPosition=TeachingTipTailPosition.BOTTOM,
        )
        tip._translate_group_panel = panel  # type: ignore[attr-defined]
        self._group_choice_tip = tip
        tip.destroyed.connect(lambda *_args, current=tip: self._clear_group_choice_tip(current))

        def on_selection_changed(names: list[str]):
            self.apply_group_selection(names, fallback_all=False)

        def on_closed():
            if qt_object_is_valid(panel):
                self.apply_group_selection(panel.selected_group_names(), fallback_all=False)

        panel.selection_changed.connect(on_selection_changed)
        tip.destroyed.connect(lambda *_args: on_closed())

    def _clear_group_choice_tip(self, tip):
        if self._group_choice_tip is tip:
            self._group_choice_tip = None

    def clear_editor(self):
        self.active_editor_origin = None
        self.oriTagLabel.setText("-")
        self.translatedTagInput.setText("")

    def bind_editor(self, origin: str | None):
        canonical = danbooru_cfg.canonicalize_term(origin or "")
        if not canonical:
            self.clear_editor()
            return
        self.active_editor_origin = canonical
        self.oriTagLabel.setText(canonical)
        self.translatedTagInput.setText(self.cache.get(canonical, ""))

    def save_active_translation(self):
        dialog = self.dialog
        origin = self.active_editor_origin
        if not origin:
            return InfoBar.warning(
                title="", content="请先选中自定义区中的标签",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=dialog,
            )
        translated = danbooru_cfg.canonicalize_term(self.translatedTagInput.text())
        if translated:
            self.cache[origin] = translated
            danbooru_cfg.merge_translate_map({origin: translated})
        else:
            self.cache.pop(origin, None)
            danbooru_cfg.drop_translate_keys([origin])
        self.apply_cache_to_tree({origin: self.display_tag(origin)})
        InfoBar.success(
            title="", content="已保存显示名",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=1800, parent=dialog,
        )

    def apply_cache_to_tree(self, origins: dict[str, str] | None = None):
        dialog = self.dialog
        display_map = origins
        for group_index in range(dialog.custom_tree.topLevelItemCount()):
            group_item = dialog.custom_tree.topLevelItem(group_index)
            for child_index in range(group_item.childCount()):
                tag_item = group_item.child(child_index)
                meta = dialog._item_meta(tag_item)
                if meta.get("kind") != "tag":
                    continue
                origin = meta.get("tag", "")
                if not origin:
                    continue
                if display_map is not None and origin not in display_map:
                    continue
                row = dialog.custom_tree.itemWidget(tag_item, 0)
                set_display = getattr(row, "set_display_text", None)
                if not callable(set_display):
                    continue
                text = display_map[origin] if display_map is not None else self.display_tag(origin)
                set_display(text)
                tag_item.setSizeHint(0, QSize(0, row.height()))

    def snapshot_tags(self) -> list[str]:
        selected_groups = set(self.active_groups)
        if not selected_groups:
            return []
        tags: list[str] = []
        seen: set[str] = set()
        for group in self.dialog._groups_state.custom_groups:
            if group.name not in selected_groups:
                continue
            for tag in group.tags:
                canonical = danbooru_cfg.canonicalize_term(tag)
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                tags.append(canonical)
        return tags

    def existing_translated_origins(self) -> set[str]:
        self.cache.update(danbooru_cfg.get_translate_map())
        existing: set[str] = set()
        merged = dict(danbooru_cfg.get_translate_map())
        merged.update(self.cache)
        for raw_origin, raw_translated in merged.items():
            origin = danbooru_cfg.canonicalize_term(str(raw_origin))
            translated = danbooru_cfg.canonicalize_term(str(raw_translated))
            if origin and translated:
                existing.add(origin)
        return existing

    def pending_tags(self, snapshot_tags: list[str]) -> tuple[list[str], int]:
        snapshot_ordered: list[str] = []
        seen: set[str] = set()
        for raw_tag in snapshot_tags:
            canonical = danbooru_cfg.canonicalize_term(raw_tag)
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            snapshot_ordered.append(canonical)
        snapshot_set = set(snapshot_ordered)
        already_translated = self.existing_translated_origins()
        pending_set = snapshot_set - already_translated
        pending_ordered = [tag for tag in snapshot_ordered if tag in pending_set]
        skipped_already = len(snapshot_ordered) - len(pending_ordered)
        return pending_ordered, skipped_already

    def on_groups_changed(self):
        available = set(self.dialog._groups_state.group_names())
        self.active_groups = (self.active_groups & available) or set(available)

    def prune_to_living(self) -> dict[str, str]:
        living_tags = self.dialog._groups_state.all_terms()
        pruned = {
            origin: translated
            for origin, translated in self.cache.items()
            if origin in living_tags
        }
        self.cache = pruned
        return pruned

    def run_translate(self):
        dialog = self.dialog
        if self._running:
            return InfoBar.warning(
                title="", content="翻译任务进行中",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=dialog,
            )
        self.sync_groups_from_open_tip()
        selected_groups = sorted(self.active_groups)
        snapshot_tags = self.snapshot_tags()
        if not selected_groups:
            return InfoBar.warning(
                title="", content="请先用组选择按钮勾选至少一个收藏组",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=dialog,
            )
        if not snapshot_tags:
            return InfoBar.warning(
                title="", content=f"所选组无标签: {', '.join(selected_groups)}",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=dialog,
            )
        tags, skipped_already = self.pending_tags(snapshot_tags)
        if not tags:
            return InfoBar.info(
                title="",
                content=(
                    f"所选组共 {len(snapshot_tags)} 个标签均已有译文，已跳过（跳过 {skipped_already}）"
                ),
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3500, parent=dialog,
            )
        engine = self.searchSiteBox.currentData() or "danbooru"
        language = self.languageBox.currentData() or "zh"

        def on_success(result):
            if not qt_object_is_valid(dialog):
                return
            self._running = False
            self.runTranslateBtn.setEnabled(True)
            translations = getattr(result, "translations", None) or {}
            for origin, translated in translations.items():
                canonical = danbooru_cfg.canonicalize_term(origin)
                display = danbooru_cfg.canonicalize_term(translated)
                if canonical and display:
                    self.cache[canonical] = display
            self.cache.update(danbooru_cfg.get_translate_map())
            self.apply_cache_to_tree()
            if self.active_editor_origin:
                self.bind_editor(self.active_editor_origin)

        def on_error(message: str):
            _ = message
            if not qt_object_is_valid(dialog):
                return
            self._running = False
            self.runTranslateBtn.setEnabled(True)

        self._running = True
        self.runTranslateBtn.setEnabled(False)
        total_tags = len(tags)
        try:
            started = dialog.parent().favorite_translate.begin(
                tags,
                engine=str(engine),
                language=str(language),
                success_callback=on_success,
                error_callback=on_error,
            )
        except Exception as exc:
            self._running = False
            self.runTranslateBtn.setEnabled(True)
            return InfoBar.error(
                title="", content=f"翻译启动失败: {exc}",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=dialog,
            )
        if not started:
            self._running = False
            self.runTranslateBtn.setEnabled(True)
            return InfoBar.warning(
                title="", content="翻译任务未能启动（可能已在运行）",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=dialog,
            )
        group_preview = ", ".join(selected_groups)
        if len(group_preview) > 30:
            group_preview = f"{group_preview} …"
        content = (
            f"已提交翻译任务: {len(selected_groups)} 组（{group_preview}），"
            f"待译 {total_tags}/{len(snapshot_tags)}"
        )
        if skipped_already:
            content = f"{content}（已跳过已有译文 {skipped_already}）"
        InfoBar.info(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4000,
            parent=dialog,
        )
