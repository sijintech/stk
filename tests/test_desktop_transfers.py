"""Transfer retry ordering at the terminal-event/worker-cleanup boundary."""
import threading
from types import SimpleNamespace

import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.transfers import TransferManager


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_resume_during_terminal_event_is_not_lost(tmp_path, monkeypatch, terminal):
    announced = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    attempts = []

    def emit(event, data):
        state = data["transfer"]["state"]
        if state == terminal:
            announced.set()
            assert release.wait(10), "test did not release the terminal notification"
        elif state == "completed":
            completed.set()

    manager = TransferManager(tmp_path, emit, lambda *_: SimpleNamespace(kind="runtime"))

    def upload(record, backend):
        attempts.append(record["id"])
        if len(attempts) == 1:
            if terminal == "cancelled":
                manager.cancelled.add(record["id"])
                manager._check(record["id"])
            raise BridgeError("unavailable", "simulated connection drop")

    monkeypatch.setattr(manager, "_upload", upload)
    source = tmp_path / "source.dat"
    source.write_bytes(b"resumable")
    try:
        transfer = manager.start_upload("test", "workspace", source)
        assert announced.wait(10)
        # The failed/cancelled event has reached the client, but its worker is
        # still alive and holds the journal lock. Immediate and repeated retries
        # must queue exactly one new attempt, without colliding with that lock.
        first = manager.resume(transfer["id"])
        second = manager.resume(transfer["id"])
        assert first["state"] == second["state"] == "queued"
        release.set()
        assert completed.wait(10)
        assert attempts == [transfer["id"], transfer["id"]]
        assert manager.load(transfer["id"])["state"] == "completed"
        assert manager.resume(transfer["id"])["state"] == "completed"
    finally:
        release.set()
        manager.stop()


@pytest.mark.parametrize("followup", ["cancel", "stop"])
def test_pending_retry_can_be_cancelled_or_interrupted(tmp_path, monkeypatch, followup):
    announced = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    attempts = []

    def emit(event, data):
        if data["transfer"]["state"] == "failed":
            announced.set()
            assert release.wait(10)
        elif data["transfer"]["state"] == "completed":
            completed.set()

    backend_for = lambda *_: SimpleNamespace(kind="runtime")
    manager = TransferManager(tmp_path, emit, backend_for)

    def upload(record, backend):
        attempts.append(record["id"])
        if len(attempts) == 1:
            raise BridgeError("unavailable", "simulated connection drop")

    monkeypatch.setattr(manager, "_upload", upload)
    source = tmp_path / "source.dat"
    source.write_bytes(b"resumable")
    try:
        transfer = manager.start_upload("test", "workspace", source)
        transfer_id = transfer["id"]
        assert announced.wait(10)
        assert manager.resume(transfer_id)["state"] == "queued"
        worker = manager.threads[transfer_id]
        join = worker.join

        def release_and_join(*args, **kwargs):
            # cancel/stop has signalled the worker by the time it joins it.
            release.set()
            return join(*args, **kwargs)

        monkeypatch.setattr(worker, "join", release_and_join)
        if followup == "cancel":
            assert manager.cancel(transfer_id)["state"] == "cancelled"
        else:
            manager.stop()
            assert manager.load(transfer_id)["state"] == "queued"
        assert attempts == [transfer_id]
        assert not manager.threads and not manager.resuming and not manager.releasers
        if followup == "stop":
            restarted = TransferManager(tmp_path, emit, backend_for)
            monkeypatch.setattr(restarted, "_upload", upload)
            try:
                assert restarted.load(transfer_id)["state"] == "interrupted"
                assert restarted.resume_interrupted() == [transfer_id]
                assert completed.wait(10)
            finally:
                restarted.stop()
            assert attempts == [transfer_id, transfer_id]
    finally:
        release.set()
        manager.stop()
