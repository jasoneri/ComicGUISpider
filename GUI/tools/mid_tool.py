# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QFrame, QDialog, QPushButton, QComboBox
)
from qfluentwidgets import (
    CardWidget, SwitchButton, PushButton, PrimaryPushButton,
    TransparentToolButton, FluentIcon as FIF, BodyLabel,
    SubtitleLabel, StrongBodyLabel, ComboBox, InfoBar, InfoBarPosition
)

from utils.middleware import (
    CGSMidManager, WorkflowDefinition, MiddlewareDefinition,
    TimelineStage, SCHEMA_VERSION
)
from utils.middleware.providers import PresetProvider
from utils.middleware.serialization import workflow_from_dict


class RuleBlockCard(CardWidget):
    clicked = pyqtSignal(object)

    def __init__(self, definition: MiddlewareDefinition, parent=None):
        super().__init__(parent)
        self.definition = definition
        self.setFixedSize(280, 60)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.enable_switch = SwitchButton()
        self.enable_switch.setChecked(self.definition.enabled)
        self.enable_switch.checkedChanged.connect(self._on_enable_changed)
        layout.addWidget(self.enable_switch)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = StrongBodyLabel(self.definition.name)
        info_layout.addWidget(name_label)

        type_label = BodyLabel(f"#{self.definition.priority} {self.definition.type}")
        type_label.setStyleSheet("color: #666;")
        info_layout.addWidget(type_label)

        layout.addLayout(info_layout)
        layout.addStretch()

    def _on_enable_changed(self, checked: bool):
        self.definition.enabled = checked

    def mouseDoubleClickEvent(self, event):
        self.clicked.emit(self.definition)
        super().mouseDoubleClickEvent(event)


class LaneWidget(QFrame):
    rule_added = pyqtSignal(object)
    rule_clicked = pyqtSignal(object)

    STAGE_LABELS = {
        TimelineStage.WAIT_BOOK_DECISION: "选择书本",
        TimelineStage.WAIT_EP_DECISION: "选择章节",
        TimelineStage.POSTPROCESSING: "后处理",
    }

    def __init__(self, stage: TimelineStage, parent=None):
        super().__init__(parent)
        self.stage = stage
        self.rules = []
        self._init_ui()

    def _init_ui(self):
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet(
            "LaneWidget { background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        stage_label = SubtitleLabel(self.STAGE_LABELS.get(self.stage, f"Stage {self.stage}"))
        header.addWidget(stage_label)
        header.addStretch()
        layout.addLayout(header)

        self.rules_container = QVBoxLayout()
        self.rules_container.setSpacing(6)
        layout.addLayout(self.rules_container)
        layout.addStretch()

    def add_rule(self, definition: MiddlewareDefinition):
        card = RuleBlockCard(definition, self)
        card.clicked.connect(self.rule_clicked)
        self.rules.append(definition)
        self.rules_container.addWidget(card)

    def clear_rules(self):
        for i in reversed(range(self.rules_container.count())):
            item = self.rules_container.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
        self.rules.clear()


class WorkflowCanvas(QWidget):
    rule_clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lanes = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self.container_layout = QHBoxLayout(container)
        self.container_layout.setSpacing(16)

        self._create_timeline_nodes()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _create_timeline_nodes(self):
        stages = [
            ("搜索", TimelineStage.SEARCHING),
            ("选择书本", TimelineStage.WAIT_BOOK_DECISION),
            ("选择章节", TimelineStage.WAIT_EP_DECISION),
            ("下载", TimelineStage.DOWNLOADING),
            ("后处理", TimelineStage.POSTPROCESSING),
            ("完成", TimelineStage.FINISHED),
        ]

        for label, stage in stages:
            node = self._create_node(label)
            self.container_layout.addWidget(node)

            if stage in (TimelineStage.WAIT_BOOK_DECISION, TimelineStage.WAIT_EP_DECISION, TimelineStage.POSTPROCESSING):
                lane = LaneWidget(stage)
                lane.rule_clicked.connect(self.rule_clicked)
                self.lanes[stage] = lane
                self.container_layout.addWidget(lane)

    def _create_node(self, label: str) -> QWidget:
        node = QFrame()
        node.setFixedSize(80, 40)
        node.setStyleSheet(
            "QFrame { background: #0078d4; border-radius: 6px; }"
        )
        layout = QVBoxLayout(node)
        layout.setContentsMargins(4, 4, 4, 4)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: white; font-weight: bold;")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        return node

    def update_workflow(self, workflow: WorkflowDefinition):
        for lane in self.lanes.values():
            lane.clear_rules()

        for mw in workflow.middlewares:
            for stage_val in mw.supported_stages:
                stage = TimelineStage(stage_val)
                if stage in self.lanes:
                    self.lanes[stage].add_rule(mw)


class PropertyPanel(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_definition = None
        self._init_ui()

    def _init_ui(self):
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.title_label = SubtitleLabel("属性面板")
        layout.addWidget(self.title_label)
        layout.addSpacing(12)

        self.info_label = BodyLabel("选择一个规则查看属性")
        layout.addWidget(self.info_label)
        layout.addStretch()

    def show_definition(self, definition: MiddlewareDefinition):
        self.current_definition = definition
        self._update_content()

    def _update_content(self):
        for i in reversed(range(self.layout().count())):
            item = self.layout().itemAt(i)
            if item.widget() and item.widget() not in (self.title_label, self.info_label):
                item.widget().deleteLater()

        if self.current_definition is None:
            self.info_label.setText("选择一个规则查看属性")
            return

        self.info_label.setText(f"名称: {self.current_definition.name}")
        self.info_label.setStyleSheet("")

        details = QVBoxLayout()
        details.setSpacing(8)

        info_rows = [
            ("Provider", self._get_provider_info()),
            ("Priority", str(self.current_definition.priority)),
            ("Type", self.current_definition.type),
            ("Enabled", "是" if self.current_definition.enabled else "否"),
        ]

        for key, value in info_rows:
            row = QHBoxLayout()
            key_label = BodyLabel(f"{key}:")
            key_label.setStyleSheet("font-weight: bold;")
            val_label = BodyLabel(value)
            row.addWidget(key_label)
            row.addWidget(val_label)
            row.addStretch()
            details.addLayout(row)

        self.layout().insertLayout(2, details)

    def _get_provider_info(self) -> str:
        if self.current_definition.id.startswith("preset:"):
            return "Built-in 🛡️"
        elif self.current_definition.id.startswith("user:"):
            return "My Rules 👤"
        else:
            return "Community ☁️"


class RuleLibraryPanel(CardWidget):
    rule_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        self.setFixedWidth(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        title = SubtitleLabel("规则库")
        layout.addWidget(title)
        layout.addSpacing(8)

        provider = PresetProvider()
        self.available_rules = provider.list_available()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)

        for rule in self.available_rules:
            btn = PushButton(f"{rule.name}", self)
            btn.clicked.connect(lambda checked, r=rule: self.rule_selected.emit(r))
            container_layout.addWidget(btn)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)


class TestWorkflowDialog(QDialog):
    def __init__(self, workflow: WorkflowDefinition, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("模拟执行")
        self.setFixedSize(500, 400)

        layout = QVBoxLayout(self)

        info = BodyLabel(
            f"工作流: {self.workflow.workflow_name}\n"
            f"流程类型: {self.workflow.flow_type}\n"
            f"规则数量: {len(self.workflow.middlewares)}"
        )
        layout.addWidget(info)
        layout.addSpacing(12)

        self.result_label = BodyLabel("点击运行开始模拟")
        layout.addWidget(self.result_label)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        run_btn = PrimaryPushButton("运行", self)
        run_btn.clicked.connect(self._on_run)
        close_btn = PushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(run_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _on_run(self):
        results = []
        for mw in self.workflow.middlewares:
            if mw.enabled:
                results.append(f"  ✓ {mw.name} (优先级: {mw.priority})")
            else:
                results.append(f"  ✗ {mw.name} (已禁用)")

        self.result_label.setText(
            "执行结果:\n" +
            "\n".join(results) +
            "\n\n模拟完成。未发现错误。"
        )


class MidToolInterface(QWidget):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.workflow = WorkflowDefinition(workflow_name="Auto Download Latest")
        self._init_ui()
        self._load_default_workflow()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()

        self.title_label = SubtitleLabel(f"Workflow Editor: \"{self.workflow.workflow_name}\"")
        header.addWidget(self.title_label)
        header.addStretch()

        self.enable_switch = SwitchButton()
        self.enable_switch.setText("启用自动化")
        self.enable_switch.setChecked(False)
        self.enable_switch.checkedChanged.connect(self._on_enable_changed)
        header.addWidget(self.enable_switch)

        save_btn = PushButton("保存", self)
        save_btn.clicked.connect(self._on_save)
        header.addWidget(save_btn)

        test_btn = PushButton("测试", self)
        test_btn.clicked.connect(self._on_test)
        header.addWidget(test_btn)

        layout.addLayout(header)

        config_row = QHBoxLayout()
        config_row.addWidget(BodyLabel("流程类型:"))
        self.flow_combo = ComboBox()
        self.flow_combo.addItems(["自动", "EP Flow", "Book Flow"])
        self.flow_combo.setCurrentIndex(0)
        self.flow_combo.currentIndexChanged.connect(self._on_flow_changed)
        config_row.addWidget(self.flow_combo)
        config_row.addStretch()
        layout.addLayout(config_row)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        self.canvas = WorkflowCanvas()
        self.canvas.rule_clicked.connect(self._on_rule_clicked)
        content_layout.addWidget(self.canvas, stretch=3)

        self.library = RuleLibraryPanel()
        self.library.rule_selected.connect(self._on_rule_selected)
        content_layout.addWidget(self.library, stretch=1)

        layout.addLayout(content_layout, stretch=1)

    def _load_default_workflow(self):
        provider = PresetProvider()
        self.workflow.middlewares = provider.list_available()[:2]
        self.canvas.update_workflow(self.workflow)

    def _on_enable_changed(self, checked: bool):
        mgr = getattr(self.gui, "mid_mgr", None)
        if mgr:
            mgr.set_enabled(checked)

    def _on_save(self):
        from pathlib import Path
        workflow_dir = Path.home() / ".comicguispider" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_file = workflow_dir / f"{self.workflow.workflow_name}.json"
        workflow_file.write_text(self.workflow.to_json(), encoding="utf-8")
        InfoBar.success("保存成功", f"工作流已保存到 {workflow_file}", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _on_test(self):
        dlg = TestWorkflowDialog(self.workflow, self)
        dlg.exec_()

    def _on_rule_clicked(self, definition: MiddlewareDefinition):
        pass

    def _on_rule_selected(self, definition: MiddlewareDefinition):
        self.workflow.middlewares.append(definition)
        self.canvas.update_workflow(self.workflow)

    def _on_flow_changed(self, index: int):
        flow_types = ["auto", "ep", "book"]
        self.workflow.flow_type = flow_types[index]
