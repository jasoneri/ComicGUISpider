from enum import Enum


class GUIFlowStage(Enum):
    IDLE = 0
    SEARCHED = 1
    DOWNLOADING = 2
    FINISHED = 3
    ERROR = 4


class PageDirection(str, Enum):
    NEXT = "next"
    PREVIOUS = "previous"
