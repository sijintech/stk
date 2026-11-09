"""Deterministic transfer handoff between a published terminal state and worker cleanup."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.transfers import TransferManager
import suan.desktop_bridge.transfers as transfers


@pytest.mark.parametrize("bad_state", [[], {}], ids=["array", "object"])
@pytest.mark.parametrize("aged", [False, True], ids=["recent", "old"])
@pytest.mark.parametrize("active_state", ["queued", "running"])
def test_startup_recovers_other_transfers_without_touching_bad_state_journals(
        tmp_path, monkeypatch, bad_state, aged, active_state):
    source = tmp_path / "input.txt"
    source.write_text("public restart fixture", encoding="utf-8")
    state = tmp_path / "state"
    launches, events, backend_reads = [], [], []

    def backend(*args):
        backend_reads.append(args)
        return SimpleNamespace(kind="runtime", server_key="runtime:test")

    monkeypatch.setattr(TransferManager, "_launch", lambda self, transfer_id: launches.append(transfer_id))
    manager = TransferManager(state, lambda *args: events.append(args), backend)
    restarted = None
    try:
        first = manager.start_upload("runtime:test", "workspace", source, idempotency_key="restart-once")
        record = manager.load(first["id"])
        record["state"] = active_state
        manager.save(record)
        original_request = record["request"]
        bad_path = manager.root / ("f" * 32 + ".json")
        bad_bytes = json.dumps({"id": "f" * 32, "state": bad_state}).encode("utf-8")
        bad_path.write_bytes(bad_bytes)
        bad_lock = bad_path.with_suffix(".lock")
        bad_lock.write_bytes(b"preserve this existing lock")
        if aged:
            old = time.time() - transfers.KEEP_FINISHED_SECONDS - 60
            os.utime(bad_path, (old, old))
        bad_stat = bad_path.stat()
        manager.stop()
        launches.clear()
        backend_reads.clear()
        events.clear()

        restarted = TransferManager(state, lambda *args: events.append(args), backend)
        recovered = restarted.load(first["id"])
        assert recovered["state"] == "interrupted"
        assert recovered["request"] == original_request
        assert recovered["idempotency_key"] == "restart-once"
        assert recovered["connection_identity"] == "runtime:test"
        assert launches == backend_reads == events == []
        assert bad_path.read_bytes() == bad_bytes
        assert bad_path.stat().st_mtime_ns == bad_stat.st_mtime_ns
        assert bad_lock.read_bytes() == b"preserve this existing lock"

        # Explicit resume sees only the valid interrupted record, with its original identity.
        assert restarted.resume_interrupted() == [first["id"]]
        assert launches == [first["id"]]
        assert restarted.load(first["id"])["request"] == original_request
        assert bad_path.read_bytes() == bad_bytes
    finally:
        manager.stop()
        if restarted is not None:
            restarted.stop()


def test_startup_retains_unknown_state_and_collects_only_old_finished_journals(tmp_path):
    state = tmp_path / "state"
    root = state / "transfers"
    root.mkdir(parents=True)
    kept = {}
    old = time.time() - transfers.KEEP_FINISHED_SECONDS - 60
    for index, state_name in enumerate(("completed", "failed", "cancelled", "future-state"), 1):
        path = root / (f"{index:032x}" + ".json")
        path.write_text(json.dumps({"id": f"{index:032x}", "state": state_name}), encoding="utf-8")
        path.with_suffix(".lock").write_bytes(b"existing lock")
        os.utime(path, (old, old))
        if state_name == "future-state":
            kept[path] = path.read_bytes()
    recent = root / ("e" * 32 + ".json")
    recent.write_text(json.dumps({"id": "e" * 32, "state": "completed"}), encoding="utf-8")
    kept[recent] = recent.read_bytes()

    def unexpected(*args):
        pytest.fail("Startup must not emit events or contact a backend")

    manager = TransferManager(state, unexpected, unexpected)
    try:
        assert set(root.glob("*.json")) == set(kept)
        for path, contents in kept.items():
            assert path.read_bytes() == contents
        assert (root / (f"{4:032x}" + ".lock")).read_bytes() == b"existing lock"
        assert not any((root / (f"{index:032x}" + ".lock")).exists() for index in (1, 2, 3))
        assert manager.threads == {}
        assert manager.resume_interrupted() == []
    finally:
        manager.stop()


@pytest.mark.parametrize("kind", ["runtime", "hub"])
@pytest.mark.parametrize("source_kind", ["file", "folder"])
@pytest.mark.parametrize("remote", [None, ".", "./", "nested//./input"])
def test_upload_start_reuses_the_original_request_across_states_and_restart(tmp_path, monkeypatch, kind,
                                                                          source_kind, remote):
    source = tmp_path / "input"
    if source_kind == "file":
        source.write_text("one upload", encoding="utf-8")
    else:
        source.mkdir()
        (source / "data.txt").write_text("one upload", encoding="utf-8")
    state = tmp_path / "state"
    launches = []
    manager = TransferManager(state, lambda *args: None, lambda *args: SimpleNamespace(kind=kind, server_key=f"{kind}:test"))
    monkeypatch.setattr(manager, "_launch", launches.append)
    restarted = None
    params = {"connection": kind + ":test", "workspace_id": "workspace", "source": source,
              "remote": remote, "node": "node" if kind == "hub" else None, "idempotency_key": "upload-once"}
    try:
        first = manager.start_upload(**params)
        record = manager.load(first["id"])
        expected_path = "nested/input" if remote == "nested//./input" else "input"
        if source_kind == "folder":
            expected_path = ("" if remote in (".", "./") else expected_path + "/") + "data.txt"
        assert [item["remote"] for item in record["items"]] == [expected_path]
        for state_name in ("queued", "running", "completed", "failed", "cancelled", "interrupted"):
            record["state"] = state_name
            manager.save(record)
            repeated = manager.start_upload(**params)
            assert repeated["id"] == first["id"] and repeated["state"] == state_name
            assert launches == [first["id"]]
        # The key names the accepted request even after its original source has moved.
        source.rename(tmp_path / "moved-input")
        record["state"] = "queued"
        manager.save(record)
        manager.stop()
        restarted = TransferManager(state, lambda *args: None, lambda *args: SimpleNamespace(kind=kind, server_key=f"{kind}:test"))
        monkeypatch.setattr(restarted, "_launch", launches.append)
        repeated = restarted.start_upload(**params)
        assert repeated["id"] == first["id"] and repeated["state"] == "interrupted"
        assert launches == [first["id"]]
    finally:
        manager.stop()
        if restarted is not None:
            restarted.stop()


@pytest.mark.parametrize("kind", ["runtime", "hub"])
def test_upload_start_same_key_keeps_raw_request_identity(tmp_path, monkeypatch, kind):
    source = tmp_path / "input.txt"
    source.write_text("one upload", encoding="utf-8")
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind=kind, server_key=f"{kind}:test"))
    launches = []
    monkeypatch.setattr(manager, "_launch", launches.append)
    params = {"connection": kind + ":test", "workspace_id": "workspace", "source": source,
              "remote": None, "node": "node" if kind == "hub" else None, "idempotency_key": "upload-once"}
    try:
        first = manager.start_upload(**params)
        assert manager.start_upload(**{**params, "source": str(source)})["id"] == first["id"]
        # Effective destination aliases are different client requests under an already used key.
        # Do not reconstruct the original request from normalized item paths or public fields.
        changes = ({"connection": kind + ":other"}, {"node": "other"}, {"workspace_id": "other"},
                   {"source": str(source.parent) + "/./" + source.name},
                   {"remote": source.name}, {"remote": "."}, {"remote": "./"})
        for change in changes:
            with pytest.raises(BridgeError) as error:
                manager.start_upload(**{**params, **change})
            assert error.value.code == "conflict"
            assert error.value.data == {"transfer_id": first["id"]}
        assert launches == [first["id"]]
    finally:
        manager.stop()


@pytest.mark.parametrize("kind", ["runtime", "hub"])
def test_concurrent_upload_start_with_the_same_key_launches_once(tmp_path, monkeypatch, kind):
    source = tmp_path / "input.txt"
    source.write_text("one upload", encoding="utf-8")
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind=kind, server_key=f"{kind}:test"))
    launches = []
    monkeypatch.setattr(manager, "_launch", launches.append)
    params = {"connection": kind + ":test", "workspace_id": "workspace", "source": source,
              "node": "node" if kind == "hub" else None, "idempotency_key": "upload-once"}
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: manager.start_upload(**params), range(4)))
        assert {result["id"] for result in results} == {launches[0]}
        assert len(launches) == 1
        assert len(manager.list()) == 1
    finally:
        manager.stop()


def test_hub_import_budget_is_checked_before_creating_or_launching_a_transfer(tmp_path, monkeypatch):
    source = tmp_path / "inputs"
    source.mkdir()
    for index in range(8):
        (source / (str(index) + "-" + "x" * 40 + ".txt")).write_text("input", encoding="utf-8")
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind="hub", server_key="hub:test"))
    launches = []
    monkeypatch.setattr(manager, "_launch", launches.append)
    monkeypatch.setattr(transfers, "IMPORT_REQUEST_BYTES", 512)
    try:
        with pytest.raises(BridgeError) as error:
            manager.start_upload("hub:test", "workspace", source, node="node", idempotency_key="upload-once")
        assert error.value.code == "invalid_params" and "import request limit" in error.value.message
        assert manager.list() == [] and launches == []
    finally:
        manager.stop()


def test_an_old_hub_journal_with_no_original_request_keeps_a_key_conflict(tmp_path, monkeypatch):
    source = tmp_path / "input.txt"
    source.write_text("one upload", encoding="utf-8")
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind="hub", server_key="hub:test"))
    launches = []
    monkeypatch.setattr(manager, "_launch", launches.append)
    params = {"connection": "hub:test", "workspace_id": "workspace", "source": source,
              "node": "node", "idempotency_key": "upload-once"}
    try:
        first = manager.start_upload(**params)
        record = manager.load(first["id"])
        # Old Hub journals lost remote=None versus explicit basename/root intent. Their
        # normalized item paths cannot prove which original client request used the key.
        old_request = {"id": "0" * 32, "node_id": "0" * 32, "kind": "workspace.import", "payload": {
            "workspace_id": "workspace", "files": [{"path": "input.txt", "sha256": "0" * 64,
                                                       "size": source.stat().st_size}]}}
        record.update(request=old_request, state="completed")
        manager.save(record)
        for remote in (None, "input.txt", ".", "./"):
            with pytest.raises(BridgeError) as error:
                manager.start_upload(**{**params, "remote": remote})
            assert error.value.code == "conflict"
            assert error.value.data == {"transfer_id": first["id"]}
        assert manager.resume(first["id"])["state"] == "completed"
        assert manager.load(first["id"])["request"] == old_request
        assert launches == [first["id"]]
    finally:
        manager.stop()


def test_resume_after_failure_event_waits_for_old_worker_and_restarts(tmp_path, monkeypatch):
    failed, release, observed = (threading.Event() for _ in range(3))
    attempts = []

    def emit(event, data):
        if data["transfer"]["state"] == "failed":
            failed.set()
            assert release.wait(10)

    manager = TransferManager(tmp_path / "state", emit, lambda *args: SimpleNamespace(kind="runtime", server_key="runtime:test"))

    def download(record, backend):
        attempts.append(record["id"])
        if len(attempts) == 1:
            raise BridgeError("unavailable", "Simulated network loss")
        record.update(bytes_done=3, bytes_total=3, files_done=1)

    monkeypatch.setattr(manager, "_download", download)
    try:
        transfer = manager.start_download("local", "workspace", "workspace", "file", tmp_path / "file")
        assert failed.wait(10)
        old = manager.threads[transfer["id"]]
        is_alive = old.is_alive

        def report_alive():
            alive = is_alive()
            observed.set()
            return alive

        monkeypatch.setattr(old, "is_alive", report_alive)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(manager.resume, transfer["id"])
            try:
                # Capture the actual live-thread observation; no timing-based sleep is needed.
                assert observed.wait(5)
            finally:
                release.set()
            resumed = pending.result(timeout=10)
        assert resumed["state"] in {"queued", "running", "completed"}
        current = manager.threads[transfer["id"]]
        assert current is not old
        current.join(timeout=10)
        assert not current.is_alive()
        assert attempts == [transfer["id"], transfer["id"]]
        assert manager.load(transfer["id"])["state"] == "completed"
        assert manager.resume(transfer["id"])["state"] == "completed"
        assert len(attempts) == 2
    finally:
        release.set()
        manager.stop()


def test_cancel_after_transfer_worker_retires_preserves_completed_download(tmp_path, monkeypatch):
    downloading, finish_download, cancel_at_lock, allow_cancel = (threading.Event() for _ in range(4))
    body = b"synthetic download"
    states = []

    def read_chunk(owner, owner_id, path, offset):
        assert (owner, owner_id, path, offset) == ("workspace", "workspace", "file.dat", 0)
        downloading.set()
        assert finish_download.wait(10), "test did not release the download"
        return body

    backend = SimpleNamespace(kind="runtime", server_key="runtime:test", read_chunk=read_chunk,
                              describe=lambda *args: {"path": "file.dat", "size": len(body),
                                                      "sha256": hashlib.sha256(body).hexdigest()})

    def emit(event, data):
        states.append(data["transfer"]["state"])

    manager = TransferManager(tmp_path / "state", emit, lambda *args: backend)
    lock = manager.lock

    class GateCancelLock:
        def __enter__(self):
            if threading.current_thread().name.startswith("test-cancel"):
                cancel_at_lock.set()
                assert allow_cancel.wait(10), "test did not release the cancellation"
            return lock.__enter__()

        def __exit__(self, *args):
            return lock.__exit__(*args)

    monkeypatch.setattr(manager, "lock", GateCancelLock())
    destination = tmp_path / "download.dat"
    try:
        transfer = manager.start_download("local", "workspace", "workspace", "file.dat", destination)
        transfer_id = transfer["id"]
        assert downloading.wait(5)
        worker = manager.threads[transfer_id]
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-cancel") as pool:
            cancellation = pool.submit(manager.cancel, transfer_id)
            try:
                assert cancel_at_lock.wait(5)
                finish_download.set()
                worker.join(timeout=5)
                assert not worker.is_alive()
                assert destination.read_bytes() == body
                assert manager.load(transfer_id)["state"] == "completed"
                journal = manager.root / (transfer_id + ".json")
                completed_bytes = journal.read_bytes()
                completed_events = list(states)
                assert completed_events[-1] == "completed"
            finally:
                finish_download.set()
                allow_cancel.set()
            result = cancellation.result(timeout=5)
        assert result["state"] == "completed"
        assert journal.read_bytes() == completed_bytes
        assert destination.read_bytes() == body
        assert states == completed_events
    finally:
        finish_download.set()
        allow_cancel.set()
        manager.stop()
