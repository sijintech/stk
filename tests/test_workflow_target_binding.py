"""A frozen workflow target survives profile changes and transfer-worker/restart boundaries."""
from contextvars import ContextVar
import threading

import pytest

from suan.desktop_bridge.transfers import TransferManager
from suan.desktop_bridge.protocol import BridgeError
from suan.project import ProjectStore
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


class Backend:
    kind = "runtime"

    def __init__(self, identity):
        self.server_key = identity
        self.workspaces_created = 0

    def create_workspace(self, name, key=None):
        self.workspaces_created += 1
        return {"workspace": {"id": "b" * 32, "name": name}}


def test_workflow_checks_the_exact_backend_used_for_each_operation(inproc, tmp_path, monkeypatch):
    h = inproc()
    store = ProjectStore.create(tmp_path / "project", "Target binding")
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    store = h.bridge.projects._stores[handle]
    a, b = Backend("a" * 16), Backend("b" * 16)
    current = [a]
    monkeypatch.setattr(h.bridge.connections, "backend", lambda connection, node=None: current[0])
    api = h.bridge._workflow_scripting(store, threading.Event(), simulation={
        "connection": "runtime:lab", "connection_identity": a.server_key, "options": {}})
    api.runtime("runtime:lab").workspaces.create("Approved", idempotency_key="approved")
    current[0] = b  # profile changed after approval and after a prior successful operation
    with pytest.raises(BridgeError, match="endpoint changed"):
        api.runtime("runtime:lab").workspaces.create("Refused", idempotency_key="refused")
    with pytest.raises(BridgeError, match="another Runtime"):
        api.runtime("runtime:other").workspaces.create("Wrong profile", idempotency_key="wrong")
    assert a.workspaces_created == 1 and b.workspaces_created == 0
    # The workflow guard is scoped to that dispatch, not leaked into ordinary explicit desktop work.
    assert h.bridge._workflow_target.get() is None
    h.call("workspace.create", {"connection": "runtime:lab", "name": "Manual", "idempotency_key": "manual"})
    assert b.workspaces_created == 1


def test_transfer_worker_retains_workflow_context(tmp_path, monkeypatch):
    target = ContextVar("test_workflow_target", default=None)
    seen = []
    backend = Backend("a" * 16)

    def bound(connection, node=None):
        seen.append(target.get())
        assert target.get() == "approved-target"
        return backend

    manager = TransferManager(tmp_path / "bridge", lambda *args: None, bound)
    source = tmp_path / "input.txt"
    source.write_text("manufactured input")
    monkeypatch.setattr(manager, "_upload", lambda record, backend: record.update(state="succeeded"))
    token = target.set("approved-target")
    try:
        transfer = manager.start_upload("runtime:lab", "c" * 32, source)
    finally:
        target.reset(token)
    manager.threads[transfer["id"]].join(5)
    assert manager.load(transfer["id"])["state"] == "completed"
    assert len(seen) >= 3 and all(value == "approved-target" for value in seen)
    manager.stop()


def test_reopened_transfer_refuses_changed_endpoint_before_any_bytes_move(tmp_path, monkeypatch):
    a, b = Backend("a" * 16), Backend("b" * 16)
    source = tmp_path / "input.txt"
    source.write_text("manufactured input")
    first = TransferManager(tmp_path / "bridge", lambda *args: None, lambda *args: a)
    monkeypatch.setattr(first, "_launch", lambda identity: None)  # crash after journaling, before worker dispatch
    transfer = first.start_upload("runtime:lab", "c" * 32, source)
    assert first.load(transfer["id"])["connection_identity"] == a.server_key
    first.stop()
    reopened = TransferManager(tmp_path / "bridge", lambda *args: None, lambda *args: b)
    moved = []
    monkeypatch.setattr(reopened, "_upload", lambda *args: moved.append(True))
    reopened.resume(transfer["id"])
    reopened.threads[transfer["id"]].join(5)
    record = reopened.load(transfer["id"])
    assert record["state"] == "failed" and record["error"]["code"] == "conflict"
    assert moved == []
    reopened.stop()
