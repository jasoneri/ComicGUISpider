# -*- coding: utf-8 -*-
from PyQt5.QtCore import QObject

from GUI.thread.mid import CGSMidThread
from utils.middleware.core import CGSMidManager, ExecutionContext
from utils.middleware.timeline import TimelineStage


class CGSMidManagerGUI(QObject):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.thread = None

        self.backend_mgr = CGSMidManager.get_instance()
        self.session = None
        self.enabled = False

    def start(self, session_id: str, workflow=None):
        self.enabled = True
        ctx = ExecutionContext(session_id=session_id)
        ctx.input_state = getattr(self.gui, "input_state", None)
        ctx.process_state = getattr(self.gui, "process_state", None)
        ctx.flow_type = getattr(self.gui, "webs_status", None)
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
        self.session.handle_event(evt.stage, evt)

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
