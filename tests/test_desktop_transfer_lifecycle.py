"""Deterministic transfer handoff between a published terminal state and worker cleanup."""

from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.transfers import TransferManager


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
