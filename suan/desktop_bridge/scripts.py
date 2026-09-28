"""One bounded-output, persistent Python session per local desktop bridge.

The process is disposable; the project database and submitted Runtime tasks are not. Interrupting
code resets its Python namespace and never replays or rolls back already accepted operations.
"""
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import queue
import sys
import threading
from uuid import uuid4

from .protocol import BridgeError, MAX_LINE_BYTES, encode_message
from .worker_process import WorkerProcess

OUTPUT_LIMIT = 1024 * 1024  # Unicode characters; cursor units intentionally differ from byte logs.
SOURCE_LIMIT = 1024 * 1024


@dataclass
class _Session:
    id: str
    directory: str
    state: str = "ready"
    kernel: str | None = None
    child: object = None
    pump: object = None
    run: dict | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    output: deque = field(default_factory=deque)
    output_size: int = 0
    output_end: int = 0
    notified: bool = False


class ScriptSessions:
    def __init__(self, emit, call):
        self.emit, self.call = emit, call
        self.lock = threading.RLock()
        self.session = None
        self.closed = False

    def _get(self, params):
        if self.closed:
            raise BridgeError("shutting_down", "Python sessions are shutting down")
        if self.session is None or self.session.id != params["session"]:
            raise BridgeError("not_found", "Python session is closed or belongs to an earlier bridge")
        return self.session

    @staticmethod
    def _status(session):
        return {"session": session.id, "state": session.state, "kernel": session.kernel,
                "directory": session.directory, "run": dict(session.run) if session.run else None,
                "output_start": session.output_end - session.output_size, "output_end": session.output_end}

    def open(self, params):
        with self.lock:
            if self.closed:
                raise BridgeError("shutting_down", "Python sessions are shutting down")
            directory = Path(params.get("directory", str(Path.cwd())))
            if not directory.is_absolute() or not directory.is_dir():
                raise BridgeError("invalid_params", "Python working directory must be an existing absolute directory")
            directory = str(directory.resolve())
            if self.session is not None:
                if "directory" in params and self.session.directory != directory:
                    raise BridgeError("conflict", "Close the Python session before changing its initial directory")
            else:
                self.session = _Session(uuid4().hex, directory)
            return self._status(self.session)

    def status(self, params):
        with self.lock:
            return self._status(self._get(params))

    def _changed(self, session, *, force=False):
        with self.lock:
            if self.session is not session or self.closed or (session.notified and not force):
                return
            session.notified = True
        self.emit("script.changed", {"session": session.id})

    def _output(self, session, value):
        with self.lock:
            session.output.append(value)
            session.output_size += len(value)
            session.output_end += len(value)
            while session.output_size > OUTPUT_LIMIT:
                first = session.output.popleft()
                excess = session.output_size - OUTPUT_LIMIT
                session.output_size -= min(excess, len(first))
                if excess < len(first):
                    session.output.appendleft(first[excess:])
        self._changed(session)

    def read(self, params):
        with self.lock:
            session = self._get(params)
            cursor, limit = params.get("cursor", 0), params.get("limit", 65536)
            if cursor > session.output_end:
                raise BridgeError("invalid_params", "Output cursor is beyond the end of this session")
            start = session.output_end - session.output_size
            actual = max(start, cursor)
            text = "".join(session.output)[actual - start:actual - start + limit]
            session.notified = False
            return {**self._status(session), "text": text, "cursor": actual + len(text), "truncated": cursor < start}

    @staticmethod
    def _source(params):
        if "source" in params:
            source, filename = params["source"], "<console>"
        else:
            path = Path(params["path"])
            if not path.is_absolute() or not path.is_file():
                raise BridgeError("not_found", "Script path must be an existing absolute file")
            try:
                with path.open("rb") as stream:
                    raw = stream.read(SOURCE_LIMIT + 1)
                if len(raw) > SOURCE_LIMIT:
                    raise BridgeError("invalid_params", "Script file exceeds 1 MiB")
                source, filename = raw.decode("utf-8-sig"), str(path.resolve())
            except (OSError, UnicodeError) as exc:
                raise BridgeError("invalid_params", f"Cannot read UTF-8 script: {exc}") from None
        if len(source.encode("utf-8")) > SOURCE_LIMIT:
            raise BridgeError("invalid_params", "Script source exceeds 1 MiB")
        return source, filename

    def execute(self, params, context):
        source, filename = self._source(params)
        with self.lock:
            session = self._get(params)
            if session.state != "ready":
                raise BridgeError("busy", "The Python session is still executing or stopping", retryable=True)
            if session.child is None:
                try:
                    session.child = WorkerProcess([sys.executable, "-m", "suan.desktop_bridge.script_worker_main"],
                                                   cwd=session.directory)
                except OSError as exc:
                    raise BridgeError("unavailable", f"Cannot start the Python worker: {exc}") from None
                session.kernel = uuid4().hex
                session.pump = threading.Thread(target=self._pump, args=(session, session.child),
                                                daemon=True, name="stk-script-session")
                session.pump.start()
            session.cancelled.clear()
            session.state = "running"
            session.run = {"id": uuid4().hex, "state": "running", "filename": filename, "error": None}
            child = session.child
            message = {"id": session.run["id"], "source": source, "filename": filename,
                       "project_handle": params.get("project_handle")}
            # Starting after the execute response lets the UI establish its run identity first.
            context.after(lambda: self._start(session, child, message))
            return {"run": session.run["id"]}

    def _start(self, session, child, message):
        with self.lock:
            if self.session is not session or session.cancelled.is_set() or child.stopped.is_set():
                return
            child.outgoing.put(encode_message(message))
        self._changed(session, force=True)

    def _pump(self, session, child):
        error = None
        try:
            while not child.stopped.is_set():
                try:
                    message = child.incoming.get(timeout=0.05)
                except queue.Empty:
                    continue
                if not isinstance(message, dict):
                    raise BridgeError("unavailable", "The Python worker exited; its namespace has been reset")
                if isinstance(message.get("output"), str):
                    self._output(session, message["output"])
                    continue
                with self.lock:
                    if session.run is None or message.get("id") != session.run["id"] or session.state != "running":
                        if session.cancelled.is_set():
                            break
                        raise BridgeError("unavailable", "The Python worker sent an invalid response")
                if "call" in message:
                    response = {"reply": message["call"]}
                    try:
                        response["result"] = self.call(message["operation"], message["params"], session.cancelled)
                    except BridgeError as exc:
                        response["error"] = exc.to_json()
                    except Exception as exc:
                        response["error"] = BridgeError("internal_error", f"{type(exc).__name__}: {exc}").to_json()
                    line = encode_message(response)
                    if len(line) > MAX_LINE_BYTES:
                        line = encode_message({"reply": message["call"], "error": BridgeError(
                            "result_too_large", "The operation result exceeds the bridge message limit").to_json()})
                    if not child.stopped.is_set():
                        child.outgoing.put(line)
                elif isinstance(message.get("finished"), bool):
                    with self.lock:
                        if not session.cancelled.is_set():
                            session.state = "ready"
                            session.run["state"] = "succeeded" if message["finished"] else "failed"
                    self._changed(session, force=True)
                else:
                    raise BridgeError("unavailable", "The Python worker sent an invalid message")
        except Exception as exc:
            error = exc.to_json() if isinstance(exc, BridgeError) else BridgeError("internal_error", str(exc)).to_json()
        finally:
            child.stop()
            with self.lock:
                if session.child is child:
                    session.child = None
                    session.kernel = None
                    session.state = "ready"
                    if session.run is not None and session.run["state"] == "running":
                        session.run["state"] = "cancelled" if session.cancelled.is_set() else "failed"
                        session.run["error"] = None if session.cancelled.is_set() else error
            self._changed(session, force=True)

    def interrupt(self, params):
        with self.lock:
            session = self._get(params)
            interrupted = session.state == "running"
            child = session.child
            if child is not None:
                session.state = "stopping"
                session.cancelled.set()
        if child is not None:
            child.stop()
        self._changed(session, force=True)
        return {"interrupted": interrupted}

    def close(self, params):
        with self.lock:
            session = self._get(params)
            self.session = None
            session.cancelled.set()
            child = session.child
        if child is not None:
            child.stop()
        return {"closed": True}

    def shutdown(self):
        with self.lock:
            self.closed = True
            session, self.session = self.session, None
            if session is not None:
                session.cancelled.set()
        if session is not None and session.child is not None:
            session.child.stop()
