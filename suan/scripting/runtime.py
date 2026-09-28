"""Console helpers over the desktop's existing Runtime/Hub operations.

Mutations require caller-owned idempotency keys. No helper retries a failed request, approves a
Hub action, or cancels accepted work when the Python worker is interrupted.
"""
import base64
import math
from pathlib import Path
import time


def _wait(read, done, timeout, interval):
    for name, value in (("timeout", timeout), ("interval", interval)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
    if timeout < 0 or interval <= 0:
        raise ValueError("timeout must be nonnegative and interval must be positive")
    deadline = time.monotonic() + timeout
    while True:
        result = read()
        if done(result):
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Wait expired; accepted remote work was not cancelled")
        time.sleep(min(interval, remaining))


class Connections:
    def __init__(self, call):
        self._call = call

    def list(self):
        """Saved profiles without their credentials."""
        return self._call("connections.list", {})["connections"]

    def check(self, connection):
        return self._call("connections.check", {"id": connection})

    def ssh(self, connection, action="status"):
        """Inspect, explicitly connect, or disconnect a saved managed SSH profile."""
        return self._call("connections.ssh", {"id": connection, "action": action})


class Transfers:
    def __init__(self, call):
        self._call = call

    def list(self):
        return self._call("transfer.list", {})["transfers"]

    def get(self, transfer_id):
        return self._call("transfer.get", {"id": transfer_id})["transfer"]

    def resume(self, transfer_id):
        return self._call("transfer.resume", {"id": transfer_id})["transfer"]

    def cancel(self, transfer_id):
        return self._call("transfer.cancel", {"id": transfer_id})["transfer"]

    def wait(self, transfer_id, *, timeout=300, interval=0.25):
        """Return on completion, failure, cancellation, interruption, or pending Hub review.

        Inspect ``state`` and ``action``; returning is not a claim of success. Timeout only stops
        polling, and transport failures propagate without an automatic reconnect or resume.
        """
        return _wait(lambda: self.get(transfer_id),
                     lambda r: r["state"] not in {"queued", "running"}
                     or (r.get("action") or {}).get("state") == "review", timeout, interval)


class Runtime:
    """A saved connection and optional Hub execution-node identity; construction makes no request."""
    def __init__(self, call, connection, *, node=None):
        self._call = call
        self.connection, self.node = connection, node
        self.workspaces = Workspaces(self)
        self.tasks = Tasks(self)

    def _request(self, operation, **params):
        params["connection"] = self.connection
        if self.node is not None:
            params["node"] = self.node
        return self._call(operation, params)

    def upload(self, workspace_id, source, *, idempotency_key, remote=None):
        params = {"workspace_id": workspace_id, "source": str(Path(source).absolute()),
                  "idempotency_key": idempotency_key}
        if remote is not None:
            params["remote"] = remote
        return self._request("upload.start", **params)["transfer"]

    def download(self, path, *, idempotency_key, task_id=None, workspace_id=None, dest=None):
        if (task_id is None) == (workspace_id is None):
            raise ValueError("Choose exactly one of task_id and workspace_id")
        params = {"path": path, "idempotency_key": idempotency_key}
        params["task_id" if task_id is not None else "workspace_id"] = task_id if task_id is not None else workspace_id
        if dest is not None:
            params["dest"] = str(Path(dest).absolute())
        return self._request("download.start", **params)["transfer"]


class Workspaces:
    def __init__(self, runtime):
        self._runtime = runtime

    def list(self):
        return self._runtime._request("workspace.list")["workspaces"]

    def create(self, name, *, idempotency_key):
        """Return the full result: a Hub action needing review may not have a workspace yet."""
        return self._runtime._request("workspace.create", name=name, idempotency_key=idempotency_key)

    def files(self, workspace_id):
        return self._runtime._request("workspace.files", workspace_id=workspace_id)["files"]


class Tasks:
    def __init__(self, runtime):
        self._runtime = runtime

    def list(self, *, workspace_id=None):
        params = {} if workspace_id is None else {"workspace_id": workspace_id}
        return self._runtime._request("task.list", **params)["tasks"]

    def submit(self, spec=None, *, idempotency_key, template=None, workspace_id=None):
        """Return the full result, including a pending Hub action when submission needs review."""
        params = {"idempotency_key": idempotency_key}
        for name, value in (("spec", spec), ("template", template), ("workspace_id", workspace_id)):
            if value is not None:
                params[name] = value
        return self._runtime._request("task.submit", **params)

    def get(self, task_id):
        return self._runtime._request("task.get", task_id=task_id)["task"]

    def cancel(self, task_id, *, idempotency_key):
        return self._runtime._request("task.cancel", task_id=task_id, idempotency_key=idempotency_key)

    def artifacts(self, task_id):
        return self._runtime._request("task.artifacts", task_id=task_id)["artifacts"]

    def logs(self, task_id, *, stream="stdout", offset=0, limit=65536):
        """A bounded byte chunk. Decode after joining chunks, or use an incremental UTF-8 decoder."""
        result = self._runtime._request("task.logs", task_id=task_id, stream=stream, offset=offset, limit=limit)
        return {**result, "data": base64.b64decode(result["data"], validate=True)}

    def wait(self, task_id, *, timeout=300, interval=0.25):
        """Return a terminal task or ``unknown``; inspect state before using its outputs."""
        return _wait(lambda: self.get(task_id),
                     lambda r: r["state"] in {"succeeded", "failed", "cancelled", "unknown"}, timeout, interval)
