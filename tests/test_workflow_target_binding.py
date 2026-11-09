"""A frozen workflow target survives profile changes and transfer-worker/restart boundaries."""
from contextvars import ContextVar
import hashlib
import os
import threading

import pytest

from mupro_fake import write_case
from suan.desktop_bridge.transfers import TransferManager
from suan.desktop_bridge.protocol import BridgeError
from suan.mupro import muferro_spec
from suan.mupro.run import RUN_OUTPUTS, expected_frames, read_case
from suan.project import ProjectStore
from suan.scripting import API
from suan.workflows.muferro import FIELD_IDS, LABEL, TABLE_ID
from test_desktop_bridge import BridgeCallError, bridge_env, inproc  # noqa: F401


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


@pytest.mark.parametrize("kind", ["upload", "download"])
def test_reopened_transfer_refuses_changed_endpoint_before_any_bytes_move(tmp_path, monkeypatch, kind):
    a, b = Backend("a" * 16), Backend("b" * 16)
    source = tmp_path / "input.txt"
    source.write_text("manufactured input")
    first = TransferManager(tmp_path / "bridge", lambda *args: None, lambda *args: a)
    monkeypatch.setattr(first, "_launch", lambda identity: None)  # crash after journaling, before worker dispatch
    if kind == "upload":
        transfer = first.start_upload("runtime:lab", "c" * 32, source)
    else:
        transfer = first.start_download("runtime:lab", "task", "c" * 32, "result.dat", tmp_path / "result.dat",
                                        expected_connection_identity=a.server_key)
    assert first.load(transfer["id"])["connection_identity"] == a.server_key
    first.stop()
    reopened = TransferManager(tmp_path / "bridge", lambda *args: None, lambda *args: b)
    moved = []
    monkeypatch.setattr(reopened, "_" + kind, lambda *args: moved.append(True))
    reopened.resume(transfer["id"])
    reopened.threads[transfer["id"]].join(5)
    record = reopened.load(transfer["id"])
    assert record["state"] == "failed" and record["error"]["code"] == "conflict"
    assert moved == []
    reopened.stop()


def test_cold_restarted_guarded_download_completes_only_after_the_original_endpoint_returns(tmp_path, monkeypatch):
    payload = b"synthetic frozen result bytes"
    digest = hashlib.sha256(payload).hexdigest()
    observed = []

    class SyntheticBackend(Backend):
        def __init__(self, name, identity):
            super().__init__(identity)
            self.name = name

        def describe(self, owner, owner_id, path):
            observed.append((self.name, "describe", owner, owner_id, path))
            return {"path": path, "size": len(payload), "sha256": digest}

        def read_chunk(self, owner, owner_id, path, offset):
            observed.append((self.name, "read_chunk", offset))
            return payload[offset:offset + 8]  # several reads through the real append loop

    original, replacement = SyntheticBackend("original", "a" * 16), SyntheticBackend("replacement", "b" * 16)
    active = [original]  # the mock desktop profile's current Runtime

    def resolve(connection, node=None):
        return active[0]

    dest = tmp_path / "downloads" / "result.dat"  # its directory is only created after describe
    start = ("runtime:lab", "task", "c" * 32, "case/result.dat", dest)
    key = "frozen-collect-result"

    first = TransferManager(tmp_path / "bridge", lambda *args: None, resolve)
    monkeypatch.setattr(first, "_launch", lambda identity: None)  # crash after journaling, before worker dispatch
    transfer = first.start_download(*start, idempotency_key=key, expected_connection_identity=original.server_key)
    journaled = first.load(transfer["id"])
    assert transfer["id"] == TransferManager.keyed_id("download", key) and journaled["state"] == "queued"
    assert journaled["connection_identity"] == original.server_key and journaled["idempotency_key"] == key
    assert "expected_connection_identity" not in journaled["request"]
    first.stop()
    assert observed == [] and not dest.parent.exists()

    active[0] = replacement  # the desktop profile now names another Runtime
    reopened = TransferManager(tmp_path / "bridge", lambda *args: None, resolve)
    assert reopened.load(transfer["id"])["state"] == "interrupted"
    reopened.resume(transfer["id"])
    reopened.threads[transfer["id"]].join(5)
    assert not reopened.threads[transfer["id"]].is_alive()
    refused = reopened.load(transfer["id"])
    assert refused["state"] == "failed" and refused["error"]["code"] == "conflict"
    assert refused.get("sha256") is None and refused["bytes_done"] == 0
    assert observed == [] and not dest.parent.exists()

    active[0] = original  # restore the approved profile and explicitly resume the same transfer
    resumed = reopened.resume(transfer["id"])
    assert resumed["id"] == transfer["id"]
    reopened.threads[transfer["id"]].join(5)
    assert not reopened.threads[transfer["id"]].is_alive()
    done = reopened.load(transfer["id"])
    assert done["state"] == "completed" and done.get("error") is None
    assert done["sha256"] == digest and done["bytes_done"] == done["bytes_total"] == len(payload)
    assert done["files_done"] == 1 and done["items"][0]["done"] is True
    assert dest.read_bytes() == payload and hashlib.sha256(dest.read_bytes()).hexdigest() == digest
    assert sorted(path.name for path in dest.parent.iterdir()) == [dest.name]  # part and its meta published away
    for field in ("id", "request", "idempotency_key", "connection_identity", "created_at", "local", "remote"):
        assert done[field] == journaled[field]
    assert observed == [("original", "describe", "task", "c" * 32, "case/result.dat")] + [
        ("original", "read_chunk", offset) for offset in range(0, len(payload), 8)]
    assert all(name == "original" for name, *_ in observed)  # the replacement saw no describe or read

    replay = reopened.start_download(*start, idempotency_key=key, expected_connection_identity=original.server_key)
    assert replay["id"] == transfer["id"] and replay["state"] == "completed"
    assert [entry["id"] for entry in reopened.list()] == [transfer["id"]]
    assert len(observed) == 1 + len(range(0, len(payload), 8))
    reopened.stop()


def test_guarded_keyed_download_replays_the_matching_journal_and_preserves_legacy_calls(inproc, tmp_path, monkeypatch):
    h = inproc()
    a, b = Backend("a" * 16), Backend("b" * 16)
    active, resolutions, launches = [a], [], []

    def resolve(connection, node=None):
        resolutions.append((connection, node))
        return active[0]

    manager = h.bridge.transfers
    monkeypatch.setattr(h.bridge.connections, "backend", resolve)
    monkeypatch.setattr(manager, "_launch", launches.append)
    params = {"connection": "hub:fixture", "node": "e" * 32, "task_id": "c" * 32,
              "path": "case/energy_out.dat", "idempotency_key": "download-once"}
    dest = str(tmp_path / "legacy.dat")
    legacy = h.call("download.start", {**params, "dest": dest})["transfer"]
    guarded = {**params, "idempotency_key": "guarded-default", "expected_connection_identity": a.server_key}
    original = h.call("download.start", guarded)["transfer"]
    cached = h.bridge.download_dir / a.server_key / params["task_id"]
    assert cached.is_dir()
    if os.name != "nt":
        assert cached.stat().st_mode & 0o777 == 0o700
    assert resolutions == [(params["connection"], params["node"])] * 2
    assert launches == [legacy["id"], original["id"]]
    assert manager.load(legacy["id"])["connection_identity"] == a.server_key
    assert manager.load(original["id"])["connection_identity"] == a.server_key
    assert "expected_connection_identity" not in manager.load(original["id"])["request"]

    active[0] = b
    assert h.call("download.start", guarded)["transfer"] == original
    assert h.call("download.start", {**params, "dest": dest, "expected_connection_identity": a.server_key})["transfer"] == legacy
    assert len(resolutions) == 2 and len(launches) == 2

    with pytest.raises(BridgeCallError) as wrong:
        h.call("download.start", {**params, "dest": dest, "expected_connection_identity": b.server_key})
    assert wrong.value.code == "conflict" and wrong.value.error["data"]["transfer_id"] == legacy["id"]
    old_record = manager.load(legacy["id"])
    old_record.pop("connection_identity")
    manager.save(old_record)
    with pytest.raises(BridgeCallError) as missing:
        h.call("download.start", {**params, "dest": dest, "expected_connection_identity": a.server_key})
    assert missing.value.code == "conflict" and missing.value.error["data"]["transfer_id"] == legacy["id"]
    assert h.call("download.start", {**params, "dest": dest})["transfer"]["id"] == legacy["id"]
    assert len(resolutions) == 2 and len(launches) == 2
    assert manager.load(legacy["id"]) == old_record

    rejected_task = "d" * 32
    with pytest.raises(BridgeCallError) as switched:
        h.call("download.start", {**guarded, "idempotency_key": "fresh-mismatch", "task_id": rejected_task})
    assert switched.value.code == "conflict"
    assert {entry["id"] for entry in manager.list()} == {legacy["id"], original["id"]}
    assert launches == [legacy["id"], original["id"]]
    assert len(resolutions) == 3 and not (cached.parent / rejected_task).exists()


@pytest.mark.parametrize("bad", [None, "../cache-escape", "A" * 16, "a" * 16 + "\n"])
def test_connection_identity_precondition_rejects_malformed_values(inproc, monkeypatch, bad):
    h = inproc()

    def unexpected(*args):
        pytest.fail("An invalid identity must be refused before resolving a backend")

    monkeypatch.setattr(h.bridge.connections, "backend", unexpected)
    params = {"connection": "runtime:lab", "task_id": "c" * 32, "expected_connection_identity": bad}
    for operation, fields in (("task.artifacts", {}), ("download.start", {"path": "result.dat"})):
        with pytest.raises(BridgeCallError) as error:
            h.call(operation, {**params, **fields}, check=False)
        assert error.value.code == "invalid_params"


@pytest.mark.parametrize("switch_after", ["project.runs.refresh", "task.artifacts"])
def test_muferro_collect_rejects_a_profile_switch_before_artifact_io(inproc, tmp_path, monkeypatch, switch_after):
    h = inproc()
    task = "a" * 32
    profile = "runtime:synthetic"
    source = tmp_path / "fixture-case"
    write_case(source)
    observed = []
    available = []

    class FixtureBackend:
        kind = "runtime"

        def __init__(self, name):
            self.name = name
            self.server_key = hashlib.sha256(name.encode()).hexdigest()[:16]

        def task(self, task_id):
            observed.append((self.name, "task", task_id))
            return {"task": {"id": task_id, "state": "succeeded"}}

        def artifacts(self, task_id):
            observed.append((self.name, "artifacts", task_id))
            return {"artifacts": list(available)}

        def describe(self, owner, task_id, path):
            observed.append((self.name, "describe", task_id))
            raise BridgeError("not_found", "Synthetic source has no file contents")

    original = FixtureBackend("original")
    replacement = FixtureBackend("replacement")
    active = [original]
    monkeypatch.setattr(h.bridge.connections, "backend", lambda name, node=None: active[0])

    def call(operation, params):
        result = h.call(operation, params)
        if operation == switch_after:
            active[0] = replacement
        return result

    api = API(call)
    p = api.projects.create(tmp_path / "fixture-project", "Fixture")
    row_id = api.muferro.import_case(source, expected_revision=0, project=p)["record_id"]
    model = p.snapshot()
    row = next(table for table in model["tables"] if table["id"] == TABLE_ID)["records"][0]
    frozen = row["values"][FIELD_IDS["source"]]
    bindings = {"case/" + name: value for name, value in frozen["bindings"].items()}
    spec = muferro_spec("b" * 32, case_dir="case", launcher="none", inputs=list(bindings))
    run_id = p.runs.prepare([{"label": LABEL + "Fixture", "table_id": TABLE_ID, "record_id": row_id,
        "input_snapshot_id": frozen["snapshot_id"], "input_bindings": bindings, "spec": spec}],
        connection=profile, expected_revision=model["project"]["revision"])["run_ids"][0]
    store = h.bridge.projects._stores[p.handle]
    store.runs.observe(run_id, {"task": {"id": task, "state": "succeeded"}, "submission": "accepted"})
    plan = p.runs.get(run_id)["plan"]
    if switch_after == "task.artifacts":
        hashes = {item["path"]: item["sha256"] for item in plan["inputs"]}
        names = set(bindings) | {"stk-mupro.json"} | {
            "case/" + name for name in (*RUN_OUTPUTS, *expected_frames(read_case(source)))}
        available.extend({"path": name, "size": 1, "sha256": hashes.get(name, "0" * 64)} for name in sorted(names))

    with pytest.raises(BridgeCallError) as error:
        api.muferro.collect(run_id, project=p)
    assert error.value.code == "conflict"
    expected = [("original", "task", task)]
    if switch_after == "task.artifacts":
        expected.append(("original", "artifacts", task))
    assert observed == expected
    assert h.bridge.transfers.list() == []
    assert p.snapshot()["project"]["revision"] == model["project"]["revision"] + 1
