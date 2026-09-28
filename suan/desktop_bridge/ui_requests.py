"""Explicit local desktop control extension; requests are executed by the attached UI thread.

This is not a network endpoint. A bridge has at most one attached desktop on its private stdio
channel. Session and request IDs reject replies from detached/restarted desktops. A timeout or
cancellation does not imply that an already accepted UI mutation was rolled back.
"""
from dataclasses import dataclass, field
import threading
import time
from uuid import uuid4

from .protocol import BridgeError

UI_OPERATIONS = ("layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close")


@dataclass
class _Pending:
    ready: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: dict | None = None


class UIRequests:
    def __init__(self, emit):
        self.emit = emit
        self.lock = threading.Lock()
        self.session = None
        self.operations = ()
        self.pending = {}
        self.closed = False

    def attach(self, params):
        with self.lock:
            if self.closed:
                raise BridgeError("shutting_down", "Desktop control is shutting down")
            operations = tuple(sorted(set(params["operations"])))
            if self.session is not None and operations != self.operations:
                raise BridgeError("conflict", "Detach the current desktop before changing its capabilities")
            if self.session is None:
                self.session = uuid4().hex
                self.operations = operations
            return {"session": self.session, "operations": list(self.operations)}

    def _detach(self):
        self.session = None
        self.operations = ()
        for pending in self.pending.values():
            pending.error = BridgeError("unavailable", "The desktop session was detached").to_json()
            pending.ready.set()
        self.pending.clear()

    def detach(self, params):
        with self.lock:
            matched = self.session is not None and params["session"] == self.session
            if matched:
                self._detach()
            return {"detached": matched}

    def reply(self, params):
        with self.lock:
            pending = self.pending.get(params["request"]) if params["session"] == self.session else None
            if pending is None or pending.ready.is_set():
                return {"accepted": False}
            pending.result = params.get("result")
            pending.error = params.get("error")
            pending.ready.set()
            return {"accepted": True}

    def call(self, operation, params, cancelled, *, timeout=30.0):
        request, pending = uuid4().hex, _Pending()
        with self.lock:
            if self.closed:
                raise BridgeError("shutting_down", "Desktop control is shutting down")
            if self.session is None:
                raise BridgeError("unavailable", "No desktop is attached to this Python session")
            if operation not in self.operations:
                raise BridgeError("unsupported", f"The desktop does not support {operation!r}")
            if cancelled.is_set():
                raise BridgeError("cancelled", "Script execution interrupted")
            self.pending[request] = pending
            session = self.session
        try:
            deadline = time.monotonic() + timeout
            self.emit("ui.request", {"session": session, "request": request, "operation": operation, "params": params,
                                     "expires_at_ms": int((time.time() + timeout) * 1000)})
            while True:
                if cancelled.is_set():
                    raise BridgeError("cancelled", "Script execution interrupted; an accepted UI change may have completed")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeError("timeout", "The desktop did not reply; inspect its state before repeating a change")
                if pending.ready.wait(min(remaining, 0.05)):
                    break
            if pending.error is not None:
                error = pending.error
                raise BridgeError(error["code"], error["message"], data=error.get("data"), retryable=error.get("retryable"))
            return pending.result
        finally:
            with self.lock:
                self.pending.pop(request, None)

    def close(self):
        with self.lock:
            self.closed = True
            self._detach()
