# -*- coding: utf-8 -*-
from copy import deepcopy

from PyQt5.QtCore import QThread, pyqtSignal

from utils import Queues
from utils.middleware.timeline import (
    Event,
    EventSource,
    TimelineStage,
    stage_from_process_name,
)


class CGSMidThread(QThread):
    event_signal = pyqtSignal(object)

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.active = True
        self._last_process_state = None
        self._last_stage = None

    def run(self):
        manager = self.gui.manager
        ProcessQueue = manager.ProcessQueue()
        while self.active:
            self.msleep(20)
            process_state = Queues.recv(ProcessQueue)
            if not process_state:
                continue
            if self._last_process_state and process_state == self._last_process_state:
                continue
            self._last_process_state = deepcopy(process_state)

            stage = stage_from_process_name(getattr(process_state, "process", ""))
            if stage is None:
                continue
            if stage == self._last_stage:
                continue
            self._last_stage = stage

            evt = Event(
                source=EventSource.PROCESS_QUEUE,
                stage=stage,
                payload={"process_state": deepcopy(process_state)},
            )
            self.event_signal.emit(evt)

            if stage == TimelineStage.FINISHED:
                self.event_signal.emit(
                    Event(
                        source=EventSource.PROCESS_QUEUE,
                        stage=TimelineStage.SESSION_END,
                        payload={"process_state": deepcopy(process_state)},
                    )
                )
                break

            if stage in (TimelineStage.SESSION_END, TimelineStage.SESSION_CANCEL, TimelineStage.SESSION_ERROR):
                break

    def stop(self):
        self.active = False
