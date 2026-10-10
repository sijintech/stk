"""The bridge process: request dispatch, responses, events, lifecycle (spec §2-§5).

Requests are handled concurrently (one thread each, at most :data:`MAX_INFLIGHT`), so responses
can arrive in any order; the app matches them by ``id``. Every write to the protocol stream is one
complete line under a lock. Params are validated against ``desktop-bridge-1.schema.json`` before a
handler runs; with ``strict`` the bridge also validates every message it sends (tests, CI).

One bridge owns a state directory at a time: :class:`StateDirLock` takes an exclusive,
non-blocking OS lock on ``<state_dir>/bridge.lock`` (``fcntl.flock`` on POSIX, ``msvcrt.locking``
on Windows; the OS drops it when the process dies). A second bridge raises ``busy``; run as a
process it answers every request with that error (:func:`refuse`) and exits with status 3.
"""
import math
import os
from pathlib import Path
import platform
import sys
import threading
import time

from suan.runtime.common import inside

from . import schema as bridge_schema
from .backends import HubBackend
from .hub import HubResponseError, hub_error
from .connections import ConnectionStore
from .graphs import GraphService
from .projects import ProjectSessions
from .analysis_runs import AnalysisRunExecutor
from .workflow_runs import WorkflowRunExecutor
from .project_runs import ProjectRuns
from .scripts import ScriptSessions
from .ui_requests import UIRequests, UI_OPERATIONS
from .protocol import (MAX_LINE_BYTES, PROTOCOL_VERSION, BridgeError, LineReader, check_envelope, decode_line,
                       encode_message, error_object, leading_id)
from .subscriptions import SubscriptionManager
from .transfers import TransferManager

__all__ = ["Bridge", "StateDirLock", "default_state_dir", "refuse"]

VERSION = "1.0.0"
MAX_INFLIGHT = 64
SHUTDOWN_GRACE = 5.0
LOCK_NAME = "bridge.lock"


def with_kind(record):
    """A hub action record with a top-level ``kind`` (the hub keeps it in ``request.kind`` only)."""
    if isinstance(record, dict) and "kind" not in record and isinstance(record.get("request"), dict):
        return {**record, "kind": record["request"].get("kind")}
    return record


def default_state_dir():
    return Path(os.environ.get("STK_DESKTOP_BRIDGE_DIR", str(Path.home() / ".stk" / "desktop-bridge")))


def _absolute(path):
    """A dataset folder given as an absolute path (the service has no notion of the caller's working directory)."""
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise BridgeError("invalid_params", "directory is an absolute path")
    return Path(path)


class StateDirLock:
    """An exclusive lock on ``<state_dir>/bridge.lock`` held for the bridge's lifetime (``busy`` otherwise)."""

    def __init__(self, state_dir):
        self.path = Path(state_dir) / LOCK_NAME
        self.stream = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0, os.SEEK_END)
                if self.stream.tell() == 0:  # lock a byte that exists (as suan.runtime.common.instance_lock)
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            # Not retryable (unlike the in-flight limit's busy): repeating the request cannot help
            # while the other bridge runs; data.state_dir tells the two apart.
            raise BridgeError("busy", f"Another STK desktop bridge is using the state directory {state_dir}; "
                              "close it first or start this one with another --state-dir",
                              data={"state_dir": str(state_dir)}, retryable=False) from None

    def release(self):
        if self.stream.closed:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            self.stream.close()  # closing also drops a POSIX flock


def refuse(stream, writer, error, max_line=MAX_LINE_BYTES):
    """Answer every request on ``stream`` with ``error`` until EOF (a bridge that could not start)."""
    reader = LineReader(stream, max_line)
    while True:
        try:
            line, problem = reader.next()
        except (OSError, ValueError):
            return
        if line is None and problem is None:
            return
        identity = getattr(problem, "request_id", None)
        if line is not None:
            if not line.strip():
                continue
            try:
                identity = check_envelope(decode_line(line))[0]
            except BridgeError as exc:
                identity = getattr(exc, "request_id", None)
                if identity is None:
                    identity = leading_id(line)
        try:
            writer.write(encode_message({"id": identity, "error": error.to_json()}))
            writer.flush()
        except (OSError, ValueError):
            return


class _Context:
    def __init__(self):
        self.callbacks = []

    def after(self, callback):
        """Run ``callback`` once the response has been written (subscriptions start then)."""
        self.callbacks.append(callback)


def _poll_seconds():
    """How often workflow runs read their Runtime tasks: 15 s, or STK_WORKFLOW_POLL_SECONDS (0.02-3600)."""
    try:
        value = float(os.environ.get("STK_WORKFLOW_POLL_SECONDS", "15"))
    except ValueError:
        return 15.0
    return min(max(value, 0.02), 3600.0) if math.isfinite(value) else 15.0


class Bridge:
    def __init__(self, state_dir=None, cache_dir=None, *, writer, strict=False, max_line=MAX_LINE_BYTES,
                 on_exit=None):
        self.state_dir = Path(state_dir) if state_dir else default_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_lock = StateDirLock(self.state_dir)  # before anything reads or rewrites journals
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
        self.analysis_executor = AnalysisRunExecutor(self.graphs.worker, self.graphs.blobs.root)
        # Workflow runs register outputs as ordinary edits in the background; open handles hear about them.
        self.workflow_executor = WorkflowRunExecutor(self.analysis_executor, changed=self._announce,
                                                     scripting=self._workflow_scripting, poll_seconds=_poll_seconds())
        self.projects = ProjectSessions(self.state_dir, analysis_executor=self.analysis_executor,
                                        workflow_executor=self.workflow_executor)
        self.projects.local.emit = self.emit
        self._local_started = False
        self.project_runs = ProjectRuns(self.projects, self.connections.backend)
        self.ui = UIRequests(self.emit)
        self.scripts = ScriptSessions(self.emit, self.script_call)
        self.transfers = TransferManager(self.state_dir, self.emit, self.connections.backend)
        # Materials prediction models (S3): datasets, training on this computer, a registry and prediction.
        from suan.materials.service import MaterialsService
        self.materials = MaterialsService(self.state_dir / "materials")
        # Optional software modules (engines and modeling tools): detected, or installed from conda-forge (E0b).
        from suan.modules import Modules
        self.modules = Modules(policy=self.projects.models.policy, emit=self.emit)
        self.subscriptions = SubscriptionManager(self.emit, self.connections.backend, self.connections.hub_client)
        self.methods = {
            "hello": self.hello,
            "shutdown": self.shutdown_method,
            "connections.list": lambda p, c: {"connections": self.connections.list()},
            "connections.add_runtime": self.add_runtime,
            "connections.remove": self.remove_connection,
            "connections.ssh": self.ssh_connection,
            "connections.check": self.check_connection,
            "connections.pair_hub": self.pair_hub,
            "connections.local": lambda p, c: self.connections.local_status(),
            "connections.local_start": lambda p, c: self.connections.local_start(bool(p.get("initialize"))),
            "hub.devices": self.hub_devices,
            "hub.templates": self.hub_templates,
            "hub.actions": self.hub_actions,
            "hub.action": self.hub_action,
            "hub.review": self.hub_review,
            "hub.policy": self.hub_policy,
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
            "task.logs": self.task_logs,
            "watch": lambda p, c: self._subscribe("watch", p, c),
            "logs.subscribe": lambda p, c: self._subscribe("logs", p, c),
            "events.subscribe": lambda p, c: self._subscribe("events", p, c),
            "unsubscribe": self.unsubscribe,
            "graph.catalog": lambda p, c: self.graphs.catalog(),
            "graph.presets": lambda p, c: self.graphs.presets(),
            "graph.validate": lambda p, c: self.graphs.validate(p["graph"], p.get("parameters")),
            "graph.evaluate": lambda p, c: self.graphs.evaluate(p),
            "graph.cancel": lambda p, c: self.graphs.cancel(p["eval_id"], p.get("connection"), p.get("node")),
            "blob.ensure": lambda p, c: self.graphs.ensure(p["sha256"], p.get("connection")),
            "probe": lambda p, c: self.graphs.probe(p),
            "colormaps.list": lambda p, c: self.graphs.colormaps(),
            "skills.list": lambda p, c: self.skills_list(p),
            "skills.get": lambda p, c: self.skills_get(p),
            "project.create": lambda p, c: self.projects.create(p),
            "project.open": lambda p, c: self.projects.open(p),
            "project.list": lambda p, c: self.projects.list(p),
            "project.recent": lambda p, c: self.projects.recent(p),
            "project.forget": lambda p, c: self.projects.forget(p),
            "project.close": self.close_project,
            "project.snapshot": lambda p, c: self.projects.snapshot(p),
            "project.apply": self.apply_project,
            "project.preview": lambda p, c: self.projects.preview(p),
            "project.sweep.plan": lambda p, c: self.projects.sweep_plan(p),
            "demo.create": lambda p, c: self.demo_create(p),
            "project.drafts.save": lambda p, c: self.projects.drafts("save", p),
            "project.drafts.get": lambda p, c: self.projects.drafts("get", p),
            "project.drafts.list": lambda p, c: self.projects.drafts("list", p),
            "project.drafts.apply": self.apply_project_draft,
            "project.drafts.discard": lambda p, c: self.projects.drafts("discard", p),
            "project.contexts.capture": lambda p, c: self.projects.contexts("capture", p),
            "project.contexts.get": lambda p, c: self.projects.contexts("get", p),
            "project.contexts.list": lambda p, c: self.projects.contexts("list", p),
            "project.discussion.add": lambda p, c: self.projects.discussion("add", p),
            "project.discussion.get": lambda p, c: self.projects.discussion("get", p),
            "project.discussion.list": lambda p, c: self.projects.discussion("list", p),
            "project.discussion.link_draft": lambda p, c: self.projects.discussion("link_draft", p),
            "project.discussion.proposals": lambda p, c: self.projects.discussion("proposals", p),
            "project.requests.create": lambda p, c: self.projects.requests("create", p),
            "project.requests.get": lambda p, c: self.projects.requests("get", p),
            "project.requests.progress": lambda p, c: self.projects.requests("progress", p),
            "project.requests.propose_edits": lambda p, c: self.projects.requests("propose_edits", p),
            "project.requests.edit_proposal": lambda p, c: self.projects.requests("edit_proposal", p),
            "project.requests.list": lambda p, c: self.projects.requests("list", p),
            "project.requests.usage": lambda p, c: self.projects.requests("usage", p),
            "project.requests.cancel": lambda p, c: self.projects.requests("cancel", p),
            "project.requests.provider": lambda p, c: self.projects.requests("provider", p),
            "ai.credentials.set": lambda p, c: self.projects.credentials("set", p),
            "ai.credentials.clear": lambda p, c: self.projects.credentials("clear", p),
            "project.requests.start": lambda p, c: self.projects.requests("start", p),
            "project.requests.recover": lambda p, c: self.projects.requests("recover", p),
            "project.history": lambda p, c: self.projects.history(p),
            "project.backup": lambda p, c: self.projects.backup(p),
            "project.upgrade": self.upgrade_project,
            "project.undo": lambda p, c: self.restore_project(p, c, redo=False),
            "project.redo": lambda p, c: self.restore_project(p, c, redo=True),
            "project.csv.import": lambda p, c: self.csv_project("import", p, c),
            "project.csv.export": lambda p, c: self.csv_project("export", p, c),
            "project.files.list": lambda p, c: self.projects.files("list", p),
            "project.files.index": lambda p, c: self.edit_project_files("index", p, c),
            "project.files.refresh": lambda p, c: self.edit_project_files("refresh", p, c),
            "project.files.resolve": lambda p, c: self.projects.files("resolve", p),
            "project.analyses.create": lambda p, c: self.edit_project_analyses("create", p, c),
            "project.analyses.update": lambda p, c: self.edit_project_analyses("update", p, c),
            "project.analyses.get": lambda p, c: self.projects.analyses("get", p),
            "project.analyses.list": lambda p, c: self.projects.analyses("list", p),
            "project.workflows.create": lambda p, c: self.edit_project_workflows("create", p, c),
            "project.workflows.update": lambda p, c: self.edit_project_workflows("update", p, c),
            "project.workflows.get": lambda p, c: self.projects.workflows("get", p),
            "project.workflows.list": lambda p, c: self.projects.workflows("list", p),
            "project.workflows.validate": lambda p, c: self.projects.workflows("validate", p),
            "project.workflows.choices": lambda p, c: self.projects.workflows("choices", p),
            "project.workflow_runs.prepare": lambda p, c: self.projects.workflow_runs("prepare", self._simulation_identity(p)),
            "project.workflow_runs.get": lambda p, c: self.projects.workflow_runs("get", p),
            "project.workflow_runs.list": lambda p, c: self.projects.workflow_runs("list", p),
            "project.workflow_runs.start": lambda p, c: self.projects.workflow_runs("start", p),
            "project.workflow_runs.cancel": lambda p, c: self.projects.workflow_runs("cancel", p),
            "project.workflow_runs.recover": lambda p, c: self.projects.workflow_runs("recover", p),
            "project.workflow_runs.stale": lambda p, c: self.projects.workflow_runs("stale", p),
            "project.attention.list": lambda p, c: self.projects.attention("list", p),
            "project.search": lambda p, c: self.projects.search(p),
            "project.archive.set": self.archive_set,
            "project.archive.list": lambda p, c: self.projects.archive("list", p),
            "project.labels.set": self.labels_set,
            "models.list": lambda p, c: self.projects.model_settings("list", p),
            "models.local.list": lambda p, c: self.projects.local_models("list", p),
            "modules.list": lambda p, c: self.modules_call("list", p),
            "modules.detect": lambda p, c: self.modules_call("detect", p),
            "modules.install": lambda p, c: self.modules_call("install", p),
            "modules.cancel": lambda p, c: self.modules_call("cancel", p),
            "modules.remove": lambda p, c: self.modules_call("remove", p),
            "materials.datasets.synthetic": lambda p, c: self.materials_call("synthetic", p),
            "materials.datasets.validate": lambda p, c: self.materials_call("validate", p),
            "materials.train": lambda p, c: self.materials_call("train", p),
            "materials.jobs.get": lambda p, c: self.materials_call("job", p),
            "materials.jobs.cancel": lambda p, c: self.materials_call("cancel", p),
            "materials.models.list": lambda p, c: self.materials_call("models", p),
            "materials.models.activate": lambda p, c: self.materials_call("activate", p),
            "materials.predict": lambda p, c: self.materials_call("predict", p),
            "models.route": lambda p, c: self.projects.model_route(p),
            "project.agent.tools": lambda p, c: self.projects.agent("tools", p),
            "project.agent.route": lambda p, c: self.projects.agent("route", p),
            "project.agent.create": lambda p, c: self.projects.agent("create", p),
            "project.agent.say": lambda p, c: self.projects.agent("say", p),
            "project.agent.start": lambda p, c: self.projects.agent("start", p),
            "project.agent.cancel": lambda p, c: self.projects.agent("cancel", p),
            "project.agent.recover": lambda p, c: self.projects.agent("recover", p),
            "project.agent.get": lambda p, c: self.projects.agent("get", p),
            "project.agent.list": lambda p, c: self.projects.agent("list", p),
            "project.agent.objects": lambda p, c: self.projects.agent("objects", p),
            "project.agent.verify": lambda p, c: self.projects.agent("verify", p),
            "project.agent.export": lambda p, c: self.projects.agent("export", p),
            "project.agent.decide": self.decide_agent_item,
            "models.local.recommendations": lambda p, c: self.projects.local_models("recommendations", p),
            "models.local.install": lambda p, c: self.projects.local_models("install", p),
            "models.local.import": lambda p, c: self.projects.local_models("import", p),
            "models.local.cancel": lambda p, c: self.projects.local_models("cancel", p),
            "models.local.start": lambda p, c: self.projects.local_models("start", p),
            "models.local.stop": lambda p, c: self.projects.local_models("stop", p),
            "models.local.remove": lambda p, c: self.projects.local_models("remove", p),
            "models.endpoints.add": lambda p, c: self.model_settings("add", p, c),
            "models.endpoints.remove": lambda p, c: self.model_settings("remove", p, c),
            "models.keys.set": lambda p, c: self.model_settings("key.set", p, c),
            "models.keys.clear": lambda p, c: self.model_settings("key.clear", p, c),
            "models.policy.set": lambda p, c: self.model_settings("policy", p, c),
            "project.labels.list": lambda p, c: self.projects.labels("list", p),
            "project.attention.viewed": lambda p, c: self.projects.attention("viewed", p),
            "project.analysis_runs.prepare": lambda p, c: self.projects.analysis_runs("prepare", p),
            "project.analysis_runs.get": lambda p, c: self.projects.analysis_runs("get", p),
            "project.analysis_runs.list": lambda p, c: self.projects.analysis_runs("list", p),
            "project.analysis_runs.start": lambda p, c: self.projects.analysis_runs("start", p),
            "project.analysis_runs.cancel": lambda p, c: self.projects.analysis_runs("cancel", p),
            "project.analysis_runs.recover": lambda p, c: self.projects.analysis_runs("recover", p),
            "project.analysis_runs.result": lambda p, c: self.projects.analysis_runs("result", p),
            "project.snapshots.list": lambda p, c: self.projects.snapshots("list", p),
            "project.snapshots.capture": self.capture_project_files,
            "project.snapshots.get": lambda p, c: self.projects.snapshots("get", p),
            "project.snapshots.verify": lambda p, c: self.projects.snapshots("verify", p),
            "project.snapshots.resolve": lambda p, c: self.projects.snapshots("resolve", p),
            "project.runs.prepare": lambda p, c: self.run_project("prepare", p, c),
            "project.runs.list": lambda p, c: self.run_project("list", p, c),
            "project.runs.get": lambda p, c: self.run_project("get", p, c),
            "project.runs.submit": lambda p, c: self.run_project("submit", p, c),
            "project.runs.refresh": lambda p, c: self.run_project("refresh", p, c),
            "project.runs.cancel": lambda p, c: self.run_project("cancel", p, c),
            "script.open": lambda p, c: self.scripts.open(p),
            "script.status": lambda p, c: self.scripts.status(p),
            "script.execute": self.scripts.execute,
            "script.read": lambda p, c: self.scripts.read(p),
            "script.interrupt": lambda p, c: self.scripts.interrupt(p),
            "script.close": lambda p, c: self.scripts.close(p),
            "script.catalog": lambda p, c: self.script_catalog(),
            "ui.attach": lambda p, c: self.ui.attach(p),
            "ui.detach": lambda p, c: self.ui.detach(p),
            "ui.reply": lambda p, c: self.ui.reply(p),
        }
        missing = set(self.methods) ^ set(bridge_schema.method_names())
        if missing:
            self.state_lock.release()
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

    def _simulation_identity(self, params):
        """A workflow run's simulation settings with the Runtime endpoint fingerprint frozen beside the profile."""
        if "simulation" not in params:
            return params
        simulation = params["simulation"]
        backend = self.connections.backend(simulation["connection"], None)
        return {**params, "simulation": {"connection": simulation["connection"], "connection_identity": backend.server_key,
                                         "options": simulation.get("options", {})}}

    def _workflow_scripting(self, store, cancelled):
        """The console's stk API on an open handle of ``store`` (remote workflow steps, W5)."""
        from suan.scripting import API
        handles = self.projects.handles_of(store)
        if not handles:
            raise BridgeError("not_found", "The project is no longer open")
        api = API(lambda operation, values: self.script_call(operation, values, cancelled))
        api._project_handle = sorted(handles)[0]
        return api

    def _announce(self, store):
        """A background edit (a workflow run registering outputs) as project.changed for each open handle."""
        try:
            revision = store.info()["revision"]
        except Exception:  # noqa: BLE001 - a closed or replaced project needs no announcement
            return
        for handle in self.projects.handles_of(store):
            self.emit("project.changed", {"handle": handle, "revision": revision})

    def respond_error(self, identity, error, method=None):
        self.send({"id": identity, "error": error.to_json()}, method)

    # -- input --------------------------------------------------------------------------------

    def handle_line(self, raw):
        if not raw.strip():
            return  # blank lines are ignored
        try:
            message = decode_line(raw)
        except BridgeError as exc:
            self.respond_error(leading_id(raw), exc)  # the id when the line starts with it (spec §3)
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
                self.respond_error(getattr(error, "request_id", None), error)
                continue
            if line is None:
                break
            self.handle_line(line)
        self.shutdown()

    def modules_call(self, action, params):
        """Optional software modules (docs/design/multiscale-engines.md, E0b). Installing and removing change this
        computer and use the network: desktop only (not in the script catalog); listing and detecting are not."""
        from suan.project.store import ProjectError
        if self.closing.is_set():
            raise BridgeError("shutting_down", "The bridge is shutting down")
        try:
            if action == "list":
                return self.modules.list()
            if action == "detect":
                return self.modules.detect(params.get("id"))
            if action == "install":
                return {"job": self.modules.install(params["id"])}
            if action == "cancel":
                return {"job": self.modules.cancel(params["id"])}
            return self.modules.remove(params["id"])
        except ProjectError as exc:
            raise BridgeError("invalid_params", str(exc)) from None
        except OSError as exc:
            raise BridgeError("unavailable", f"The modules folder cannot be used: {exc.strerror or type(exc).__name__}",
                              retryable=False) from None

    def materials_call(self, action, params):
        """Materials models (S3, docs/design/materials-models-s3.md); everything runs on this computer."""
        from suan.materials import datasets, service, training
        if self.closing.is_set():
            raise BridgeError("shutting_down", "The bridge is shutting down")
        materials = self.materials
        try:
            if action == "synthetic":
                return {"card": datasets.write_synthetic(_absolute(params["directory"]), params["kind"], params["samples"],
                                                         seed=params.get("seed", 0), name=params.get("name"))}
            if action == "validate":
                return {"card": datasets.validate(_absolute(params["directory"]))}
            if action == "train":
                return {"job": materials.train(_absolute(params["directory"]), params["job_id"], options=params.get("options"))}
            if action == "job":
                return {"job": materials.job(params["job_id"])}
            if action == "cancel":
                return {"job": materials.cancel(params["job_id"])}
            if action == "models":
                return materials.models(params.get("kind"))
            if action == "activate":
                return {"entry": materials.activate(params["kind"], params["version"])}
            return materials.predict(params["kind"], params["inputs"], version=params.get("version"))
        except training.TrainingUnavailable as exc:
            raise BridgeError("unsupported", str(exc)) from None
        except service.MaterialsNotFound as exc:
            raise BridgeError("not_found", str(exc)) from None
        except service.MaterialsBusy as exc:
            raise BridgeError("busy", str(exc), retryable=False) from None
        except service.MaterialsUnavailable as exc:
            raise BridgeError("unavailable", str(exc), retryable=False) from None
        except (service.MaterialsError, datasets.DatasetError, ValueError) as exc:
            raise BridgeError("invalid_params", str(exc)) from None
        except OSError as exc:
            raise BridgeError("unavailable", f"A materials file or folder cannot be used: {exc.strerror or type(exc).__name__}",
                              retryable=False) from None

    def shutdown(self, grace=SHUTDOWN_GRACE):
        """Stop subscriptions and evaluations, pause transfers (journals stay resumable), finish requests.

        Runtime tasks and hub actions are never cancelled: closing the app keeps jobs running.
        """
        if self.closed.is_set():
            return
        self.closing.set()
        self.materials.shutdown()
        self.modules.shutdown()
        self.workflow_executor.shutdown(wait=False)
        self.analysis_executor.shutdown(wait=False)
        self.ui.close()
        self.scripts.shutdown()
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
        self.projects.shutdown()
        self.connections.close()
        self.state_lock.release()

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

    def script_catalog(self):
        # Deliberate initial coverage. In particular, scripts cannot recursively dispatch their
        # own lifecycle, attach arbitrary executors, or subscribe without owning a subscription.
        names = ("project.create", "project.open", "project.list", "project.recent", "project.forget", "project.close", "project.snapshot",
                 "project.apply", "project.preview", "project.sweep.plan", "project.history", "project.backup", "project.upgrade", "project.undo", "project.redo",
                 "project.drafts.save", "project.drafts.get", "project.drafts.list", "project.drafts.apply", "project.drafts.discard",
                 "project.contexts.capture", "project.contexts.get", "project.contexts.list",
                 "project.discussion.add", "project.discussion.get", "project.discussion.list",
                 "project.discussion.link_draft", "project.discussion.proposals",
                 "project.requests.create", "project.requests.get", "project.requests.list", "project.requests.cancel",
                 "project.requests.provider", "project.requests.start", "project.requests.recover", "project.requests.progress",
                 "project.requests.propose_edits", "project.requests.edit_proposal", "project.requests.usage",
                 "project.csv.import", "project.csv.export",
                 "project.files.list", "project.files.index", "project.files.refresh", "project.files.resolve",
                 "project.analyses.create", "project.analyses.update", "project.analyses.get", "project.analyses.list",
                 "project.workflows.create", "project.workflows.update", "project.workflows.get",
                 "project.workflows.list", "project.workflows.validate", "project.workflows.choices",
                 "project.workflow_runs.prepare", "project.workflow_runs.get", "project.workflow_runs.list",
                 "project.workflow_runs.start", "project.workflow_runs.cancel", "project.workflow_runs.recover",
                 "project.workflow_runs.stale", "project.attention.list", "project.attention.viewed", "project.search",
                 "project.archive.set", "project.archive.list", "project.labels.set", "project.labels.list",
                 "project.analysis_runs.prepare", "project.analysis_runs.get", "project.analysis_runs.list",
                 "project.analysis_runs.start", "project.analysis_runs.cancel", "project.analysis_runs.recover", "project.analysis_runs.result",
                 "project.snapshots.list", "project.snapshots.capture", "project.snapshots.get",
                 "project.snapshots.verify", "project.snapshots.resolve",
                 "project.runs.prepare", "project.runs.list", "project.runs.get",
                 "project.runs.submit", "project.runs.refresh", "project.runs.cancel",
                 "graph.catalog", "graph.presets", "graph.validate", "graph.evaluate", "graph.cancel",
                 "blob.ensure", "probe", "colormaps.list", "skills.list", "skills.get", "models.list", "models.local.list", "models.route",
                 "project.agent.tools", "project.agent.route", "project.agent.create", "project.agent.say",
                 "project.agent.start", "project.agent.cancel", "project.agent.recover", "project.agent.get",
                 "project.agent.list", "project.agent.objects", "project.agent.verify", "project.agent.export",
                 "modules.list", "modules.detect",
                 "materials.datasets.synthetic", "materials.datasets.validate", "materials.train", "materials.jobs.get",
                 "materials.jobs.cancel", "materials.models.list", "materials.models.activate", "materials.predict",
                 "connections.list", "connections.check", "connections.ssh",
                 "hub.devices", "hub.templates", "hub.actions", "hub.action",
                 "workspace.list", "workspace.create", "workspace.files", "upload.start", "download.start",
                 "transfer.list", "transfer.get", "transfer.resume", "transfer.cancel",
                 "task.submit", "task.list", "task.get", "task.cancel", "task.artifacts", "task.logs")
        return {"operations": {name: bridge_schema.method_contract(name) for name in names},
                "ui_operations": list(UI_OPERATIONS)}

    def demo_create(self, params):
        """Build the offline example project through the console's own operations (suan.workflows.demo)."""
        from suan.scripting import API
        from suan.workflows.demo import create_demo
        cancelled = threading.Event()
        directory = params.get("directory")
        try:
            return create_demo(API(lambda operation, values: self.script_call(operation, values, cancelled)), directory)
        except ValueError as exc:
            raise BridgeError("invalid_params", str(exc)) from None

    def script_call(self, operation, params, cancelled):
        if self.closing.is_set():
            raise BridgeError("shutting_down", "The bridge is shutting down")
        if cancelled.is_set():
            raise BridgeError("cancelled", "Script execution interrupted")
        if not isinstance(operation, str) or not isinstance(params, dict):
            raise BridgeError("invalid_params", "An operation needs a string name and object parameters")
        if operation == "operations":
            return self.script_catalog()
        if operation.startswith("ui."):
            return self.ui.call(operation[3:], params, cancelled)
        if operation not in self.script_catalog()["operations"]:
            raise BridgeError("unsupported", f"Operation {operation!r} is not exposed to Python yet")
        issues = bridge_schema.validate_params(operation, params)
        if issues:
            raise BridgeError("invalid_params", f"{issues[0][0]}: {issues[0][1]}")
        if operation == "graph.evaluate":
            # Console interruption cancels only this local evaluation; on a Hub it stops
            # waiting without issuing a graph.cancel action or cancelling simulation tasks.
            return self.graphs.evaluate(params, interrupted=cancelled)
        context = _Context()
        result = self.methods[operation](params, context)
        for callback in context.callbacks:
            callback()
        return result

    def _skill_catalog(self):
        # Reread per request: definitions are small and availability follows the environment.
        from suan.skills.catalog import load_catalog
        return load_catalog(self.graphs.registry())

    def skills_list(self, params):
        from suan.skills.catalog import DEFAULT_LIMIT, SkillCatalogError
        try:
            return self._skill_catalog().page(offset=params.get("offset", 0), limit=params.get("limit", DEFAULT_LIMIT),
                                              query=params.get("query"))
        except SkillCatalogError as exc:
            raise BridgeError(exc.code, str(exc), data=exc.data) from None

    def skills_get(self, params):
        from suan.skills.catalog import SkillCatalogError
        try:
            return {"skill": self._skill_catalog().get(params["id"], params.get("version"))}
        except SkillCatalogError as exc:
            raise BridgeError(exc.code, str(exc), data=exc.data) from None

    def task_logs(self, params, context):
        import base64
        limit = params.get("limit", 65536)
        result = self._backend(params).logs(params["task_id"], params.get("stream", "stdout"),
                                            params.get("offset", 0), limit)
        # Older Hub read endpoints may ignore the requested limit. Keep byte offsets consistent
        # with precisely the chunk returned, including when UTF-8 characters straddle chunks.
        data = result["data"][:limit]
        return {"data": base64.b64encode(data).decode("ascii"), "offset": result["offset"],
                "next_offset": result["offset"] + len(data), "terminal": result["terminal"]}

    def archive_set(self, params, context):
        result = self.projects.archive("set", params)
        if result["changed"]:
            kinds = sorted({item["kind"] for item in result["items"]})
            context.after(lambda: self.emit("project.archive.changed", {"handle": params["handle"], "kinds": kinds}))
        return result

    def model_settings(self, action, params, context):
        result = self.projects.model_settings(action, params)
        if action == "policy" and params["network"] != "internet":
            self.modules.cancel_all()  # module installations download from conda-forge too
        context.after(lambda: self.emit("models.changed", {}))
        return result

    def labels_set(self, params, context):
        result = self.projects.labels("set", params)
        if result["changed"]:
            kinds = sorted({item["kind"] for item in result["items"]})
            context.after(lambda: self.emit("project.labels.changed", {"handle": params["handle"], "kinds": kinds}))
        return result

    def run_project(self, action, params, context):
        observing = action in ("submit", "refresh", "cancel")
        before = self.project_runs.call("get", params)["run"]["observation_id"] if observing else None
        try:
            result = self.project_runs.call(action, params)
        finally:
            if observing:
                # Publish persisted failure observations too. Error responses may not run
                # context callbacks, so this independent fact is emitted immediately.
                try:
                    run = self.project_runs.call("get", params)["run"]
                    if run["observation_id"] != before:
                        self.emit("project.runs.changed", {"handle": params["handle"], "run_id": params["run_id"],
                                                           "observation_id": run["observation_id"]})
                except BridgeError:
                    pass
        if action == "prepare":
            context.after(lambda: self.emit("project.changed", {"handle": params["handle"], "revision": result["revision"]}))
        return result

    def csv_project(self, action, params, context):
        result = self.projects.csv(action, params)
        if action == "import":
            context.after(lambda: self.emit("project.changed", {"handle": params["handle"], "revision": result["revision"]}))
        return result

    def capture_project_files(self, params, context):
        result = self.projects.snapshots("capture", params)
        context.after(lambda: self.emit("project.changed", {"handle": params["handle"], "revision": result["revision"]}))
        return result

    def apply_project(self, params, context):
        result = self.projects.apply(params)
        context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                            "revision": result["revision"]}))
        return result

    def apply_project_draft(self, params, context):
        result = self.projects.drafts("apply", params)
        if not result["replayed"]:
            context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                                "revision": result["revision"]}))
        return result

    def decide_agent_item(self, params, context):
        """A person's decision on an agent session's draft (desktop only: not in the script catalog)."""
        result = self.projects.agent("decide", params)
        if result["receipt"].get("applied_revision") is not None:
            context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                                "revision": result["receipt"]["applied_revision"]}))
        return result

    def upgrade_project(self, params, context):
        result = self.projects.upgrade(params)
        if result["upgraded"]:
            context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                                "revision": result["revision"]}))
        return result

    def restore_project(self, params, context, *, redo):
        result = self.projects.redo(params) if redo else self.projects.undo(params)
        context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                            "revision": result["revision"]}))
        return result

    def edit_project_files(self, action, params, context):
        result = self.projects.files(action, params)
        context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                            "revision": result["revision"]}))
        return result

    def edit_project_analyses(self, action, params, context):
        result = self.projects.analyses(action, params)
        context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                            "revision": result["revision"]}))
        return result

    def edit_project_workflows(self, action, params, context):
        result = self.projects.workflows(action, params)
        context.after(lambda: self.emit("project.changed", {"handle": params["handle"],
                                                            "revision": result["revision"]}))
        return result

    def close_project(self, params, context):
        result = self.projects.close(params)
        if result["closed"]:
            context.after(lambda: self.emit("project.closed", {"handle": params["handle"]}))
        return result

    def hello(self, params, context):
        if params["protocol"] != PROTOCOL_VERSION:
            raise BridgeError("unsupported", f"This bridge speaks protocol {PROTOCOL_VERSION}",
                              data={"supported": [PROTOCOL_VERSION]})
        resumed = self.transfers.resume_interrupted() if params.get("resume_transfers", True) else []
        if not self._local_started:
            # Local model servers that were running when the service last stopped start again, after this reply.
            self._local_started = True
            context.after(self.projects.local.autostart)
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
                                                           params.get("check", True), params.get("ssh"))}

    def ssh_connection(self, params, context):
        return self.connections.ssh_control(params["id"], params["action"])

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
            # An uninitialized local Runtime is listed too: it is a state, not an unknown connection.
            if exc.code in ("unavailable", "unauthorized", "remote_error", "timeout") or (
                    connection == "local" and exc.code == "not_found"):
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
        return {"actions": [with_kind(record) for record in hub.call(hub.hub.actions)]}

    def hub_action(self, params, context):
        hub = self._hub(params)
        record = hub.call(hub.hub.action, params["action_id"])
        self.inspected[(params["connection"], record["id"])] = record["request"]
        return {"action": with_kind(record)}

    def hub_policy(self, params, context):
        hub = self._hub(params)
        return {"policy": hub.policy()}

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
        try:
            record = hub.hub.review(params["action_id"], params["approved"])
        except HubResponseError as exc:
            if exc.status == 403:  # the hub's review_policy (not-self / owner) refuses this device
                raise BridgeError("unauthorized", exc.message, data={"action_id": params["action_id"],
                                                                     "reason": "review_policy"}) from None
            raise hub_error(exc) from None
        except BridgeError:
            raise
        except Exception as exc:
            raise hub_error(exc) from None
        self.inspected.pop(key, None)
        return {"action": record}

    def upload_start(self, params, context):
        transfer = self.transfers.start_upload(params["connection"], params["workspace_id"], params["source"],
                                               params.get("remote"), params.get("node"),
                                               idempotency_key=params.get("idempotency_key"))
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
                                                 params.get("node"), idempotency_key=params.get("idempotency_key"))
        return {"transfer": transfer}

    def unsubscribe(self, params, context):
        self.subscriptions.cancel(params["sub"])
        return {"ok": True}
