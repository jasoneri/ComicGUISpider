from urllib.parse import urlsplit

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCompleter, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, PasswordLineEdit, PrimaryToolButton, PushButton

from utils.config.qc import cgs_cfg
from GUI.uic.qfluent.components.icons import CgsIcon


class WebdavSettings(QWidget):
    changed = Signal()
    saved = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        # 连接配置保存即可用；历史遗留的 enabled=False 就地自愈（竞品均无配置级上传开关）。
        self.saved_config = {**cgs_cfg.webdav.get(), "enabled": True}
        self._root = str(self.saved_config.get("root") or "/")
        self.endpoint_edit = LineEdit(self)
        self.user_edit = LineEdit(self)
        self.password_edit = PasswordLineEdit(self)
        self.svBtn = PrimaryToolButton(FIF.SAVE, self)
        self.svBtn.setToolTip("保存配置")
        self.svBtn.setAccessibleName("保存配置")
        self.test_btn = PushButton(CgsIcon.AUTH_SCAN,"测试读写", self)
        self.test_btn.setEnabled(False)
        self.test_btn.setToolTip("写入、回读并清理临时文件验证连接")
        self._build_ui()
        self.endpoint_edit.setText(self.saved_config["endpoint"])
        self.user_edit.setText(self.saved_config["user"])
        self.password_edit.setText(self.saved_config["password"])
        self._refresh_endpoint_history()
        for edit in (self.endpoint_edit, self.user_edit, self.password_edit):
            edit.textChanged.connect(self._edited)
        self.svBtn.clicked.connect(self.save_config)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        # 行式表单：label 列定宽对齐；服务器地址行尾部挂测试/保存，动作随主输入同行。
        endpoint_row = QHBoxLayout()
        endpoint_row.setSpacing(8)
        endpoint_row.addWidget(self._field_label("服务器地址", self.endpoint_edit))
        endpoint_row.addWidget(self.endpoint_edit, 1)
        endpoint_row.addWidget(self.test_btn)
        endpoint_row.addWidget(self.svBtn)
        grid.addLayout(endpoint_row, 0, 0, 1, 4)
        for column, (text, edit) in enumerate((('账号', self.user_edit), ('密码', self.password_edit))):
            grid.addWidget(self._field_label(text, edit), 1, column * 2)
            grid.addWidget(edit, 1, column * 2 + 1)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 2)
        layout.addLayout(grid)

    def _field_label(self, text: str, edit: LineEdit) -> BodyLabel:
        label = BodyLabel(text, self)
        label.setFixedWidth(72)
        label.setBuddy(edit)
        edit.setAccessibleName(text)
        return label

    def _refresh_endpoint_history(self):
        completer = QCompleter(cgs_cfg.webdav.get_endpoint_history(), self.endpoint_edit)
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.endpoint_edit.setCompleter(completer)

    def draft(self) -> dict:
        return {**self.saved_config, "endpoint": self.endpoint_edit.text().strip(), "user": self.user_edit.text().strip(),
                "password": self.password_edit.text(), "root": self._root,
                "enabled": True}

    def set_root(self, path: str):
        """root 是配置接缝（config schema 默认 `/`），UI 不暴露目录选择；
        上传位置由 App 约定（服务器内 manga/doujinshi 结构）。归一化绝对路径。"""
        segments = [part for part in str(path or "").replace("\\", "/").split("/") if part and part != "."]
        root = "/" + "/".join(segments) if segments else "/"
        if root == self._root:
            return
        self._root = root
        self.changed.emit()

    def is_dirty(self) -> bool:
        return self.draft() != self.saved_config

    def validated_draft(self) -> dict:
        config = self.draft()
        endpoint = urlsplit(config["endpoint"])
        if endpoint.scheme not in ("http", "https") or not endpoint.hostname:
            raise ValueError("填写完整的 HTTP(S) WebDAV 地址")
        if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError("地址不能包含凭据、查询参数或片段，请使用账号字段")
        if ".." in config["root"].replace("\\", "/").split("/"):
            raise ValueError("上传根目录不能包含上级目录")
        return config

    def _edited(self, *_args):
        self.changed.emit()

    def save_config(self):
        try:
            config = self.validated_draft()
        except ValueError as exc:
            InfoBar.error(title='', content=str(exc), position=InfoBarPosition.TOP, duration=5000, parent=self.window())
            return
        self.saved_config = cgs_cfg.webdav.set(config)
        self._refresh_endpoint_history()
        InfoBar.success(title='', content="配置已保存", position=InfoBarPosition.TOP, duration=2500, parent=self.window())
        self.saved.emit()
        self.changed.emit()
