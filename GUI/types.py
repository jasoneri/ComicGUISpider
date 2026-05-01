from dataclasses import dataclass
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


class GUIFlowStage(Enum):
    IDLE = 0
    SEARCHED = 1


class PageDirection(str, Enum):
    NEXT = "next"
    PREVIOUS = "previous"
