from dataclasses import dataclass, field
from enum import Enum


class SearchLifecycleState(Enum):
    Unlocked = "unlocked"
    Locked = "locked"


class PreviewRequestState(Enum):
    Idle = "idle"
    Running = "running"


@dataclass(slots=True)
class SearchUiState:
    session: SearchLifecycleState = SearchLifecycleState.Unlocked
    request: PreviewRequestState = PreviewRequestState.Idle
    controls_blocked: bool = False


@dataclass(frozen=True, slots=True)
class SearchContextSnapshot:
    site_index: int
    proxies: list[str]
    cookies: dict[str, dict]
    domains: dict[str, str] = field(default_factory=dict)
    custom_map: dict[str, object] = field(default_factory=dict)
    doh_url: str = ""


class GUIFlowStage(Enum):
    IDLE = 0
    SEARCHED = 1


class PageDirection(str, Enum):
    NEXT = "next"
    PREVIOUS = "previous"
