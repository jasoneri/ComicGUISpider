# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t
from enum import Enum
from uuid import uuid4
from PyQt5.QtCore import QObject, pyqtSignal

from utils.middleware.core import CGSMidManager, ExecutionContext
from utils.middleware.executor import Action
from utils.middleware.timeline import Event, EventSource, TimelineStage, LaneStage, stage_from_process_name
from utils.middleware.lane_router import LaneActionRouter
from utils.middleware.lane_handlers import DEFAULT_LANE_HANDLERS

if t.TYPE_CHECKING:
    from GUI.gui import SpiderGUI


# ---------------------------------------------------------------------------
# Workflow state machine
# ---------------------------------------------------------------------------

class WorkflowState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"


class WorkflowSession:
    _VALID_TRANSITIONS = {
        WorkflowState.IDLE: {WorkflowState.RUNNING},
        WorkflowState.RUNNING: {WorkflowState.WAITING, WorkflowState.IDLE},
        WorkflowState.WAITING: {WorkflowState.RUNNING, WorkflowState.WAITING},
    }

    def __init__(self):
        self.state = WorkflowState.IDLE
        self.current_stage: TimelineStage | None = None
        self.current_lane: LaneStage | None = None

    def transition_to(self, new_state: WorkflowState, stage: TimelineStage | None = None,
                      on_changed=None, on_rejected=None) -> bool:
        if self.state == new_state and self.current_stage == stage:
            return True

        if new_state not in self._VALID_TRANSITIONS.get(self.state, set()):
            if on_rejected:
                on_rejected(self.state, new_state, stage)
            return False
        self.state = new_state
        self.current_stage = stage
        self.current_lane = LaneStage.from_timeline_stage(stage) if stage else None
        if on_changed:
            on_changed(new_state, stage)
        return True

    def reset(self):
        self.state = WorkflowState.IDLE
        self.current_stage = None
        self.current_lane = None


# ---------------------------------------------------------------------------
# Lane action routing (OOP)
# ---------------------------------------------------------------------------

class SpiderGuiOps:
    def __init__(self, gui: SpiderGUI):
        self.gui = gui

    def select_site(self, site_index: int):
        self.gui.chooseBox.setCurrentIndex(site_index)

    def submit_search(self, keyword: str, site_index: int | None = None):
        self.gui.start_and_search(keyword=keyword, site_index=site_index)

    def select_books(self, indexes, page_turn: str = ""):
        self.gui.submit_decision("BOOK", indexes, page_turn=page_turn)

    def select_eps(self, episodes):
        if not episodes:
            return
        book = episodes[0].from_book
        book.episodes = list(episodes)
        self.gui.submit_decision("EP", book)

    def run_postprocess(self, **kwargs):
        if log := getattr(self.gui, "log", None):
            log.info("[CGSMid] postprocess triggered: %s", kwargs)


# ---------------------------------------------------------------------------
# CGSMidManagerGUI
# ---------------------------------------------------------------------------

class CGSMidManagerGUI(QObject):
    state_changed = pyqtSignal(object, object)
    lane_execution_requested = pyqtSignal(str, object)
    lane_visibility_changed = pyqtSignal(str, bool)
    transition_rejected = pyqtSignal(object, object, object)
    action_requested = pyqtSignal(object)

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.thread = None
        self._process_stage = ""

        self.backend_mgr = CGSMidManager.get_instance()
        self.session = None
        self.enabled = False
        self._workflow = None
        self._workflow_session = WorkflowSession()

        self._ops = SpiderGuiOps(gui)
        self._router = LaneActionRouter()
        for handler_cls in DEFAULT_LANE_HANDLERS:
            self._router.register(handler_cls())

    @property
    def workflow_state(self) -> WorkflowState:
        return self._workflow_session.state

    def _new_session_id(self) -> str:
        return f"mid-{uuid4().hex[:12]}"

    def _on_transition_rejected(self, from_state, to_state, stage):
        self.transition_rejected.emit(from_state, to_state, stage)
        if log := getattr(self.gui, "log", None):
            log.warning(
                "[CGSMid] transition rejected: %s -> %s (stage=%s)",
                getattr(from_state, "name", from_state),
                getattr(to_state, "name", to_state),
                stage,
            )

    def set_state(self, state: WorkflowState, stage: TimelineStage | None = None) -> bool:
        return self._workflow_session.transition_to(
            state, stage,
            on_changed=self.state_changed.emit,
            on_rejected=self._on_transition_rejected,
        )

    def _sync_ctx_from_gui(self):
        if not self.session:
            return
        self.session.ctx.input_state = None
        self.session.ctx.process_state = self._process_stage
        self.session.ctx.books = getattr(self.gui, "books", {}) or {}
        self.session.ctx.eps = getattr(self.gui, "eps", {}) or {}

    def ensure_session(self, session_id: str | None = None, workflow=None, force_restart: bool = False):
        if workflow is not None:
            self._workflow = workflow

        if force_restart and self.session:
            self.stop()
            self.enabled = True

        if self.session:
            return

        ctx = ExecutionContext(session_id=session_id or self._new_session_id())
        ctx.flow_type = getattr(self.gui, "webs_status", None)
        self.session = self.backend_mgr.create_session(
            ctx=ctx,
            workflow=self._workflow,
            action_sink=self._handle_action,
        )
        self._sync_ctx_from_gui()
        self.session.ctx.statistics["automation_enabled"] = int(self.enabled)

    def dispatch_event(self, evt: Event) -> list:
        if not self.enabled or evt is None:
            return []
        self.ensure_session()
        if not self.session:
            return []
        self._sync_ctx_from_gui()
        self._handle_stage_transition(evt.stage)
        return self.session.handle_event(evt.stage, evt)

    def dispatch_stage(self, stage: TimelineStage, source: EventSource, payload: dict | None = None) -> list:
        return self.dispatch_event(Event(source=source, stage=stage, payload=payload or {}))

    def start(self, session_id: str, workflow=None):
        self.enabled = True
        self.ensure_session(session_id=session_id, workflow=workflow, force_restart=True)
        self._workflow_session.reset()
        self.set_state(WorkflowState.RUNNING)
        self.dispatch_stage(TimelineStage.WAIT_SITE, EventSource.UI, {"reason": "start"})

    def stop(self):
        self.enabled = False
        self._workflow_session.reset()
        self.state_changed.emit(WorkflowState.IDLE, None)
        self._process_stage = ""

        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.quit()
            self.thread.wait(500)
        self.thread = None
        self.session = None

    def rebind(self, gui):
        self.gui = gui
        self._ops.gui = gui
        if self.session:
            self.session.ctx.flow_type = getattr(self.gui, "webs_status", None)
            self._sync_ctx_from_gui()

    def on_process_stage(self, stage_str: str):
        self._process_stage = stage_str or ""
        stage = stage_from_process_name(self._process_stage)
        if stage is None:
            return []
        return self.dispatch_stage(
            stage,
            EventSource.PROCESS_QUEUE,
            {"process_state": self._process_stage},
        )

    def _handle_stage_transition(self, stage: TimelineStage):
        wait_stages = {
            TimelineStage.WAIT_SITE,
            TimelineStage.WAIT_SEARCH,
            TimelineStage.WAIT_BOOK_DECISION,
            TimelineStage.WAIT_EP_DECISION,
        }
        if stage in wait_stages:
            if self._workflow_session.state == WorkflowState.IDLE:
                self.set_state(WorkflowState.RUNNING)
            if self._workflow_session.state in (WorkflowState.RUNNING, WorkflowState.WAITING):
                prev_stage = self._workflow_session.current_stage
                if self.set_state(WorkflowState.WAITING, stage):
                    if stage != prev_stage and (lane := LaneStage.from_timeline_stage(stage)):
                        self.lane_execution_requested.emit(lane.value, stage)
        elif stage == TimelineStage.FINISHED:
            self._workflow_session.reset()
            self.state_changed.emit(WorkflowState.IDLE, None)
        elif self._workflow_session.state == WorkflowState.WAITING:
            self.set_state(WorkflowState.RUNNING, stage)

    def _current_stage_lane(self) -> LaneStage | None:
        stage = self._workflow_session.current_stage
        if stage is None:
            return None
        return LaneStage.from_timeline_stage(stage)

    def notify_lane_completed(self, lane: LaneStage):
        if self._workflow_session.state != WorkflowState.WAITING:
            return
        if not self.enabled or not self.session:
            return
        stage = self._workflow_session.current_stage
        stage_lane = self._current_stage_lane()
        if stage is None or stage_lane is None or lane != stage_lane:
            return
        actions = self.dispatch_stage(stage, EventSource.UI, {"trigger": "lane_play"})
        if actions:
            self.set_state(WorkflowState.RUNNING)

    def _handle_action(self, action: Action):
        if not action.lane and (lane := self._current_stage_lane()):
            action.lane = lane.value
        if not self._router.dispatch(action, self._ops):
            if log := getattr(self.gui, "log", None):
                log.warning("[CGSMid] unhandled action: lane=%s kind=%s", action.lane, action.kind)
        self.action_requested.emit(action)

    def set_enabled(self, enabled: bool, workflow=None, force_restart: bool = False):
        if not bool(enabled):
            self.stop()
            return

        self.enabled = True
        self.ensure_session(workflow=workflow, force_restart=force_restart)
        if self.session:
            self.session.ctx.statistics["automation_enabled"] = 1

        if self._workflow_session.state == WorkflowState.IDLE:
            self.set_state(WorkflowState.RUNNING)
            self.dispatch_stage(
                TimelineStage.WAIT_SITE,
                EventSource.UI,
                {"reason": "enabled"},
            )

    def set_stage(self, stage: TimelineStage):
        if self.session:
            self.session.ctx.current_stage = stage

    def set_lane_hidden(self, lane_id: str, hidden: bool):
        # TODO[2](2026-02-09): 遗留对rulePanel的可用规则隐藏
        self.lane_visibility_changed.emit(lane_id, hidden)
