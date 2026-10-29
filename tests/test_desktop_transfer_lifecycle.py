"""Deterministic transfer handoff between a published terminal state and worker cleanup."""

from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.transfers import TransferManager
import suan.desktop_bridge.transfers as transfers


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
    manager = TransferManager(state, lambda *args: None, lambda *args: SimpleNamespace(kind=kind))
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
        restarted = TransferManager(state, lambda *args: None, lambda *args: SimpleNamespace(kind=kind))
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
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind=kind))
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
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind=kind))
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
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind="hub"))
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
    manager = TransferManager(tmp_path / "state", lambda *args: None, lambda *args: SimpleNamespace(kind="hub"))
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

    manager = TransferManager(tmp_path / "state", emit, lambda *args: SimpleNamespace(kind="runtime"))

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
