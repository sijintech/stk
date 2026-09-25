"""Server-pushed subscriptions: task snapshots, incremental logs, monitoring events, hub events.

Each subscription is a thread polling one backend and emitting events that carry its ``sub`` id.
Offsets in events are byte offsets the app can hand back after a bridge restart to continue
exactly where it stopped (``logs.subscribe`` ``offsets``, ``events.subscribe`` ``offset``).
"""
import codecs
import json
import threading
import time
import uuid

from .protocol import BridgeError

__all__ = ["LogDecoder", "SubscriptionManager"]

LOG_CHUNK = 256 * 1024
LOG_TICK_BYTES = 4 * 1024 * 1024  # at most this much log text per stream per poll
MIN_INTERVAL = 0.5
HUB_INTERVAL = 2.0


class LogDecoder:
    """Incremental UTF-8 decoding of a byte stream read in arbitrary chunks.

    A character split across chunks is held back until its remaining bytes arrive; invalid bytes
    become U+FFFD. ``decoded_offset`` is the byte offset up to which text has been emitted, always
    on a character boundary, so a new decoder started there continues the text exactly.
    """

    def __init__(self, offset=0):
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.read_offset = offset
        self.decoded_offset = offset

    def feed(self, data, final=False):
        text = self.decoder.decode(data, final)
        self.read_offset += len(data)
        pending = len(self.decoder.getstate()[0])
        self.decoded_offset = self.read_offset - pending
        return text


class _Subscription:
    def __init__(self, manager, kind, params):
        self.manager = manager
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.params = params
        self.stop = threading.Event()
        self.failing = False
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._main, daemon=True, name=f"stk-sub-{kind}-{self.id[:8]}")

    def emit(self, event, data):
        if not self.stop.is_set():
            self.manager.emit(event, {"sub": self.id, **data})

    def failed(self, error):
        if not self.failing:
            self.failing = True
            self.emit("subscription.error", {"error": error.to_json()})

    def recovered(self):
        self.failing = False

    def wait(self, seconds):
        return self.stop.wait(seconds) or self.manager.stopping.is_set()

    def _main(self):
        try:
            if not self.ready.wait(30) or self.stop.is_set():
                return
            self.run()
        except BridgeError as exc:
            self.emit("subscription.error", {"error": exc.to_json(), "final": True})
        except Exception as exc:
            error = BridgeError("internal_error", f"{type(exc).__name__}: {exc}")
            self.emit("subscription.error", {"error": error.to_json(), "final": True})
        finally:
            self.manager.forget(self.id)


class _Watch(_Subscription):
    def run(self):
        backend = self.manager.backend_for(self.params["connection"], self.params.get("node"))
        interval = max(MIN_INTERVAL, float(self.params.get("interval", 2.0)))
        workspace = self.params.get("workspace_id")
        wanted = set(self.params.get("task_ids") or ())
        last = None
        while True:
            try:
                tasks = backend.tasks(workspace)["tasks"]
                if wanted:
                    tasks = [t for t in tasks if t.get("id") in wanted]
                body = json.dumps(tasks, sort_keys=True)
                if body != last:
                    self.emit("watch.snapshot", {"tasks": tasks, "time": time.time()})
                    last = body
                self.recovered()
            except BridgeError as exc:
                if exc.code in ("not_found", "unauthorized", "invalid_params", "unsupported"):
                    raise
                self.failed(exc)
            if self.wait(interval):
                return


class _Logs(_Subscription):
    def run(self):
        backend = self.manager.backend_for(self.params["connection"], self.params.get("node"))
        task_id = self.params["task_id"]
        streams = list(dict.fromkeys(self.params.get("streams") or ["stdout", "stderr"]))
        offsets = self.params.get("offsets") or {}
        chunk = int(self.params.get("chunk_bytes", LOG_CHUNK))
        decoders = {s: LogDecoder(int(offsets.get(s, 0))) for s in streams}
        # A stream ends after two empty reads of a finished task (the second one after a pause), so
        # bytes written just before the task finished are never missed.
        drained = {s: False for s in streams}
        idle = HUB_INTERVAL if backend.kind == "hub" else MIN_INTERVAL
        while True:
            try:
                for stream in streams:
                    if drained[stream] is True:
                        continue
                    decoder = decoders[stream]
                    budget = LOG_TICK_BYTES
                    while True:
                        start = decoder.decoded_offset
                        response = backend.logs(task_id, stream, decoder.read_offset, chunk)
                        data = response["data"]
                        text = decoder.feed(data)
                        final = not data and response["terminal"] and drained[stream] == "once"
                        if final:
                            text += decoder.feed(b"", final=True)
                            drained[stream] = True
                        elif not data and response["terminal"]:
                            drained[stream] = "once"
                        elif data:
                            drained[stream] = False
                        if text:
                            self.emit("logs.chunk", {"stream": stream, "text": text, "offset": start,
                                                     "next_offset": decoder.decoded_offset})
                        budget -= len(data)
                        if not data or budget <= 0 or self.stop.is_set():
                            break
                self.recovered()
            except BridgeError as exc:
                if exc.code in ("not_found", "unauthorized", "invalid_params", "unsupported"):
                    raise
                self.failed(exc)
            if all(value is True for value in drained.values()):
                self.emit("logs.end", {"offsets": {s: d.decoded_offset for s, d in decoders.items()}})
                return
            if self.wait(idle):
                return


class _Events(_Subscription):
    def run(self):
        backend = self.manager.backend_for(self.params["connection"], self.params.get("node"))
        task_id = self.params["task_id"]
        offset = int(self.params.get("offset", 0))
        idle = HUB_INTERVAL if backend.kind == "hub" else MIN_INTERVAL
        while True:
            try:
                result = backend.events(task_id, offset)
                events, invalid = result.get("events") or [], result.get("invalid") or []
                if events or invalid:
                    self.emit("events.batch", {"events": events, "invalid": invalid, "offset": offset,
                                               "next_offset": result["next_offset"]})
                progressed = result["next_offset"] > offset
                offset = result["next_offset"]
                self.recovered()
                if result.get("terminal") and offset >= result.get("size", offset) and not progressed:
                    self.emit("events.end", {"next_offset": offset})
                    return
                if progressed:
                    continue
            except BridgeError as exc:
                if exc.code in ("not_found", "unauthorized", "invalid_params", "unsupported"):
                    raise
                self.failed(exc)
            if self.wait(idle):
                return


class _HubEvents(_Subscription):
    def run(self):
        hub = self.manager.hub_for(self.params["connection"])
        cursor = int(self.params.get("after", 0))
        delay = 1.0
        while not self.stop.is_set() and not self.manager.stopping.is_set():
            try:
                for cursor, kind, payload in hub.events(cursor, self.stop):
                    self.emit("hub.event", {"cursor": cursor, "kind": kind, "payload": payload})
                    delay = 1.0
                self.recovered()
            except Exception as exc:
                from .hub import hub_error
                error = hub_error(exc)
                if error.code == "unauthorized":
                    raise error from None
                self.failed(error)
            if self.wait(delay):
                return
            delay = min(30.0, delay * 2)


KINDS = {"watch": _Watch, "logs": _Logs, "events": _Events, "hub": _HubEvents}


class SubscriptionManager:
    def __init__(self, emit, backend_for, hub_for):
        self.emit = emit
        self.backend_for = backend_for
        self.hub_for = hub_for
        self.lock = threading.Lock()
        self.active = {}
        self.stopping = threading.Event()

    def start(self, kind, params):
        # Resolve the connection now, so an unknown connection fails the subscribe request itself.
        if kind == "hub":
            self.hub_for(params["connection"])
        else:
            self.backend_for(params["connection"], params.get("node"))
        subscription = KINDS[kind](self, kind, params)
        with self.lock:
            self.active[subscription.id] = subscription
        subscription.thread.start()
        return subscription

    def cancel(self, sub_id):
        with self.lock:
            subscription = self.active.pop(sub_id, None)
        if subscription is None:
            raise BridgeError("not_found", "Unknown or finished subscription")
        subscription.stop.set()

    def forget(self, sub_id):
        with self.lock:
            self.active.pop(sub_id, None)

    def stop_all(self, timeout=2.0):
        self.stopping.set()
        with self.lock:
            subscriptions = list(self.active.values())
            self.active.clear()
        for subscription in subscriptions:
            subscription.stop.set()
        deadline = time.monotonic() + timeout
        for subscription in subscriptions:
            subscription.thread.join(timeout=max(0.0, deadline - time.monotonic()))
