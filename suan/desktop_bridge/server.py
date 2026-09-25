"""The bridge process: request dispatch, responses, events, lifecycle (spec §2-§5).

Requests are handled concurrently (one thread each, at most :data:`MAX_INFLIGHT`), so responses
can arrive in any order; the app matches them by ``id``. Every write to the protocol stream is one
complete line under a lock. Params are validated against ``desktop-bridge-1.schema.json`` before a
handler runs; with ``strict`` the bridge also validates every message it sends (tests, CI).
"""
import os
from pathlib import Path
import platform
import sys
import threading
import time

from suan.runtime.common import inside

from . import schema as bridge_schema
from .backends import HubBackend
from .connections import ConnectionStore
from .graphs import GraphService
from .protocol import (MAX_LINE_BYTES, PROTOCOL_VERSION, BridgeError, LineReader, check_envelope, decode_line,
                       encode_message, error_object)
from .subscriptions import SubscriptionManager
from .transfers import TransferManager

__all__ = ["Bridge", "default_state_dir"]

VERSION = "1.0.0"
MAX_INFLIGHT = 64
SHUTDOWN_GRACE = 5.0


def default_state_dir():
    return Path(os.environ.get("STK_DESKTOP_BRIDGE_DIR", str(Path.home() / ".stk" / "desktop-bridge")))


class _Context:
    def __init__(self):
        self.callbacks = []

    def after(self, callback):
        """Run ``callback`` once the response has been written (subscriptions start then)."""
        self.callbacks.append(callback)


class Bridge:
    def __init__(self, state_dir=None, cache_dir=None, *, writer, strict=False, max_line=MAX_LINE_BYTES,
                 on_exit=None):
        self.state_dir = Path(state_dir) if state_dir else default_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.cache_dir = Path(cache_dir) if cache_dir else self.state_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.download_dir = self.cache_dir / "downloads"
        self.writer = writer
        self.strict = strict
        self.max_line = max_line
        self.on_exit = on_exit
        self.write_lock = threading.Lock()
        self.inflight = {}
        self.inflight_lock = threading.Lock()
        self.closing = threading.Event()
        self.closed = threading.Event()
        self.inspected = {}
        self.connections = ConnectionStore(self.state_dir)
        self.graphs = GraphService(self.cache_dir, self.connections, self.emit)
        self.transfers = TransferManager(self.state_dir, self.emit, self.connections.backend)
        self.subscriptions = SubscriptionManager(self.emit, self.connections.backend, self.connections.hub_client)
        self.methods = {
            "hello": self.hello,
            "shutdown": self.shutdown_method,
            "connections.list": lambda p, c: {"connections": self.connections.list()},
            "connections.add_runtime": self.add_runtime,
            "connections.remove": self.remove_connection,
            "connections.check": self.check_connection,
            "connections.pair_hub": self.pair_hub,
            "connections.local": lambda p, c: self.connections.local_status(),
            "connections.local_start": lambda p, c: self.connections.local_start(),
            "hub.devices": self.hub_devices,
            "hub.templates": self.hub_templates,
            "hub.actions": self.hub_actions,
            "hub.action": self.hub_action,
            "hub.review": self.hub_review,
            "hub.subscribe": lambda p, c: self._subscribe("hub", p, c),
            "workspace.list": lambda p, c: self._backend(p).workspaces(),
            "workspace.create": lambda p, c: self._backend(p).create_workspace(p["name"], p.get("idempotency_key")),
            "workspace.files": lambda p, c: self._backend(p).files(p["workspace_id"]),
            "upload.start": self.upload_start,
            "download.start": self.download_start,
            "transfer.list": lambda p, c: {"transfers": self.transfers.list()},
            "transfer.get": lambda p, c: {"transfer": self.transfers.public(self.transfers.load(p["id"]))},
            "transfer.resume": lambda p, c: {"transfer": self.transfers.resume(p["id"])},
            "transfer.cancel": lambda p, c: {"transfer": self.transfers.cancel(p["id"])},
            "task.submit": lambda p, c: self._backend(p).submit(p.get("spec"), p["idempotency_key"],
                                                                p.get("template"), p.get("workspace_id")),
            "task.list": lambda p, c: self._backend(p).tasks(p.get("workspace_id")),
            "task.get": lambda p, c: self._backend(p).task(p["task_id"]),
            "task.cancel": lambda p, c: self._backend(p).cancel(p["task_id"], p.get("idempotency_key")),
            "task.artifacts": lambda p, c: self._backend(p).artifacts(p["task_id"]),
            "watch": lambda p, c: self._subscribe("watch", p, c),
            "logs.subscribe": lambda p, c: self._subscribe("logs", p, c),
            "events.subscribe": lambda p, c: self._subscribe("events", p, c),
            "unsubscribe": self.unsubscribe,
            "graph.catalog": lambda p, c: self.graphs.catalog(),
            "graph.presets": lambda p, c: self.graphs.presets(),
            "graph.validate": lambda p, c: self.graphs.validate(p["graph"], p.get("parameters")),
            "graph.evaluate": lambda p, c: self.graphs.evaluate(p),
            "graph.cancel": lambda p, c: self.graphs.cancel(p["eval_id"]),
            "blob.ensure": lambda p, c: self.graphs.ensure(p["sha256"], p.get("connection")),
            "probe": lambda p, c: self.graphs.probe(p),
            "colormaps.list": lambda p, c: self.graphs.colormaps(),
        }
        missing = set(self.methods) ^ set(bridge_schema.method_names())
        if missing:
            raise RuntimeError(f"Bridge methods and schema disagree: {sorted(missing)}")

    # -- output -------------------------------------------------------------------------------

    def send(self, message, method=None):
        if self.strict:
            issues = bridge_schema.validate_outgoing(message, method)
            if issues:
                print(f"stk-desktop-bridge: schema violation in {method or message.get('event')}: {issues[:3]}",
                      file=sys.stderr)
                if "event" in message:
                    return
                message = {"id": message.get("id"), "error": error_object(
                    "internal_error", f"The bridge produced a result that violates the protocol schema: "
                    f"{issues[0][0]} {issues[0][1]}")}
        try:
            line = encode_message(message)
        except (TypeError, ValueError) as exc:
            if "event" in message:
                return
            line = encode_message({"id": message.get("id"), "error": error_object(
                "internal_error", f"The result is not JSON: {exc}")})
        if len(line) > self.max_line + 1:
            if "event" in message:
                print("stk-desktop-bridge: dropped an oversized event", file=sys.stderr)
                return
            line = encode_message({"id": message.get("id"), "error": error_object(
                "result_too_large", f"The result exceeds {self.max_line} bytes; request less data")})
        with self.write_lock:
            try:
                self.writer.write(line)
                self.writer.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass  # the app is gone; jobs and transfers keep their durable state

    def emit(self, event, data):
        self.send({"event": event, "data": data})

    def respond_error(self, identity, error, method=None):
        self.send({"id": identity, "error": error.to_json()}, method)

    # -- input --------------------------------------------------------------------------------

    def handle_line(self, raw):
        if not raw.strip():
            return  # blank lines are ignored
        try:
            message = decode_line(raw)
        except BridgeError as exc:
            self.respond_error(None, exc)
            return
        try:
            identity, method, params = check_envelope(message)
        except BridgeError as exc:
            self.respond_error(getattr(exc, "request_id", None), exc)
            return
        if method not in self.methods:
            self.respond_error(identity, BridgeError("unknown_method", f"Unknown method {method!r}",
                                                     data={"methods": sorted(self.methods)}))
            return
        if self.closing.is_set():
            self.respond_error(identity, BridgeError("shutting_down", "The bridge is shutting down"))
            return
        issues = bridge_schema.validate_params(method, params)
        if issues:
            self.respond_error(identity, BridgeError(
                "invalid_params", f"{issues[0][0] or '/'}: {issues[0][1]}",
                data={"errors": [{"path": path, "message": text} for path, text in issues[:20]]}), method)
            return
        with self.inflight_lock:
            if len(self.inflight) >= MAX_INFLIGHT:
                busy = True
            else:
                busy = False
                thread = threading.Thread(target=self._run, args=(identity, method, params), daemon=True,
                                          name=f"stk-bridge-{method}")
                self.inflight[thread] = method
        if busy:
            self.respond_error(identity, BridgeError("busy", f"More than {MAX_INFLIGHT} requests are in flight"))
            return
        thread.start()

    def _run(self, identity, method, params):
        context = _Context()
        try:
            try:
                result = self.methods[method](params, context)
            except BridgeError as exc:
                self.respond_error(identity, exc, method)
                return
            except Exception as exc:
                import traceback
                traceback.print_exc(file=sys.stderr)
                self.respond_error(identity, BridgeError("internal_error", f"{type(exc).__name__}: {exc}"), method)
                return
            self.send({"id": identity, "result": result}, method)
            for callback in context.callbacks:
                callback()
        finally:
            with self.inflight_lock:
                self.inflight.pop(threading.current_thread(), None)

    def serve(self, stream):
        """Read requests until EOF (or ``shutdown``), then shut down gracefully."""
        reader = LineReader(stream, self.max_line)
        while not self.closing.is_set():
            try:
                line, error = reader.next()
            except (OSError, ValueError):
                break
            if error is not None:
                self.respond_error(None, error)
                continue
            if line is None:
                break
            self.handle_line(line)
        self.shutdown()

    def shutdown(self, grace=SHUTDOWN_GRACE):
        """Stop subscriptions and evaluations, pause transfers (journals stay resumable), finish requests.

        Runtime tasks and hub actions are never cancelled: closing the app keeps jobs running.
        """
        if self.closed.is_set():
            return
        self.closing.set()
        self.subscriptions.stop_all()
        self.graphs.cancel_all()
        self.transfers.stop(timeout=grace)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            with self.inflight_lock:
                others = [t for t in self.inflight if t is not threading.current_thread()]
            if not others:
                break
            time.sleep(0.02)
        self.closed.set()

    # -- helpers ------------------------------------------------------------------------------

    def _backend(self, params):
        return self.connections.backend(params["connection"], params.get("node"))

    def _hub(self, params):
        connection = params["connection"]
        if not connection.startswith("hub:"):
            raise BridgeError("invalid_params", "This method needs a hub connection")
        return HubBackend(connection, self.connections.hub_client(connection), params.get("node") or "")

    def _subscribe(self, kind, params, context):
        subscription = self.subscriptions.start(kind, params)
        context.after(subscription.ready.set)
        return {"sub": subscription.id}

    # -- methods ------------------------------------------------------------------------------

    def hello(self, params, context):
        if params["protocol"] != PROTOCOL_VERSION:
            raise BridgeError("unsupported", f"This bridge speaks protocol {PROTOCOL_VERSION}",
                              data={"supported": [PROTOCOL_VERSION]})
        resumed = self.transfers.resume_interrupted() if params.get("resume_transfers", True) else []
        return {
            "protocol": PROTOCOL_VERSION,
            "server": {"name": "stk-desktop-bridge", "version": VERSION, "python": platform.python_version(),
                       "platform": sys.platform, "pid": os.getpid()},
            "methods": sorted(self.methods),
            "events": list(bridge_schema.event_names()),
            "limits": {"max_line_bytes": self.max_line, "max_inflight": MAX_INFLIGHT, "watch_interval_s": 2.0,
                       "log_chunk_bytes": 256 * 1024, "transfer_chunk_bytes": 1024 * 1024},
            "paths": {"state_dir": str(self.state_dir), "cache_dir": str(self.cache_dir),
                      "blob_dir": str(self.graphs.blobs.root), "download_dir": str(self.download_dir)},
            "resumed_transfers": resumed,
        }

    def shutdown_method(self, params, context):
        def stop():
            threading.Thread(target=self._shutdown_and_exit, daemon=True, name="stk-bridge-shutdown").start()
        context.after(stop)
        return {"ok": True}

    def _shutdown_and_exit(self):
        self.shutdown()
        if self.on_exit is not None:
            self.on_exit()

    def add_runtime(self, params, context):
        token = params.get("token")
        if params.get("token_file"):
            try:
                token = Path(params["token_file"]).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise BridgeError("not_found", f"The token file cannot be read ({exc.strerror})") from None
        if not token:
            raise BridgeError("invalid_params", "Give 'token' or 'token_file'")
        return {"connection": self.connections.add_runtime(params["name"], params["url"], token,
                                                           params.get("check", True))}

    def remove_connection(self, params, context):
        self.connections.remove(params["id"])
        return {"removed": params["id"]}

    def check_connection(self, params, context):
        connection = params["id"]
        self.connections.describe(connection)
        try:
            if connection.startswith("hub:"):
                hub = self._hub({"connection": connection})
                health = hub.call(hub.hub.health)
                devices = hub.call(hub.hub.devices)
                return {"id": connection, "ok": True, "health": health,
                        "nodes": sum(1 for d in devices if d.get("role") == "node" and not d.get("revoked"))}
            return {"id": connection, "ok": True, "health": self._backend({"connection": connection}).health()}
        except BridgeError as exc:
            if exc.code in ("unavailable", "unauthorized", "remote_error", "timeout"):
                return {"id": connection, "ok": False, "error": exc.to_json()}
            raise

    def pair_hub(self, params, context):
        return {"connection": self.connections.pair_hub(params["name"], params["url"], params["code"],
                                                        params.get("device_name") or "STK Desktop")}

    def hub_devices(self, params, context):
        hub = self._hub(params)
        devices = [d for d in hub.call(hub.hub.devices) if not d.get("revoked")]
        return {"devices": devices}

    def hub_templates(self, params, context):
        hub = self._hub(params)
        return {"templates": hub.call(hub.hub.templates)}

    def hub_actions(self, params, context):
        hub = self._hub(params)
        return {"actions": hub.call(hub.hub.actions)}

    def hub_action(self, params, context):
        hub = self._hub(params)
        record = hub.call(hub.hub.action, params["action_id"])
        self.inspected[(params["connection"], record["id"])] = record["request"]
        return {"action": record}

    def hub_review(self, params, context):
        hub = self._hub(params)
        key = (params["connection"], params["action_id"])
        if params["approved"]:
            if key not in self.inspected:
                raise BridgeError("review_not_inspected", "Read the full request (hub.action) before approving it",
                                  data={"action_id": params["action_id"]})
            current = hub.call(hub.hub.action, params["action_id"])
            if current["request"] != self.inspected[key]:
                raise BridgeError("conflict", "The action changed since it was inspected; inspect it again")
        record = hub.call(hub.hub.review, params["action_id"], params["approved"])
        self.inspected.pop(key, None)
        return {"action": record}

    def upload_start(self, params, context):
        transfer = self.transfers.start_upload(params["connection"], params["workspace_id"], params["source"],
                                               params.get("remote"), params.get("node"))
        return {"transfer": transfer}

    def download_start(self, params, context):
        if ("task_id" in params) == ("workspace_id" in params):
            raise BridgeError("invalid_params", "Give exactly one of 'task_id' or 'workspace_id'")
        owner = "task" if "task_id" in params else "workspace"
        owner_id = params.get("task_id") or params.get("workspace_id")
        dest = params.get("dest")
        if dest is None:
            backend = self._backend(params)
            root = self.download_dir / backend.server_key / owner_id
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                dest = str(inside(root, params["path"]))
            except ValueError as exc:
                raise BridgeError("invalid_params", str(exc)) from None
        transfer = self.transfers.start_download(params["connection"], owner, owner_id, params["path"], dest,
                                                 params.get("node"))
        return {"transfer": transfer}

    def unsubscribe(self, params, context):
        self.subscriptions.cancel(params["sub"])
        return {"ok": True}
