from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ServiceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    CHECKING = "checking"


@dataclass(frozen=True)
class ServiceInstance:
    url: str
    host: str
    alive: bool
    last_check: float | None
    last_seen: float | None

    def is_stale(self, *, server_time: float, stale_threshold: float) -> bool:
        if self.last_seen is None:
            return True
        return server_time - self.last_seen > stale_threshold


@dataclass(frozen=True)
class ServiceStatusEntry:
    name: str
    label: str
    description: str
    instances: tuple[ServiceInstance, ...]
    status: ServiceStatus
    online_count: int
    total_count: int

    @property
    def can_open(self) -> bool:
        return self.online_count > 0


@dataclass(frozen=True)
class StatusSnapshot:
    server_time: float
    stale_threshold: float
    services: tuple[ServiceStatusEntry, ...]


def normalize_api_base_url(raw_url: object) -> str:
    url = str(raw_url or "").strip().rstrip("/")
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Jsoneri Server Status API URL must start with http:// or https://.")
    return url


def normalize_status_payload(payload: Any) -> StatusSnapshot:
    data = _require_mapping(payload, "status payload")
    server_time = _require_number(data.get("server_time"), "server_time")
    stale_threshold = _require_number(data.get("stale_threshold"), "stale_threshold")
    if stale_threshold <= 0:
        raise ValueError("status payload stale_threshold must be greater than 0.")
    services_data = _require_mapping(data.get("services"), "services")
    services = tuple(
        _normalize_service(name, service_payload, server_time=server_time, stale_threshold=stale_threshold)
        for name, service_payload in sorted(services_data.items(), key=lambda item: str(item[0]).casefold())
    )
    return StatusSnapshot(server_time=server_time, stale_threshold=stale_threshold, services=services)


def _normalize_service(name: object, payload: Any, *, server_time: float, stale_threshold: float) -> ServiceStatusEntry:
    service_name = _require_non_empty_string(name, "service name")
    data = _require_mapping(payload, f"service {service_name}")
    label = _optional_string(data.get("label")) or service_name
    description = _optional_string(data.get("description"))
    instances_data = data.get("instances")
    if not isinstance(instances_data, list):
        raise TypeError(f"service {service_name} instances must be an array.")
    instances = tuple(
        _normalize_instance(entry, service_name=service_name, server_time=server_time, stale_threshold=stale_threshold)
        for entry in instances_data
    )
    online_count = sum(
        1
        for instance in instances
        if instance.alive and not instance.is_stale(server_time=server_time, stale_threshold=stale_threshold)
    )
    status = _derive_service_status(instances, online_count=online_count, server_time=server_time, stale_threshold=stale_threshold)
    return ServiceStatusEntry(
        name=service_name, label=label, description=description, instances=instances,
        status=status, online_count=online_count, total_count=len(instances),
    )


def _normalize_instance(payload: Any, *, service_name: str, server_time: float, stale_threshold: float) -> ServiceInstance:
    data = _require_mapping(payload, f"service {service_name} instance")
    url = _require_non_empty_string(data.get("url"), f"service {service_name} instance url")
    host = _optional_string(data.get("host")) or url
    alive = data.get("alive")
    if not isinstance(alive, bool):
        raise TypeError(f"service {service_name} instance alive must be a boolean.")
    last_check = _optional_number(data.get("last_check"), f"service {service_name} instance last_check")
    last_seen = _optional_number(data.get("last_seen"), f"service {service_name} instance last_seen")
    return ServiceInstance(url=url, host=host, alive=alive, last_check=last_check, last_seen=last_seen)


def _derive_service_status(
    instances: tuple[ServiceInstance, ...], *, online_count: int, server_time: float, stale_threshold: float,
) -> ServiceStatus:
    if not instances:
        return ServiceStatus.UNKNOWN
    if online_count > 0:
        return ServiceStatus.ONLINE
    if any(instance.alive for instance in instances):
        return ServiceStatus.CHECKING
    if all(instance.is_stale(server_time=server_time, stale_threshold=stale_threshold) for instance in instances):
        return ServiceStatus.UNKNOWN
    return ServiceStatus.OFFLINE


def _require_mapping(value: Any, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object.")
    return value


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _require_number(value: object, field_name: str) -> float:
    number = _optional_number(value, field_name)
    if number is None:
        raise TypeError(f"{field_name} must be a finite number.")
    return number


def _optional_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a finite number.")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise TypeError(f"{field_name} must be a finite number.")
    return number
