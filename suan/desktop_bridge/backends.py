"""One interface over a direct Runtime connection and a node reached through the control hub.

A :class:`RuntimeBackend` talks to an STK Runtime (``suan.runtime.client.RuntimeClient``; loopback
or an SSH tunnel). A :class:`HubBackend` reaches one execution node of a paired control hub: reads
come from the node's heartbeat snapshot, and operations become hub actions (``suan.control``) whose
ids are derived from the caller's idempotency keys, so a retried request never creates a second
operation. Actions that need review return with ``state: "review"``. Polled reads (logs, events,
artifacts, file chunks, workspace inputs) use the hub's read path (``POST /api/v1/nodes/<id>/read``,
no action row); a hub or node agent without it gets a read action instead. Uploads go into the hub's
blob store (resumable sessions) and then into the workspace through a ``workspace.import`` action.
"""
import base64
import hashlib
import socket
import time
import uuid
from urllib.error import URLError
from urllib.parse import urlencode

from suan.runtime.client import RuntimeClient, RuntimeErrorResponse
from suan.runtime.models import TaskSpec

from .hub import HubClient, HubResponseError, hub_error
from .protocol import BridgeError

__all__ = ["HubBackend", "RuntimeBackend", "action_id", "runtime_error"]

LOG_STREAMS = ("stdout", "stderr", "scheduler.out", "scheduler.err", "wrapper")
FILE_CHUNK = 1024 * 1024
ACTION_WAIT = 30.0
FINISHED_ACTIONS = {"succeeded", "failed", "rejected"}
READ_PATH_RETRY = 60.0
# (hub url, node id) -> monotonic time the hub or node answered that it has no read path.
_NO_READ_PATH = {}


def action_failure(record, message=None):
    """The BridgeError of a failed or rejected hub action (``cancelled`` for a cancelled evaluation)."""
    data = {"action": summary(record)}
    if record["state"] == "rejected":
        return BridgeError("remote_error", message or "The action was rejected in review", data=data)
    error = record.get("error") or "The node reported a failure"
    if error.startswith("cancelled:"):
        return BridgeError("cancelled", error.partition(":")[2].strip() or "Cancelled", data=data)
    return BridgeError("remote_error", error, data=data)


def runtime_error(exc):
    """A :class:`BridgeError` for a Runtime transport or response failure."""
    if isinstance(exc, BridgeError):
        return exc
    if isinstance(exc, RuntimeErrorResponse):
        status, message = exc.status, str(exc)
        if status in (401, 403):
            return BridgeError("unauthorized", f"The Runtime refused the stored token ({status})")
        if status == 404:
            return BridgeError("not_found", message)
        if status == 409 or (status == 400 and ("Idempotency key" in message or "offset/size conflict" in message
                                                or "reused" in message)):
            return BridgeError("conflict", message)
        if status >= 500:
            return BridgeError("remote_error", message, retryable=True)
        return BridgeError("remote_error", message)
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return BridgeError("unavailable", "The Runtime did not answer in time; retry")
    if isinstance(exc, (URLError, ConnectionError, OSError)):
        return BridgeError("unavailable", f"The Runtime cannot be reached ({type(exc).__name__}); "
                           "check that it runs and the SSH tunnel is open")
    return BridgeError("internal_error", f"{type(exc).__name__}: {exc}")


def action_id(*parts):
    """A deterministic 32-hex hub action id for an operation identity (idempotency key)."""
    return hashlib.sha256("\x00".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]


def _check_task_id(task_id):
    if not isinstance(task_id, str) or not task_id:
        raise BridgeError("invalid_params", "A task id is required")
    return task_id


class RuntimeBackend:
    kind = "runtime"

    def __init__(self, connection_id, client):
        self.connection_id = connection_id
        self.client = client  # RuntimeClient (duck-typed in tests)

    @property
    def server_key(self):
        """A stable, credential-free key of this Runtime (download cache directories)."""
        return hashlib.sha256(self.client.url.encode("utf-8")).hexdigest()[:16]

    def call(self, function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except BridgeError:
            raise
        except (RuntimeErrorResponse, URLError, OSError) as exc:
            raise runtime_error(exc) from None

    def health(self):
        return self.call(self.client.health)

    def workspaces(self):
        return {"workspaces": self.call(self.client.workspaces)}

    def create_workspace(self, name, key=None):
        return {"workspace": self.call(self.client.create_workspace, name, key)}

    def files(self, workspace_id):
        return {"files": self.call(self.client.files, workspace_id)}

    def submit(self, spec, key, template=None, workspace_id=None):
        if spec is None:
            raise BridgeError("invalid_params", "A direct Runtime connection needs a full 'spec' (templates are "
                              "hub-registered)")
        try:
            spec = TaskSpec(**spec).to_dict()
        except (TypeError, ValueError) as exc:
            raise BridgeError("invalid_params", f"Invalid task spec: {exc}") from None
        return {"task": self.call(self.client.submit, spec, key)}

    def tasks(self, workspace_id=None):
        return {"tasks": self.call(self.client.tasks, workspace_id)}

    def task(self, task_id):
        return {"task": self.call(self.client.task, _check_task_id(task_id))}

    def cancel(self, task_id, key=None):
        return {"task": self.call(self.client.cancel, _check_task_id(task_id))}

    def artifacts(self, task_id):
        return {"artifacts": self.call(self.client.artifacts, _check_task_id(task_id))}

    def logs(self, task_id, stream, offset, limit):
        query = urlencode({"stream": stream, "offset": offset, "limit": limit})
        response = self.call(self.client.request, "GET", f"tasks/{task_id}/logs?{query}")
        return {"data": base64.b64decode(response["data"]), "offset": response["offset"],
                "next_offset": response["next_offset"], "terminal": bool(response["terminal"])}

    def events(self, task_id, offset):
        try:
            return self.client.events(task_id, offset)
        except RuntimeErrorResponse as exc:
            if exc.status == 404:
                try:
                    features = self.client.health().get("features") or ()
                except Exception:
                    features = ()
                if "events" not in features:
                    raise BridgeError("unsupported", "This Runtime does not publish monitoring events; upgrade "
                                      "its STK Runtime") from None
            raise runtime_error(exc) from None
        except (URLError, OSError) as exc:
            raise runtime_error(exc) from None

    def describe(self, owner, owner_id, path):
        """``{path, size, sha256}`` of a task artifact (``owner="task"``) or a workspace input file."""
        items = self.artifacts(owner_id)["artifacts"] if owner == "task" else self.files(owner_id)["files"]
        item = next((a for a in items if a["path"] == path), None)
        if item is None:
            raise BridgeError("not_found", "Artifact not found; wait for the task to finish" if owner == "task"
                              else "Workspace file not found")
        return item

    def read_chunk(self, owner, owner_id, path, offset, limit=FILE_CHUNK):
        route = f"tasks/{owner_id}/file" if owner == "task" else f"workspaces/{owner_id}/file"
        query = urlencode({"path": path, "offset": offset, "limit": limit})
        return self.call(self.client.request, "GET", route + "?" + query, binary=True)

    # Uploads (RuntimeService.begin_upload / upload_chunk / finish_upload / abort_upload).
    def upload_begin(self, workspace_id, path, size, digest):
        return self.call(self.client.request, "POST", f"workspaces/{workspace_id}/uploads",
                         {"path": path, "size": size, "sha256": digest})

    def upload_status(self, workspace_id, upload_id):
        return self.call(self.client.request, "GET", f"workspaces/{workspace_id}/uploads/{upload_id}")

    def upload_chunk(self, workspace_id, upload_id, offset, data):
        return self.call(self.client.request, "PUT", f"workspaces/{workspace_id}/uploads/{upload_id}?offset={offset}",
                         data)

    def upload_finish(self, workspace_id, upload_id):
        return self.call(self.client.request, "POST", f"workspaces/{workspace_id}/uploads/{upload_id}/finish", {})

    def upload_abort(self, workspace_id, upload_id):
        return self.call(self.client.request, "DELETE", f"workspaces/{workspace_id}/uploads/{upload_id}")


class HubBackend:
    kind = "hub"

    def __init__(self, connection_id, hub, node_id, *, wait=ACTION_WAIT):
        self.connection_id = connection_id
        self.hub = hub  # HubClient
        self.node_id = node_id
        self.wait = wait

    @property
    def server_key(self):
        return hashlib.sha256((self.hub.url + "\x00" + self.node_id).encode("utf-8")).hexdigest()[:16]

    def call(self, function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except BridgeError:
            raise
        except Exception as exc:  # transport and response errors of urllib
            raise hub_error(exc) from None

    # -- snapshot reads -------------------------------------------------------------------------

    def device(self):
        devices = self.call(self.hub.devices)
        device = next((d for d in devices if d["id"] == self.node_id and d["role"] == "node"), None)
        if device is None:
            raise BridgeError("not_found", "Execution node not found on this hub")
        return device

    def snapshot(self):
        snapshot = self.device().get("snapshot") or {}
        if "error" in snapshot and "tasks" not in snapshot:
            raise BridgeError("unavailable", "The node reports that its Runtime is unavailable", retryable=True)
        return snapshot

    def health(self):
        device = self.device()
        snapshot = device.get("snapshot") or {}
        return {**(snapshot.get("health") or {}), "online": bool(device.get("online")),
                "node_features": snapshot.get("features") or []}

    def workspaces(self):
        return {"workspaces": list(self.snapshot().get("workspaces") or [])}

    def tasks(self, workspace_id=None):
        tasks = [t for t in self.snapshot().get("tasks") or []
                 if workspace_id is None or t.get("workspace_id") == workspace_id]
        return {"tasks": tasks}

    def task(self, task_id):
        found = next((t for t in self.snapshot().get("tasks") or [] if t.get("id") == task_id), None)
        if found is None:
            raise BridgeError("not_found", "Task not found in the node's latest snapshot")
        return {"task": found}

    def files(self, workspace_id):
        return {"files": self._read("workspace.files", {"workspace_id": workspace_id})}

    def policy(self):
        return self.call(self.hub.policy)

    # -- actions --------------------------------------------------------------------------------

    def run_action(self, kind, payload, identity, *, wait=None, cancel=None):
        """Create (idempotently) and wait for one hub action; returns the full action record."""
        body = {"id": identity, "node_id": self.node_id, "kind": kind, "payload": payload}
        record = self.call(self.hub.post_action, body)
        deadline = time.monotonic() + (self.wait if wait is None else wait)
        delay = 0.05
        while record["state"] not in FINISHED_ACTIONS and record["state"] != "review":
            if cancel is not None and cancel():
                raise BridgeError("cancelled", "Stopped waiting for the hub action; it may still run on the node",
                                  data={"action": summary(record)})
            if time.monotonic() >= deadline:
                raise BridgeError("timeout", "The hub action has not finished yet; repeat the request to keep "
                                  "waiting", data={"action": summary(record)})
            time.sleep(delay)
            delay = min(0.5, delay * 1.5)
            record = self.call(self.hub.action, identity)
        if record["state"] in ("failed", "rejected"):
            raise action_failure(record)
        return record

    def _operation(self, kind, payload, identity, result_key):
        record = self.run_action(kind, payload, identity)
        out = {"action": summary(record)}
        if record["state"] == "succeeded":
            out[result_key] = record["result"]
        return out

    def create_workspace(self, name, key=None):
        identity = action_id("workspace.create", self.node_id, key) if key else uuid.uuid4().hex
        return self._operation("workspace.create", {"name": name}, identity, "workspace")

    def submit(self, spec, key, template=None, workspace_id=None):
        if template is not None:
            if not workspace_id:
                raise BridgeError("invalid_params", "A template submission needs 'workspace_id'")
            payload = {"template": template, "workspace_id": workspace_id}
        else:
            if spec is None:
                raise BridgeError("invalid_params", "Give a 'spec' or a hub 'template'")
            try:
                TaskSpec(**spec)
            except (TypeError, ValueError) as exc:
                raise BridgeError("invalid_params", f"Invalid task spec: {exc}") from None
            payload = {"spec": spec}
        return self._operation("task.submit", payload, action_id("task.submit", self.node_id, key), "task")

    def cancel(self, task_id, key=None):
        identity = action_id("task.cancel", self.node_id, key) if key else uuid.uuid4().hex
        return self._operation("task.cancel", {"task_id": _check_task_id(task_id)}, identity, "task")

    def _read(self, kind, payload):
        """A review-free read: the hub's read path (no action row), else a read action.

        Hubs and node agents from before the read path answer 404/405 (no route) or 501 (agent);
        they get read actions (a fresh id per call: the node caches results by action id), and the
        read path is tried again a minute later.
        """
        key = (self.hub.url, self.node_id)
        refused = _NO_READ_PATH.get(key)
        if refused is None or time.monotonic() - refused > READ_PATH_RETRY:
            try:
                return self.hub.read(self.node_id, kind, payload)
            except HubResponseError as exc:
                if exc.status == 422:  # the node answered with an error (unknown task, missing file, ...)
                    raise BridgeError("remote_error", exc.message) from None
                if not (exc.status in (405, 501) or (exc.status == 404 and exc.message == "Not Found")):
                    raise hub_error(exc) from None
                _NO_READ_PATH[key] = time.monotonic()
            except BridgeError:
                raise
            except Exception as exc:
                raise hub_error(exc) from None
        return self.run_action(kind, payload, uuid.uuid4().hex)["result"]

    def artifacts(self, task_id):
        return {"artifacts": self._read("task.artifacts", {"task_id": _check_task_id(task_id)})}

    def logs(self, task_id, stream, offset, limit):
        response = self._read("task.logs", {"task_id": task_id, "stream": stream, "offset": offset})
        data = base64.b64decode(response["data"])
        return {"data": data, "offset": response["offset"], "next_offset": response["next_offset"],
                "terminal": bool(response["terminal"])}

    def events(self, task_id, offset):
        return self._read("task.events", {"task_id": task_id, "offset": offset})

    def describe(self, owner, owner_id, path):
        items = self.artifacts(owner_id)["artifacts"] if owner == "task" else self.files(owner_id)["files"]
        item = next((a for a in items if a["path"] == path), None)
        if item is None:
            raise BridgeError("not_found", "Artifact not found; wait for the task to finish" if owner == "task"
                              else "Workspace file not found")
        return item

    def read_chunk(self, owner, owner_id, path, offset, limit=FILE_CHUNK):
        key = "task_id" if owner == "task" else "workspace_id"
        result = self._read("file.read", {key: owner_id, "path": path, "offset": offset})
        return base64.b64decode(result["data"])

    # Uploads: the bytes go into the hub's blob store (the same begin/chunk/finish/abort shape as the
    # Runtime's sessions); workspace.import then moves them into the workspace on the node.
    def upload_begin(self, workspace_id, path, size, digest):
        return self.call(self.hub.upload_begin, digest, size)

    def upload_status(self, workspace_id, upload_id):
        return self.call(self.hub.upload_status, upload_id)

    def upload_chunk(self, workspace_id, upload_id, offset, data):
        return self.call(self.hub.upload_chunk, upload_id, offset, data)

    def upload_finish(self, workspace_id, upload_id):
        return self.call(self.hub.upload_finish, upload_id)

    def upload_abort(self, workspace_id, upload_id):
        return self.call(self.hub.upload_abort, upload_id)

    def post_import(self, workspace_id, files, identity):
        """Create (idempotently) the ``workspace.import`` action; returns its record without waiting."""
        return self.call(self.hub.post_action, {"id": identity, "node_id": self.node_id, "kind": "workspace.import",
                                                "payload": {"workspace_id": workspace_id, "files": files}})

    def action_record(self, identity):
        return self.call(self.hub.action, identity)

    def reject(self, identity):
        return self.call(self.hub.review, identity, False)

    def cancel_evaluation(self, target, wait=10.0):
        """Ask the hub to cancel ``graph.evaluate`` action ``target`` (in review: at once; running: on the node)."""
        record = self.run_action("graph.cancel", {"action_id": target},
                                 action_id("graph.cancel", self.node_id, target), wait=wait)
        return record


def summary(record):
    """The action fields the app shows (results are returned separately)."""
    keys = ("id", "node_id", "state", "error", "review_reason", "created", "updated")
    return {key: record.get(key) for key in keys if key in record} | {"kind": record["request"]["kind"]}


def make_runtime_client(url, token):
    try:
        return RuntimeClient(url, token)
    except ValueError as exc:
        raise BridgeError("invalid_params", str(exc)) from None


def make_hub_client(url, token=""):
    try:
        return HubClient(url, token)
    except ValueError as exc:
        raise BridgeError("invalid_params", str(exc)) from None
