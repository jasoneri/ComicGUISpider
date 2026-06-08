from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, PrimaryPushButton, ToolButton

from utils.script import conf as script_conf

from .browser import JsoneriServicesStatusBrowserController
from .client import JsoneriServicesStatusApiClient
from .dashboard import DashboardViewModel, JsoneriServicesDashboardStore, ServiceViewModel
from .models import ServiceStatus, normalize_api_base_url
from .topology import JsoneriServicesTopologyCanvas


class JsoneriServicesStatusInterface(QFrame):
    info_bar_orient = Qt.Horizontal

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("JsoneriServicesStatusInterface")
        self.store = JsoneriServicesDashboardStore()
        self.client = JsoneriServicesStatusApiClient(parent=self)
        self.browser_controller = JsoneriServicesStatusBrowserController(self, self.client)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(30_000)
        self.poll_timer.timeout.connect(self.refresh_status)
        self._config_expanded = False
        self._setup_ui()
        self._connect_runtime()
        self.refresh_config(fetch=False)

    def refresh_config(self, *, fetch: bool = True) -> None:
        config = script_conf.jsoneri_server_status or {}
        url = str(config.get("url") or "")
        token = str(config.get("token") or "")
        self.url_edit.setText(url)
        self.token_edit.setText(token)
        self.client.configure(base_url=url, token=token)
        self.store.set_configured(self.client.is_configured)
        if self.client.is_configured:
            if self.isVisible() and not self.poll_timer.isActive():
                self.poll_timer.start()
            if fetch:
                self.refresh_status()
            else:
                self._render()
            return
        self.poll_timer.stop()
        self._config_expanded = True
        self._render()

    def save_config(self) -> None:
        try:
            url = normalize_api_base_url(self.url_edit.text())
        except ValueError as error:
            InfoBar.error(
                title="", content=str(error), orient=self.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=3500, parent=self,
            )
            return
        token = self.token_edit.text().strip()
        script_conf.update(jsoneri_server_status={"url": url, "token": token})
        self._config_expanded = not bool(url)
        self.refresh_config(fetch=bool(url))
        InfoBar.success(
            title="", content="Jsoneri Server Status saved", orient=self.info_bar_orient, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=2500, parent=self,
        )

    def refresh_status(self) -> None:
        if not self.client.is_configured:
            self.refresh_config(fetch=False)
            return
        if self.client.status_in_flight:
            return
        generation = self.store.begin_poll()
        self._render()
        self.client.fetch_status(generation)

    def close_service_window(self) -> None:
        self.browser_controller.close_window()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.client.is_configured:
            self.refresh_status()
            self.poll_timer.start()

    def hideEvent(self, event) -> None:
        self.poll_timer.stop()
        super().hideEvent(event)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        header = QFrame(self)
        header.setObjectName("JsoneriServicesStatusHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)
        self.title_label = QLabel("Jsoneri Server Status", header)
        self.title_label.setObjectName("JsoneriServicesTitle")
        self.connection_dot = QLabel(header)
        self.connection_dot.setFixedSize(10, 10)
        self.connection_label = QLabel("", header)
        self.config_button = ToolButton(FIF.SETTING, header)
        self.config_button.setToolTip("Configure Jsoneri Server Status API")
        self.config_button.clicked.connect(self._toggle_config_panel)
        self.refresh_button = ToolButton(FIF.SYNC, header)
        self.refresh_button.setToolTip("Refresh status")
        self.refresh_button.clicked.connect(self.refresh_status)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.connection_dot)
        header_layout.addWidget(self.connection_label)
        header_layout.addWidget(self.config_button)
        header_layout.addWidget(self.refresh_button)
        root.addWidget(header)

        self.config_panel = QFrame(self)
        self.config_panel.setObjectName("JsoneriServicesStatusConfig")
        config_layout = QHBoxLayout(self.config_panel)
        config_layout.setContentsMargins(14, 10, 14, 10)
        config_layout.setSpacing(10)
        self.url_edit = LineEdit(self.config_panel)
        self.url_edit.setPlaceholderText("https://status.example.com")
        self.url_edit.setClearButtonEnabled(True)
        self.token_edit = LineEdit(self.config_panel)
        self.token_edit.setPlaceholderText("suspect token")
        self.token_edit.setClearButtonEnabled(True)
        self.save_button = PrimaryPushButton(FIF.SAVE, "Save", self.config_panel)
        self.save_button.clicked.connect(self.save_config)
        config_layout.addWidget(QLabel("API URL", self.config_panel))
        config_layout.addWidget(self.url_edit, 2)
        config_layout.addWidget(QLabel("Token", self.config_panel))
        config_layout.addWidget(self.token_edit, 1)
        config_layout.addWidget(self.save_button)
        root.addWidget(self.config_panel)

        summary_panel = QFrame(self)
        summary_panel.setObjectName("JsoneriServicesSummary")
        summary_layout = QHBoxLayout(summary_panel)
        summary_layout.setContentsMargins(14, 10, 14, 10)
        summary_layout.setSpacing(18)
        self.summary_labels = {
            "total": QLabel(summary_panel),
            "online": QLabel(summary_panel),
            "checking": QLabel(summary_panel),
            "offline": QLabel(summary_panel),
            "unknown": QLabel(summary_panel),
            "last": QLabel(summary_panel),
        }
        for label in self.summary_labels.values():
            summary_layout.addWidget(label)
        summary_layout.addStretch(1)
        root.addWidget(summary_panel)

        controls = QFrame(self)
        controls.setObjectName("JsoneriServicesControls")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(14, 8, 14, 8)
        controls_layout.setSpacing(10)
        self.search_edit = LineEdit(controls)
        self.search_edit.setPlaceholderText("Filter services")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_filters_changed)
        self.status_filter = ComboBox(controls)
        self.status_filter.addItem("All", userData="all")
        for status in ServiceStatus:
            self.status_filter.addItem(status.value.title(), userData=status.value)
        self.status_filter.currentIndexChanged.connect(self._on_filters_changed)
        self.open_button = PrimaryPushButton(FIF.RIGHT_ARROW, "Open", controls)
        self.open_button.clicked.connect(self._open_selected_service)
        controls_layout.addWidget(self.search_edit, 1)
        controls_layout.addWidget(self.status_filter)
        controls_layout.addWidget(self.open_button)
        root.addWidget(controls)

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter = self.workspace_splitter
        splitter.setChildrenCollapsible(False)
        self.service_list = QListWidget(splitter)
        self.service_list.setObjectName("JsoneriServicesList")
        self.service_list.setMinimumWidth(180)
        self.service_list.setMaximumWidth(230)
        self.service_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.service_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.service_list.setWordWrap(False)
        self.service_list.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.service_list.itemClicked.connect(self._on_service_item_clicked)
        splitter.addWidget(self.service_list)

        self.topology_canvas = JsoneriServicesTopologyCanvas(splitter)
        self.topology_canvas.setMinimumWidth(420)
        self.topology_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.topology_canvas.service_selected.connect(self._select_service)
        self.topology_canvas.service_open_requested.connect(self._open_service)
        splitter.addWidget(self.topology_canvas)

        detail_panel = QFrame(splitter)
        detail_panel.setObjectName("JsoneriServicesDetail")
        detail_panel.setMinimumWidth(280)
        detail_panel.setMaximumWidth(360)
        detail_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(14, 12, 14, 12)
        detail_layout.setSpacing(8)
        self.state_message_label = QLabel(detail_panel)
        self.state_message_label.setWordWrap(True)
        self.detail_title = QLabel("No service selected", detail_panel)
        self.detail_title.setObjectName("JsoneriServicesDetailTitle")
        self.detail_status = QLabel(detail_panel)
        self.detail_description = QLabel(detail_panel)
        self.detail_description.setWordWrap(True)
        self.instances_label = QLabel(detail_panel)
        self.instances_label.setWordWrap(True)
        self.route_label = QLabel(detail_panel)
        self.route_label.setWordWrap(True)
        self.suspect_label = QLabel(detail_panel)
        self.suspect_label.setWordWrap(True)
        self.events_list = QListWidget(detail_panel)
        self.events_list.setObjectName("JsoneriServicesEvents")
        self.events_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.events_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.events_list.setWordWrap(False)
        detail_layout.addWidget(self.state_message_label)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_status)
        detail_layout.addWidget(self.detail_description)
        detail_layout.addWidget(self.instances_label)
        detail_layout.addWidget(self.route_label)
        detail_layout.addWidget(self.suspect_label)
        detail_layout.addWidget(QLabel("Recent events", detail_panel))
        detail_layout.addWidget(self.events_list, 1)
        splitter.addWidget(detail_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([210, 620, 320])
        root.addWidget(splitter, 1)

        self.setStyleSheet(
            """
            QFrame#JsoneriServicesStatusHeader,
            QFrame#JsoneriServicesStatusConfig,
            QFrame#JsoneriServicesSummary,
            QFrame#JsoneriServicesControls,
            QFrame#JsoneriServicesDetail {
                border: 1px solid rgba(125, 125, 125, 0.22);
                border-radius: 8px;
                background: rgba(125, 125, 125, 0.06);
            }
            QLabel#JsoneriServicesTitle, QLabel#JsoneriServicesDetailTitle {
                font-size: 15px;
                font-weight: 700;
            }
            QListWidget#JsoneriServicesList, QListWidget#JsoneriServicesEvents {
                border: 1px solid rgba(125, 125, 125, 0.18);
                border-radius: 8px;
                background: rgba(125, 125, 125, 0.04);
            }
            """
        )

    def _connect_runtime(self) -> None:
        self.client.status_received.connect(self._on_status_received)
        self.client.status_unreachable.connect(self._on_status_unreachable)
        self.client.route_received.connect(self._on_route_received)
        self.client.route_failed.connect(self._on_route_failed)
        self.client.suspect_reported.connect(self._on_suspect_reported)
        self.client.suspect_failed.connect(self._on_suspect_failed)
        self.browser_controller.suspect_started.connect(self._on_suspect_started)

    def _toggle_config_panel(self) -> None:
        self._config_expanded = not self._config_expanded
        self._render()

    def _on_filters_changed(self) -> None:
        self.store.set_filters(search_text=self.search_edit.text(), status_filter=self.status_filter.currentData() or "all")
        self._render()

    def _on_service_item_clicked(self, item: QListWidgetItem) -> None:
        service_name = item.data(Qt.ItemDataRole.UserRole)
        self._select_service(str(service_name or ""))

    def _select_service(self, service_name: str) -> None:
        self.store.select_service(service_name)
        self._render()

    def _open_selected_service(self) -> None:
        view_model = self.store.view_model()
        if view_model.selected_service is not None:
            self._open_service(view_model.selected_service.name)

    def _open_service(self, service_name: str) -> None:
        self.store.begin_route(service_name)
        self._render()
        self.browser_controller.open_service(service_name)

    def _on_status_received(self, generation: int, snapshot) -> None:
        if self.store.accept_status(generation, snapshot):
            self._render()

    def _on_status_unreachable(self, generation: int, message: str) -> None:
        if self.store.fail_status(generation, message):
            self._render()
        InfoBar.warning(
            title="", content=message, orient=self.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=3500, parent=self,
        )

    def _on_route_received(self, service_name: str, url: object) -> None:
        if self.store.route_received(service_name, url):
            self._render()

    def _on_route_failed(self, service_name: str, message: str) -> None:
        if self.store.route_failed(service_name, message):
            self._render()

    def _on_suspect_started(self, service_name: str, url: str) -> None:
        self.store.suspect_started(service_name, url)
        self._render()

    def _on_suspect_reported(self, service_name: str, url: str) -> None:
        if self.store.suspect_reported(service_name, url):
            self._render()

    def _on_suspect_failed(self, service_name: str, url: str, message: str) -> None:
        if self.store.suspect_failed(service_name, url, message):
            self._render()

    def _render(self) -> None:
        view_model = self.store.view_model()
        self._render_header(view_model)
        self._render_summary(view_model)
        self._render_service_list(view_model)
        self._render_detail(view_model)
        self.config_panel.setVisible(self._config_expanded or not view_model.configured)
        self.topology_canvas.set_view_model(
            view_model.topology_nodes, selected_service_name=view_model.selected_service_name, state_message=view_model.state_message
        )

    def _render_header(self, view_model: DashboardViewModel) -> None:
        self.connection_label.setText(view_model.connection_label)
        self.connection_dot.setStyleSheet(f"border-radius: 5px; background: {view_model.connection_color};")
        self.refresh_button.setEnabled(view_model.configured)

    def _render_summary(self, view_model: DashboardViewModel) -> None:
        summary = view_model.summary
        self.summary_labels["total"].setText(f"Total {summary.total}")
        self.summary_labels["online"].setText(f"Online {summary.online}")
        self.summary_labels["checking"].setText(f"Checking {summary.checking}")
        self.summary_labels["offline"].setText(f"Offline {summary.offline}")
        self.summary_labels["unknown"].setText(f"Unknown {summary.unknown}")
        self.summary_labels["last"].setText(f"Last refresh {summary.last_refresh_label}")

    def _render_service_list(self, view_model: DashboardViewModel) -> None:
        selected_name = view_model.selected_service_name
        self.service_list.blockSignals(True)
        self.service_list.clear()
        for service in view_model.services:
            item = QListWidgetItem(f"{service.status_label}  {service.label}\n{service.online_ratio}")
            item.setToolTip(f"{service.label}\n{service.online_ratio}\n{service.freshness_label}")
            item.setData(Qt.ItemDataRole.UserRole, service.name)
            self.service_list.addItem(item)
            if service.name == selected_name:
                self.service_list.setCurrentItem(item)
        self.service_list.blockSignals(False)

    def _render_detail(self, view_model: DashboardViewModel) -> None:
        self.state_message_label.setText(view_model.state_message)
        service = view_model.selected_service
        self.open_button.setEnabled(service is not None and service.can_open)
        if service is None:
            self.detail_title.setText("No service selected")
            self.detail_status.setText("")
            self.detail_description.setText("")
            self.instances_label.setText("")
        else:
            self._render_selected_service(service)
        route = view_model.route_operation
        suspect = view_model.suspect_operation
        self.route_label.setText(f"Route: {route.state.value} {route.message}".strip())
        self.suspect_label.setText(f"Suspect: {suspect.state.value} {suspect.message}".strip())
        self.events_list.clear()
        for event in view_model.events[:12]:
            item = QListWidgetItem(event.message)
            item.setToolTip(event.message)
            self.events_list.addItem(item)

    def _render_selected_service(self, service: ServiceViewModel) -> None:
        self.detail_title.setText(service.label)
        self.detail_status.setText(f"{service.status_label} · {service.online_ratio} · {service.freshness_label}")
        self.detail_description.setText(service.description)
        if service.instances:
            lines = [f"{instance.alive_label} · {instance.host} · {instance.freshness_label}" for instance in service.instances]
            self.instances_label.setText("Instances\n" + "\n".join(lines))
            return
        self.instances_label.setText("Instances\nNo instances reported.")
