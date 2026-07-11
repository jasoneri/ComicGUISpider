from __future__ import annotations

import sys
import threading
import traceback
import weakref
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.core.font import font_color


@dataclass(frozen=True, slots=True)
class GuiExceptionRecord:
    exception_type_name: str
    exception_message: str
    traceback_text: str
    summary: str
    log_path: str
    origin_thread_name: str


ExceptionPresenter = Callable[[GuiExceptionRecord, QWidget], None]
OriginalExceptionHook = Callable[[type[BaseException], BaseException, object], None]


@dataclass(slots=True)
class _FeedbackScope:
    owner_reference: weakref.ReferenceType[QWidget]
    surface_references: tuple[weakref.ReferenceType[QWidget], ...]
    presenter: ExceptionPresenter


class FeedbackScopeRegistration:
    def __init__(self, dispatcher: "GuiExceptionFeedbackDispatcher", scope_identifier: int):
        self._dispatcher_reference = weakref.ref(dispatcher)
        self._scope_identifier = scope_identifier

    def close(self):
        dispatcher = self._dispatcher_reference()
        if dispatcher is None:
            return
        dispatcher.unregister_scope(self._scope_identifier)


class GuiExceptionFeedbackDispatcher(QObject):
    feedback_requested = Signal(object)

    def __init__(self, parent: QObject | None = None, *, failure_hook: OriginalExceptionHook | None = None):
        super().__init__(parent)
        self._failure_hook = failure_hook or sys.__excepthook__
        self._scopes: dict[int, _FeedbackScope] = {}
        self._scope_order: list[int] = []
        self._next_scope_identifier = 1
        self.feedback_requested.connect(self._present_record, Qt.QueuedConnection)

    def register_scope(
        self,
        *,
        owner: QWidget,
        surfaces: Iterable[QWidget],
        presenter: ExceptionPresenter,
    ) -> FeedbackScopeRegistration:
        scope_identifier = self._next_scope_identifier
        self._next_scope_identifier += 1
        registered_surfaces = tuple(dict.fromkeys((owner, *surfaces)))
        self._scopes[scope_identifier] = _FeedbackScope(
            owner_reference=weakref.ref(owner),
            surface_references=tuple(weakref.ref(surface) for surface in registered_surfaces),
            presenter=presenter,
        )
        self._scope_order.append(scope_identifier)
        registration = FeedbackScopeRegistration(self, scope_identifier)
        owner.destroyed.connect(lambda *_args: registration.close())
        return registration

    def unregister_scope(self, scope_identifier: int):
        self._scopes.pop(scope_identifier, None)
        if scope_identifier in self._scope_order:
            self._scope_order.remove(scope_identifier)

    def submit(self, record: GuiExceptionRecord):
        if QThread.currentThread() is self.thread():
            self._present_record(record)
            return
        self.feedback_requested.emit(record)

    @Slot(object)
    def _present_record(self, record: GuiExceptionRecord):
        resolved_feedback = self._resolve_feedback_target()
        if resolved_feedback is None:
            return
        presenter, target = resolved_feedback
        try:
            presenter(record, target)
        except Exception as presenter_error:
            self._failure_hook(type(presenter_error), presenter_error, presenter_error.__traceback__)

    def _resolve_feedback_target(self) -> tuple[ExceptionPresenter, QWidget] | None:
        active_window = QApplication.activeWindow()
        for scope_identifier in reversed(self._scope_order):
            scope = self._scopes.get(scope_identifier)
            if scope is None:
                continue
            for surface_reference in scope.surface_references:
                surface = surface_reference()
                if surface is not None and surface is active_window:
                    return scope.presenter, surface

        for scope_identifier in reversed(self._scope_order):
            scope = self._scopes.get(scope_identifier)
            if scope is None:
                continue
            owner = scope.owner_reference()
            if owner is not None:
                return scope.presenter, owner
        return None


class GuiExceptionCoordinator:
    def __init__(
        self,
        *,
        logger,
        dispatcher: GuiExceptionFeedbackDispatcher,
        log_path: str | Path,
        fallback_hook: OriginalExceptionHook | None = None,
    ):
        self._logger = logger
        self._dispatcher = dispatcher
        self._log_path = str(log_path)
        self._fallback_hook = fallback_hook or sys.__excepthook__
        self._routing_state = threading.local()

    def handle_exception(self, exception_type, exception_value, exception_traceback):
        if getattr(self._routing_state, "active", False):
            self._fallback_hook(exception_type, exception_value, exception_traceback)
            return

        self._routing_state.active = True
        try:
            traceback_text = "".join(traceback.format_exception(exception_type, exception_value, exception_traceback))
            exception_message = str(exception_value).strip()
            summary = exception_type.__name__
            if exception_message:
                summary = f"{summary}: {exception_message}"
            record = GuiExceptionRecord(
                exception_type_name=exception_type.__name__,
                exception_message=exception_message,
                traceback_text=traceback_text,
                summary=summary,
                log_path=self._log_path,
                origin_thread_name=threading.current_thread().name,
            )
            self._logger.error(traceback_text)
            self._dispatcher.submit(record)
        except Exception as routing_error:
            self._fallback_hook(type(routing_error), routing_error, routing_error.__traceback__)
            self._fallback_hook(exception_type, exception_value, exception_traceback)
        finally:
            self._routing_state.active = False


class InfoBarExceptionPresenter:
    def __call__(self, record: GuiExceptionRecord, target: QWidget):
        InfoBar.error(
            title="",
            content=f"{record.summary}。详情见日志：{record.log_path}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=-1,
            parent=target,
        )


class SpiderGuiExceptionPresenter:
    def __init__(self, feedback_callback: Callable[[str, str], None], guidance_text: str):
        self._feedback_callback = feedback_callback
        self._guidance_text = guidance_text

    def __call__(self, record: GuiExceptionRecord, _target: QWidget):
        headline = font_color(record.summary, cls="theme-err", size=4)
        guidance = font_color(
            f"<br>{self._guidance_text} <br>[{record.log_path}]<br>",
            cls="theme-err",
            size=3,
        )
        self._feedback_callback(headline, guidance)
