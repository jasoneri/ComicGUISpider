# -*- coding: utf-8 -*-
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame
)
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon as FIF, BodyLabel,
    SubtitleLabel, StrongBodyLabel, CompactSpinBox, LineEdit, SwitchButton
)
from utils.middleware import MiddlewareDefinition


class RulePanel(CardWidget):
    rule_selected = Signal(object, str)

    LANE_HEADERS = {
        "SITE": "选择网站 (A)",
        "SEARCH": "输入搜索 (B)",
        "BOOK": "选择书本 (C)",
        "EP": "选择章节 (D)",
        "POSTPROCESSING": "后处理 (E)",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.rule_rows: dict[str, QWidget] = {}
        self._lane_groups: dict[str, QVBoxLayout] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = SubtitleLabel("规则库")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setSpacing(4)

        for lane_id, header_text in self.LANE_HEADERS.items():
            group_widget = QWidget()
            group_layout = QVBoxLayout(group_widget)
            group_layout.setContentsMargins(4,4,4,4)
            group_layout.setSpacing(8)

            header = StrongBodyLabel(header_text)
            group_layout.addWidget(header)

            self._lane_groups[lane_id] = group_layout
            self._container_layout.addWidget(group_widget)

        self._container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def populate(self, rules: list[MiddlewareDefinition]):
        for rule in rules:
            if not rule.allowed_lanes:
                continue
            primary_lane = rule.allowed_lanes[0]
            if primary_lane not in self._lane_groups:
                continue

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 0, 4, 0)

            name_label = BodyLabel(rule.name)
            row_layout.addWidget(name_label)
            row_layout.addStretch()

            add_btn = TransparentToolButton(FIF.ADD, row)
            add_btn.setFixedSize(24, 24)
            add_btn.clicked.connect(lambda _, r=rule, l=primary_lane: self.rule_selected.emit(r, l))
            row_layout.addWidget(add_btn)

            self._lane_groups[primary_lane].addWidget(row)
            self.rule_rows[rule.id] = row

    def hide_rule(self, rule_id: str):
        if rule_id in self.rule_rows:
            self.rule_rows[rule_id].setVisible(False)

    def show_rule(self, rule_id: str):
        if rule_id in self.rule_rows:
            self.rule_rows[rule_id].setVisible(True)


class DetailPanel(CardWidget):
    back_requested = Signal()
    param_changed = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self._definition = None
        self._param_widgets: dict[str, QWidget] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12,12,12,12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        back_btn = TransparentToolButton(FIF.RETURN, self)
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)

        self._title = SubtitleLabel("规则详情")
        header.addWidget(self._title)
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self._content = QVBoxLayout(container)
        self._content.setContentsMargins(4, 8, 4, 4)
        self._content.setSpacing(0)
        self._content.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _clear_content(self):
        while self._content.count() > 1:
            item = self._content.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._param_widgets.clear()

    def show_definition(self, definition: MiddlewareDefinition):
        self._definition = definition
        self._title.setText(definition.name)
        self._clear_content()

        fields = [
            ("标签", definition.label or "-"),
            ("类型", definition.type),
            ("优先级", str(definition.priority)),
            ("描述", definition.desc),
        ]

        for key, value in fields:
            if key == "描述" and not value:
                continue
            row = QHBoxLayout()
            row.setContentsMargins(8,4,8,4)
            key_lbl = BodyLabel(f"{key}:")
            key_lbl.setStyleSheet("font-weight: bold;")
            val_lbl = BodyLabel(value)
            row.addWidget(key_lbl)
            row.addWidget(val_lbl)
            row.addStretch()

            container = QWidget()
            container.setLayout(row)
            self._content.insertWidget(self._content.count() - 1, container)
            
        if definition.param_schema:
            separator_container = QWidget()
            separator_layout = QVBoxLayout(separator_container)
            separator_layout.setContentsMargins(0, 4, 0, 4)
            separator_layout.setSpacing(4)

            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Sunken)
            separator_layout.addWidget(separator)

            params_header = BodyLabel("参数:")
            params_header.setStyleSheet("font-weight: bold;")
            separator_layout.addWidget(params_header)

            self._content.insertWidget(self._content.count() - 1, separator_container)

            for key, schema in definition.param_schema.items():
                value = definition.params.get(key, schema.get('default'))
                widget = self._create_param_widget(key, schema, value)
                self._content.insertWidget(self._content.count() - 1, widget)

    def _create_param_widget(self, key: str, schema: dict, value) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(8, 2, 4, 2)

        label = BodyLabel(f"{key}:")
        row.addWidget(label)

        param_type = schema.get('type', 'str')
        if param_type == 'int':
            spin = CompactSpinBox()
            spin.setRange(schema.get('min', 0), schema.get('max', 99))
            spin.setValue(value if value is not None else schema.get('default', 0))
            spin.valueChanged.connect(lambda v, k=key: self._on_param_value_changed(k, v))
            row.addWidget(spin)
            self._param_widgets[key] = spin
        elif param_type == 'bool':
            switch = SwitchButton()
            switch.setChecked(bool(value) if value is not None else schema.get('default', False))
            switch.checkedChanged.connect(lambda v, k=key: self._on_param_value_changed(k, v))
            row.addWidget(switch)
            self._param_widgets[key] = switch
        else:
            edit = LineEdit()
            edit.setText(str(value) if value is not None else str(schema.get('default', '')))
            edit.textChanged.connect(lambda v, k=key: self._on_param_value_changed(k, v))
            row.addWidget(edit)
            self._param_widgets[key] = edit

        row.addStretch()
        return container

    def _on_param_value_changed(self, key: str, value):
        if self._definition:
            self._definition.params[key] = value
            self.param_changed.emit(key, value)
