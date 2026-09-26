"""One reusable local graph worker, isolated from the bridge's protocol and request threads.

Only JSON crosses the private pipes; payload buffers remain in the content-addressed cache.
Local evaluations share a serial lane and the child's in-memory graph cache. Cancelling a queued
request leaves the active evaluation alone. Active work first receives cooperative cancellation;
native code that does not stop within the grace period is terminated with its worker.
"""
import queue
import subprocess
import sys
import threading
import time

import psutil

from .protocol import BridgeError, ERROR_CODES, MAX_LINE_BYTES, decode_line, encode_message

CANCEL_GRACE = 0.5


class _Child:
    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=None, close_fds=True)
        try:
            self.tree = psutil.Process(self.process.pid)
        except psutil.NoSuchProcess:
            self.tree = None
        self.incoming = queue.Queue(maxsize=16)
        self.outgoing = queue.Queue()
        self.stopped = threading.Event()
        self.stop_lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True, name="stk-graph-reader")
        self.writer = threading.Thread(target=self._write, daemon=True, name="stk-graph-writer")
        self.reader.start()
        self.writer.start()

    def _deliver(self, message):
        while not self.stopped.is_set():
            try:
                self.incoming.put(message, timeout=0.05)
                return
            except queue.Full:
                pass

    def _read(self):
        try:
            while not self.stopped.is_set():
                line = self.process.stdout.readline(MAX_LINE_BYTES + 1)
                if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                    break
                self._deliver(decode_line(line))
        except (OSError, ValueError, BridgeError):
            pass
        finally:
            self._deliver(None)

    def _write(self):
        try:
            while not self.stopped.is_set():
                line = self.outgoing.get()
                if line is None:
                    return
                self.process.stdin.write(line)
                self.process.stdin.flush()
        except (OSError, ValueError):
            self._deliver(None)

    def stop(self):
        with self.stop_lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            self.outgoing.put(None)
            # Render nodes may have their own subprocess/session. Stop only this worker's tree,
            # including those descendants, before dropping the worker that owns them.
            descendants = set()
            if self.tree is not None:
                try:
                    self.tree.suspend()
                    for _ in range(2):
                        for process in self.tree.children(recursive=True):
                            descendants.add(process)
                            try:
                                process.suspend()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            for process in descendants:
                try:
                    process.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if self.process.poll() is None:
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
            self.process.wait(timeout=5)
            psutil.wait_procs(descendants, timeout=1)
            self.reader.join(timeout=1)
            self.writer.join(timeout=1)
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass


class GraphWorker:
    def __init__(self, cache_dir, *, command=None):
        self.command = command or [sys.executable, "-m", "suan.desktop_bridge.graph_worker_main",
                                   "--cache-dir", str(cache_dir)]
        self._lane = threading.Lock()
        self._guard = threading.Lock()
        self._child = None
        self._closed = False

    def _check(self, cancelled):
        if cancelled.is_set():
            raise BridgeError("cancelled", "Graph evaluation cancelled")
        if self._closed:
            raise BridgeError("shutting_down", "The graph worker is shutting down")

    def evaluate(self, eval_id, params, cancelled, on_event):
        # A slow startup or a blocked write must not prevent cancellation or bridge shutdown.
        while True:
            self._check(cancelled)
            if self._lane.acquire(timeout=0.05):
                break
        child, healthy = None, False
        try:
            with self._guard:
                self._check(cancelled)
                if self._child is not None and self._child.process.poll() is not None:
                    self._child.stop()
                    self._child = None
                if self._child is None:
                    try:
                        self._child = _Child(self.command)
                    except OSError:
                        raise BridgeError("unavailable", "The local graph worker could not start") from None
                child = self._child
            line = encode_message({"id": eval_id, "params": params})
            if len(line) > MAX_LINE_BYTES:
                raise BridgeError("invalid_params", "The local graph worker request is too large")
            child.outgoing.put(line)
            cancel_deadline = None
            while True:
                if self._closed:
                    raise BridgeError("shutting_down", "The graph worker is shutting down")
                if cancelled.is_set():
                    if cancel_deadline is None:
                        child.outgoing.put(encode_message({"cancel": eval_id}))
                        cancel_deadline = time.monotonic() + CANCEL_GRACE
                    if time.monotonic() >= cancel_deadline:
                        raise BridgeError("cancelled", "Graph evaluation cancelled")
                try:
                    message = child.incoming.get(timeout=0.05)
                except queue.Empty:
                    continue
                if self._closed:
                    raise BridgeError("shutting_down", "The graph worker is shutting down")
                if not isinstance(message, dict) or message.get("id") != eval_id:
                    if cancelled.is_set():
                        raise BridgeError("cancelled", "Graph evaluation cancelled")
                    raise BridgeError("unavailable", "The local graph worker exited or sent an invalid response")
                if "event" in message:
                    if not isinstance(message["event"], dict):
                        raise BridgeError("unavailable", "The local graph worker sent an invalid event")
                    if not cancelled.is_set():
                        on_event(message["event"])
                elif "result" in message:
                    healthy = True
                    self._check(cancelled)
                    return message["result"]
                elif isinstance(message.get("error"), dict) and message["error"].get("code") in ERROR_CODES:
                    error = message["error"]
                    healthy = True
                    self._check(cancelled)
                    raise BridgeError(error["code"], error.get("message", "Graph evaluation failed"),
                                      data=error.get("data"), retryable=error.get("retryable"))
                else:
                    raise BridgeError("unavailable", "The local graph worker sent an invalid response")
        finally:
            try:
                if child is not None and not healthy:
                    with self._guard:
                        if self._child is child:
                            self._child = None
                    child.stop()
            finally:
                self._lane.release()

    def close(self):
        with self._guard:
            self._closed = True
            child, self._child = self._child, None
        if child is not None:
            child.stop()
