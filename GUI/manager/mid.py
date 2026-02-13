# -*- coding: utf-8 -*-
from enum import Enum
from PyQt5.QtCore import QObject, pyqtSignal

from GUI.thread.mid import CGSMidThread
from utils.middleware.core import CGSMidManager, ExecutionContext
from utils.middleware.timeline import TimelineStage, LaneStage


class WorkflowState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"


class WorkflowSession:
    _VALID_TRANSITIONS = {
        WorkflowState.IDLE: {WorkflowState.RUNNING},
        WorkflowState.RUNNING: {WorkflowState.WAITING, WorkflowState.IDLE},
        WorkflowState.WAITING: {WorkflowState.RUNNING},
    }

    def __init__(self):
        self.state = WorkflowState.IDLE
        self.current_stage: TimelineStage | None = None
        self.current_lane: LaneStage | None = None

    def transition_to(self, new_state: WorkflowState, stage: TimelineStage | None = None, on_changed=None):
        if new_state not in self._VALID_TRANSITIONS.get(self.state, set()):
            return
        self.state = new_state
        self.current_stage = stage
        self.current_lane = LaneStage.from_timeline_stage(stage) if stage else None
        if on_changed:
            on_changed(new_state, stage)

    def reset(self):
        self.state = WorkflowState.IDLE
        self.current_stage = None
        self.current_lane = None


class CGSMidManagerGUI(QObject):
    state_changed = pyqtSignal(object, object)
    lane_execution_requested = pyqtSignal(str, object)
    lane_visibility_changed = pyqtSignal(str, bool)

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.thread = None

        self.backend_mgr = CGSMidManager.get_instance()
        self.session = None
        self.enabled = False
        self._workflow_session = WorkflowSession()

    @property
    def workflow_state(self) -> WorkflowState:
        return self._workflow_session.state

    def set_state(self, state: WorkflowState, stage: TimelineStage | None = None):
        self._workflow_session.transition_to(state, stage, on_changed=self.state_changed.emit)

    def start(self, session_id: str, workflow=None):
        self.enabled = True
        self._workflow_session.reset()
        self.set_state(WorkflowState.RUNNING)

        ctx = ExecutionContext(session_id=session_id)
        ctx.input_state = getattr(self.gui, "input_state", None)
        ctx.process_state = getattr(self.gui, "process_state", None)
        ctx.flow_type = getattr(self.gui, "webs_status", None)  # TODO[1](2026-02-13): 错误引用，根本就无关，删除前需先理清 flow_type 上下文
        ctx.books = getattr(self.gui, "books", {})
        ctx.eps = getattr(self.gui, "eps", {})

        self.session = self.backend_mgr.create_session(
            ctx=ctx,
            workflow=workflow,
            action_sink=self._handle_action,
        )

        self.thread = CGSMidThread(self.gui)
        self.thread.event_signal.connect(self._on_event)
        self.thread.start()

    def stop(self):
        self.enabled = False
        self._workflow_session.reset()
        self.state_changed.emit(WorkflowState.IDLE, None)

        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.quit()
            self.thread.wait(500)
        self.thread = None
        self.session = None

    def _on_event(self, evt):
        if not self.enabled:
            return
        if not self.session:
            return
        self.session.ctx.input_state = getattr(self.gui, "input_state", None)
        self.session.ctx.process_state = getattr(self.gui, "process_state", None)
        self.session.ctx.books = getattr(self.gui, "books", {}) or {}
        self.session.ctx.eps = getattr(self.gui, "eps", {}) or {}

        self._handle_stage_transition(evt.stage)
        self.session.handle_event(evt.stage, evt)

    def _handle_stage_transition(self, stage: TimelineStage):
        wait_stages = {
            TimelineStage.WAIT_SITE,
            TimelineStage.WAIT_SEARCH,
            TimelineStage.WAIT_BOOK_DECISION,
            TimelineStage.WAIT_EP_DECISION,
        }
        if stage in wait_stages:
            if self._workflow_session.state == WorkflowState.RUNNING:
                self.set_state(WorkflowState.WAITING, stage)
                if lane:= LaneStage.from_timeline_stage(stage):
                    self.lane_execution_requested.emit(lane.value, stage)
        elif stage == TimelineStage.FINISHED:
            self._workflow_session.reset()
            self.state_changed.emit(WorkflowState.IDLE, None)
        elif self._workflow_session.state == WorkflowState.WAITING:
            self.set_state(WorkflowState.RUNNING, stage)

    def notify_lane_completed(self, lane: LaneStage):
        if self._workflow_session.state == WorkflowState.WAITING:
            self.set_state(WorkflowState.RUNNING)

    def _handle_action(self, action):
        if action.kind == "send_input_state":
            input_state = action.payload.get("input_state")
            if input_state is not None:
                self.gui.q_InputFieldQueue_send(input_state)
            return
        if action.kind == "request_retry":
            return
        if action.kind == "postprocess_cbz":
            return

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if self.session:
            self.session.ctx.statistics["automation_enabled"] = int(self.enabled)

    def set_stage(self, stage: TimelineStage):
        if self.session:
            self.session.ctx.current_stage = stage

    def set_lane_hidden(self, lane_id: str, hidden: bool):
        self.lane_visibility_changed.emit(lane_id, hidden)
