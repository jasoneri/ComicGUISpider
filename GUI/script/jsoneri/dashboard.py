from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .models import ServiceStatus, ServiceStatusEntry, StatusSnapshot


STATUS_COLORS = {
    ServiceStatus.ONLINE: "#10b981",
    ServiceStatus.OFFLINE: "#ef4444",
    ServiceStatus.UNKNOWN: "#9ca3af",
    ServiceStatus.CHECKING: "#f59e0b",
}

STATUS_LABELS = {
    ServiceStatus.ONLINE: "Online",
    ServiceStatus.OFFLINE: "Offline",
    ServiceStatus.UNKNOWN: "Unknown",
    ServiceStatus.CHECKING: "Checking",
}


class DashboardConnection(StrEnum):
    NOT_CONFIGURED = "not_configured"
    READY = "ready"
    CHECKING = "checking"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class RouteState(StrEnum):
    IDLE = "idle"
    PENDING = "pending"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class SuspectState(StrEnum):
    IDLE = "idle"
    PENDING = "pending"
    REPORTED = "reported"
    FAILED = "failed"


@dataclass(frozen=True)
class DashboardEvent:
    message: str
    service_name: str = ""
    url: str = ""


@dataclass(frozen=True)
class DashboardSummary:
    total: int
    online: int
    checking: int
    offline: int
    unknown: int
    last_refresh_label: str


@dataclass(frozen=True)
class InstanceViewModel:
    url: str
    host: str
    alive_label: str
    freshness_label: str


@dataclass(frozen=True)
class ServiceViewModel:
    name: str
    label: str
    description: str
    status: ServiceStatus
    status_label: str
    color: str
    online_ratio: str
    freshness_label: str
    can_open: bool
    instances: tuple[InstanceViewModel, ...]


@dataclass(frozen=True)
class TopologyNodeViewModel:
    service_name: str
    label: str
    status_label: str
    color: str
    online_ratio: str
    freshness_label: str


@dataclass(frozen=True)
class RouteOperationViewModel:
    state: RouteState
    service_name: str
    url: str
    message: str


@dataclass(frozen=True)
class SuspectOperationViewModel:
    state: SuspectState
    service_name: str
    url: str
    message: str


@dataclass(frozen=True)
class DashboardViewModel:
    configured: bool
    connection: DashboardConnection
    connection_label: str
    connection_color: str
    state_message: str
    summary: DashboardSummary
    services: tuple[ServiceViewModel, ...]
    selected_service: ServiceViewModel | None
    selected_service_name: str
    topology_nodes: tuple[TopologyNodeViewModel, ...]
    route_operation: RouteOperationViewModel
    suspect_operation: SuspectOperationViewModel
    events: tuple[DashboardEvent, ...]


@dataclass
class _RouteOperation:
    state: RouteState = RouteState.IDLE
    service_name: str = ""
    url: str = ""
    message: str = ""


@dataclass
class _SuspectOperation:
    state: SuspectState = SuspectState.IDLE
    service_name: str = ""
    url: str = ""
    message: str = ""


class JsoneriServicesDashboardStore:
    def __init__(self, *, max_events: int = 30):
        self.configured = False
        self.connection = DashboardConnection.NOT_CONFIGURED
        self._snapshot: StatusSnapshot | None = None
        self._poll_generation = 0
        self._in_flight_generation = 0
        self.selected_service_name = ""
        self.search_text = ""
        self.status_filter = "all"
        self.route_operation = _RouteOperation()
        self.suspect_operation = _SuspectOperation()
        self.events: list[DashboardEvent] = []
        self.max_events = max_events
        self.last_error = ""

    @property
    def active_poll_generation(self) -> int:
        return self._in_flight_generation

    def set_configured(self, configured: bool) -> None:
        self.configured = configured
        if configured:
            if self.connection == DashboardConnection.NOT_CONFIGURED:
                self.connection = DashboardConnection.READY
            return
        self.connection = DashboardConnection.NOT_CONFIGURED
        self._snapshot = None
        self._in_flight_generation = 0
        self.selected_service_name = ""
        self.last_error = ""
        self.route_operation = _RouteOperation()
        self.suspect_operation = _SuspectOperation()

    def begin_poll(self) -> int:
        if not self.configured:
            self.connection = DashboardConnection.NOT_CONFIGURED
            return 0
        self._poll_generation += 1
        self._in_flight_generation = self._poll_generation
        self.connection = DashboardConnection.CHECKING
        self.last_error = ""
        return self._in_flight_generation

    def cancel_poll(self, generation: int) -> bool:
        if generation != self._in_flight_generation:
            return False
        self._in_flight_generation = 0
        self.connection = DashboardConnection.CONNECTED if self._snapshot is not None else DashboardConnection.READY
        return True

    def accept_status(self, generation: int, snapshot: StatusSnapshot) -> bool:
        if generation != self._in_flight_generation:
            return False
        self._snapshot = snapshot
        self._in_flight_generation = 0
        self.connection = DashboardConnection.CONNECTED
        self.last_error = ""
        self._append_event("Status snapshot updated.")
        self._ensure_selection()
        return True

    def fail_status(self, generation: int, message: str) -> bool:
        if generation != self._in_flight_generation:
            return False
        self._in_flight_generation = 0
        self.connection = DashboardConnection.DISCONNECTED
        self.last_error = str(message)
        self._append_event(f"Status API unreachable: {message}")
        return True

    def set_filters(self, *, search_text: str, status_filter: str) -> None:
        self.search_text = search_text.strip()
        self.status_filter = status_filter if status_filter in {"all", *[status.value for status in ServiceStatus]} else "all"
        self._ensure_selection()

    def select_service(self, service_name: str) -> None:
        service = str(service_name or "").strip()
        if service and self._service_by_name(service) is None:
            raise ValueError(f"Unknown Jsoneri service: {service}")
        self.selected_service_name = service

    def begin_route(self, service_name: str) -> None:
        service = self._require_service_name(service_name)
        self.route_operation = _RouteOperation(state=RouteState.PENDING, service_name=service, message="Resolving route.")
        self._append_event(f"Resolving route for {self._service_label(service)}.", service_name=service)

    def route_received(self, service_name: str, url: object) -> bool:
        service = self._require_service_name(service_name)
        if self.route_operation.state != RouteState.PENDING or self.route_operation.service_name != service:
            return False
        if url:
            route_url = str(url)
            self.route_operation = _RouteOperation(
                state=RouteState.READY, service_name=service, url=route_url, message=f"Route ready: {route_url}"
            )
            self._append_event(f"Route ready for {self._service_label(service)}.", service_name=service, url=route_url)
            return True
        self.route_operation = _RouteOperation(state=RouteState.UNAVAILABLE, service_name=service, message="No available instance.")
        self._append_event(f"No available instance for {self._service_label(service)}.", service_name=service)
        return True

    def route_failed(self, service_name: str, message: str) -> bool:
        service = self._require_service_name(service_name)
        if self.route_operation.state != RouteState.PENDING or self.route_operation.service_name != service:
            return False
        self.route_operation = _RouteOperation(state=RouteState.FAILED, service_name=service, message=str(message))
        self._append_event(f"Route failed for {self._service_label(service)}: {message}", service_name=service)
        return True

    def suspect_started(self, service_name: str, url: str) -> None:
        service = self._require_service_name(service_name)
        target_url = self._require_url(url)
        self.suspect_operation = _SuspectOperation(
            state=SuspectState.PENDING, service_name=service, url=target_url, message="Reporting suspect instance."
        )
        self._append_event(f"Reporting suspect instance for {self._service_label(service)}.", service_name=service, url=target_url)

    def suspect_reported(self, service_name: str, url: str) -> bool:
        service = self._require_service_name(service_name)
        target_url = self._require_url(url)
        if self.suspect_operation.state != SuspectState.PENDING or self.suspect_operation.service_name != service:
            return False
        self.suspect_operation = _SuspectOperation(
            state=SuspectState.REPORTED, service_name=service, url=target_url, message="Suspect instance reported."
        )
        self._append_event(f"Suspect instance reported for {self._service_label(service)}.", service_name=service, url=target_url)
        return True

    def suspect_failed(self, service_name: str, url: str, message: str) -> bool:
        service = self._require_service_name(service_name)
        target_url = self._require_url(url)
        if self.suspect_operation.state != SuspectState.PENDING or self.suspect_operation.service_name != service:
            return False
        self.suspect_operation = _SuspectOperation(state=SuspectState.FAILED, service_name=service, url=target_url, message=str(message))
        self._append_event(f"Suspect report failed for {self._service_label(service)}: {message}", service_name=service, url=target_url)
        return True

    def view_model(self) -> DashboardViewModel:
        services = tuple(self._service_vm(entry) for entry in self._filtered_entries())
        selected_entry = self._service_by_name(self.selected_service_name)
        selected_service = self._service_vm(selected_entry) if selected_entry is not None else None
        topology_nodes = tuple(
            TopologyNodeViewModel(
                service_name=service.name, label=service.label, status_label=service.status_label, color=service.color,
                online_ratio=service.online_ratio, freshness_label=service.freshness_label,
            )
            for service in services
        )
        return DashboardViewModel(
            configured=self.configured, connection=self.connection, connection_label=self._connection_label(),
            connection_color=self._connection_color(), state_message=self._state_message(services), summary=self._summary(),
            services=services, selected_service=selected_service, selected_service_name=self.selected_service_name,
            topology_nodes=topology_nodes, route_operation=RouteOperationViewModel(**self.route_operation.__dict__),
            suspect_operation=SuspectOperationViewModel(**self.suspect_operation.__dict__), events=tuple(self.events),
        )

    def _summary(self) -> DashboardSummary:
        entries = self._snapshot.services if self._snapshot is not None else ()
        return DashboardSummary(
            total=len(entries), online=sum(1 for entry in entries if entry.status == ServiceStatus.ONLINE),
            checking=sum(1 for entry in entries if entry.status == ServiceStatus.CHECKING),
            offline=sum(1 for entry in entries if entry.status == ServiceStatus.OFFLINE),
            unknown=sum(1 for entry in entries if entry.status == ServiceStatus.UNKNOWN), last_refresh_label=self._last_refresh_label(),
        )

    def _service_vm(self, entry: ServiceStatusEntry) -> ServiceViewModel:
        instances = tuple(
            InstanceViewModel(
                url=instance.url, host=instance.host, alive_label="alive" if instance.alive else "down",
                freshness_label=_format_seen_age(self._snapshot.server_time if self._snapshot is not None else None, instance.last_seen),
            )
            for instance in entry.instances
        )
        return ServiceViewModel(
            name=entry.name, label=entry.label or entry.name, description=entry.description or "No description", status=entry.status,
            status_label=STATUS_LABELS[entry.status], color=STATUS_COLORS[entry.status], online_ratio=f"{entry.online_count}/{entry.total_count} online",
            freshness_label=self._service_freshness_label(entry), can_open=entry.can_open, instances=instances,
        )

    def _filtered_entries(self) -> tuple[ServiceStatusEntry, ...]:
        if self._snapshot is None:
            return ()
        search = self.search_text.casefold()
        status_filter = self.status_filter
        entries = []
        for entry in self._snapshot.services:
            if status_filter != "all" and entry.status.value != status_filter:
                continue
            haystack = f"{entry.name} {entry.label} {entry.description}".casefold()
            if search and search not in haystack:
                continue
            entries.append(entry)
        return tuple(entries)

    def _ensure_selection(self) -> None:
        entries = self._filtered_entries()
        names = {entry.name for entry in entries}
        if self.selected_service_name in names:
            return
        self.selected_service_name = entries[0].name if entries else ""

    def _service_by_name(self, service_name: str) -> ServiceStatusEntry | None:
        if self._snapshot is None:
            return None
        for entry in self._snapshot.services:
            if entry.name == service_name:
                return entry
        return None

    def _service_label(self, service_name: str) -> str:
        entry = self._service_by_name(service_name)
        return entry.label if entry is not None and entry.label else service_name

    def _service_freshness_label(self, entry: ServiceStatusEntry) -> str:
        if self._snapshot is None:
            return "not refreshed"
        latest_seen = max((instance.last_seen for instance in entry.instances if instance.last_seen is not None), default=None)
        return _format_seen_age(self._snapshot.server_time, latest_seen)

    def _last_refresh_label(self) -> str:
        if self._snapshot is None:
            return "Never"
        return datetime.fromtimestamp(self._snapshot.server_time).strftime("%Y-%m-%d %H:%M:%S")

    def _connection_label(self) -> str:
        return {
            DashboardConnection.NOT_CONFIGURED: "Not configured",
            DashboardConnection.READY: "Ready",
            DashboardConnection.CHECKING: "Checking",
            DashboardConnection.CONNECTED: "Connected",
            DashboardConnection.DISCONNECTED: "Disconnected",
        }[self.connection]

    def _connection_color(self) -> str:
        return {
            DashboardConnection.NOT_CONFIGURED: "#9ca3af",
            DashboardConnection.READY: "#9ca3af",
            DashboardConnection.CHECKING: "#f59e0b",
            DashboardConnection.CONNECTED: "#10b981",
            DashboardConnection.DISCONNECTED: "#ef4444",
        }[self.connection]

    def _state_message(self, services: tuple[ServiceViewModel, ...]) -> str:
        if not self.configured:
            return "Configure Jsoneri Server Status API URL to begin."
        if self.connection == DashboardConnection.CHECKING and self._snapshot is None:
            return "Checking Jsoneri Server Status API..."
        if self.connection == DashboardConnection.DISCONNECTED and self._snapshot is None:
            return self.last_error or "Jsoneri Server Status API is unreachable."
        if self._snapshot is None:
            return "No status snapshot loaded."
        if not self._snapshot.services:
            return "No services reported."
        if not services:
            return "No services match the current filters."
        return ""

    def _require_service_name(self, service_name: str) -> str:
        service = str(service_name or "").strip()
        if not service:
            raise ValueError("service_name must be a non-empty string.")
        return service

    def _require_url(self, url: str) -> str:
        target_url = str(url or "").strip()
        if not target_url:
            raise ValueError("url must be a non-empty string.")
        return target_url

    def _append_event(self, message: str, *, service_name: str = "", url: str = "") -> None:
        self.events.insert(0, DashboardEvent(message=message, service_name=service_name, url=url))
        del self.events[self.max_events:]


def _format_seen_age(server_time: float | None, last_seen: float | None) -> str:
    if server_time is None:
        return "not refreshed"
    if last_seen is None:
        return "never seen"
    age = max(0, int(server_time - last_seen))
    if age < 60:
        return "seen <1m ago"
    if age < 3600:
        return f"seen {age // 60}m ago"
    if age < 86400:
        return f"seen {age // 3600}h ago"
    return f"seen {age // 86400}d ago"
