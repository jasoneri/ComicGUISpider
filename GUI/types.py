from enum import Enum


class GUIFlowStage(Enum):
    IDLE = 0
    SEARCHED = 1


class PageDirection(str, Enum):
    NEXT = "next"
    PREVIOUS = "previous"
