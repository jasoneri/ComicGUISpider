from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


API_VERSION = "jsoneri.probe.v1"
AVAILABLE_INSTANCE_STATE = "available"
INSTANCE_STATES = frozenset(
    {
        AVAILABLE_INSTANCE_STATE,
        "unavailable",
        "timeout",
        "network_error",
        "http_error",
        "disabled",
    }
)
FORBIDDEN_SERVICE_NAMES = frozenset(
    {
        "jsoneripalaces",
        "jsoneri-palaces",
        "raw-image",
        "ai-tools",
    }
)


class ServiceCardState(StrEnum):
    NORMAL = "normalCard"
    INVALID = "invalidCard"
    SUCCESS = "successCard"
    PLACEHOLDER = "lockCard"


@dataclass(frozen=True)
class ServiceResponse:
    code: str
    message: str
    detail: str


@dataclass(frozen=True)
class ServiceRoute:
    available: bool
    url: str


@dataclass(frozen=True)
class ServiceInstance:
    url: str
    host: str
    state: str
    last_check: float
    last_seen: float | None

    @property
    def alive(self) -> bool:
        return self.state == AVAILABLE_INSTANCE_STATE

    def is_stale(self, *, server_time: float, stale_threshold: float) -> bool:
        if self.last_seen is None:
            return True
        return server_time - self.last_seen > stale_threshold


@dataclass(frozen=True)
class ServiceStatusEntry:
    name: str
    label: str
    description: str
    icon: str
    card_state: ServiceCardState
    response: ServiceResponse
    route: ServiceRoute
    instances: tuple[ServiceInstance, ...]
    available_count: int
    total_count: int

    @property
    def can_open(self) -> bool:
        return self.card_state == ServiceCardState.SUCCESS and self.route.available and bool(self.route.url)


@dataclass(frozen=True)
class StatusSnapshot:
    api_version: str
    server_time: float
    stale_threshold: float
    services: tuple[ServiceStatusEntry, ...]


def normalize_api_base_url(raw_url: object) -> str:
    url = str(raw_url or "").strip().rstrip("/")
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("jsoneriPalacesProbe API URL must start with http:// or https://.")
    return url


def normalize_status_payload(payload: Any) -> StatusSnapshot:
    data = _require_mapping(payload, "status payload")
    api_version = _require_non_empty_string(data.get("api_version"), "api_version")
    if api_version != API_VERSION:
        raise ValueError(f"api_version must be {API_VERSION!r}, got {api_version!r}.")
    server_time = _require_number(data.get("server_time"), "server_time")
    stale_threshold = _require_number(data.get("stale_threshold"), "stale_threshold")
    services_data = data.get("services")
    if not isinstance(services_data, list):
        raise TypeError("services must be an array.")
    services = tuple(
        _normalize_service(service_payload, server_time=server_time, stale_threshold=stale_threshold)
        for service_payload in services_data
    )
    return StatusSnapshot(
        api_version=api_version,
        server_time=server_time,
        stale_threshold=stale_threshold,
        services=services,
    )


def _normalize_service(payload: Any, *, server_time: float, stale_threshold: float) -> ServiceStatusEntry:
    data = _require_mapping(payload, "service")
    service_name = _require_non_empty_string(data.get("name"), "service name")
    if service_name.casefold() in FORBIDDEN_SERVICE_NAMES:
        raise ValueError(f"service name is forbidden for jsoneri.probe.v1: {service_name}")
    label = _optional_string(data.get("label")) or service_name
    description = _optional_string(data.get("description"))
    icon = _optional_string(data.get("icon"))
    instances = _normalize_instances(data.get("instances"), service_name=service_name)
    available_count = sum(
        1
        for instance in instances
        if instance.alive and not instance.is_stale(server_time=server_time, stale_threshold=stale_threshold)
    )
    card_state = _normalize_card_state(data.get("card_state"), service_name=service_name)
    route = _normalize_route(data.get("route"), service_name=service_name)
    response = _normalize_response(data.get("response"), service_name=service_name)
    entry = ServiceStatusEntry(
        name=service_name,
        label=label,
        description=description,
        icon=icon,
        card_state=card_state,
        response=response,
        route=route,
        instances=instances,
        available_count=available_count,
        total_count=len(instances),
    )
    _validate_can_open_required(data.get("can_open"), entry, service_name=service_name)
    return entry


def _normalize_instances(payload: Any, *, service_name: str) -> tuple[ServiceInstance, ...]:
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise TypeError(f"service {service_name} instances must be an array.")
    return tuple(_normalize_instance(entry, service_name=service_name) for entry in payload)


def _normalize_instance(payload: Any, *, service_name: str) -> ServiceInstance:
    data = _require_mapping(payload, f"service {service_name} instance")
    if "alive" in data:
        raise TypeError(
            f"service {service_name} instance uses legacy alive field; jsoneri.probe.v1 requires state."
        )
    url = _require_non_empty_string(data.get("url"), f"service {service_name} instance url")
    host = _optional_string(data.get("host")) or url
    state = _normalize_instance_state(data.get("state"), service_name=service_name)
    last_check = _require_number(data.get("last_check"), f"service {service_name} instance last_check")
    last_seen = _optional_number(data.get("last_seen"), f"service {service_name} instance last_seen")
    return ServiceInstance(url=url, host=host, state=state, last_check=last_check, last_seen=last_seen)


def _normalize_instance_state(raw_state: object, *, service_name: str) -> str:
    state = _require_non_empty_string(raw_state, f"service {service_name} instance state")
    if state not in INSTANCE_STATES:
        raise ValueError(
            f"service {service_name} instance state is unsupported: {state}. "
            f"Expected one of {sorted(INSTANCE_STATES)}."
        )
    return state


def _normalize_card_state(raw_state: object, *, service_name: str) -> ServiceCardState:
    state = _optional_string(raw_state)
    if not state:
        raise TypeError(f"service {service_name} card_state must be a non-empty string.")
    try:
        return ServiceCardState(state)
    except ValueError as error:
        raise ValueError(f"service {service_name} card_state is unsupported: {state}") from error


def _normalize_route(payload: Any, *, service_name: str) -> ServiceRoute:
    data = _require_mapping(payload, f"service {service_name} route")
    available = data.get("available")
    if not isinstance(available, bool):
        raise TypeError(f"service {service_name} route.available must be a boolean.")
    url = _optional_string(data.get("url"))
    if available and not url:
        raise TypeError(f"service {service_name} route.url must be a non-empty string when route.available is true.")
    return ServiceRoute(available=available, url=url)


def _normalize_response(payload: Any, *, service_name: str) -> ServiceResponse:
    data = _require_mapping(payload, f"service {service_name} response")
    code = _optional_string(data.get("code"))
    message = _optional_string(data.get("message"))
    detail = _optional_string(data.get("detail"))
    if not code:
        raise TypeError(f"service {service_name} response code must be a non-empty string.")
    if not message:
        raise TypeError(f"service {service_name} response message must be a non-empty string.")
    return ServiceResponse(code=code, message=message, detail=detail)


def _validate_can_open_required(raw_can_open: object, entry: ServiceStatusEntry, *, service_name: str) -> None:
    if raw_can_open is None:
        raise TypeError(f"service {service_name} can_open is required.")
    if not isinstance(raw_can_open, bool):
        raise TypeError(f"service {service_name} can_open must be a boolean.")
    if raw_can_open != entry.can_open:
        raise ValueError(f"service {service_name} can_open conflicts with card_state and route availability.")


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
