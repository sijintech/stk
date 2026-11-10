"""The bridge namespace stays owned until its admitted transfer writers really exit."""

import threading
from types import SimpleNamespace

import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.server import Bridge, StateDirLock
from suan.desktop_bridge.transfers import TransferManager


def bridge_with_transfers(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    bridge = Bridge.__new__(Bridge)
    bridge.closing, bridge.closed = threading.Event(), threading.Event()
    bridge._literature_lock = threading.Lock()
    bridge._materials_lock = threading.Lock()
    bridge._literature = bridge._materials = None
    bridge._mupro_preflight, bridge._mupro_preflight_lock = None, threading.RLock()
    bridge.inflight_lock, bridge.inflight = threading.Lock(), set()
    noop = lambda *args, **kwargs: None
    bridge.peers = bridge.modules = bridge.projects = SimpleNamespace(shutdown=noop)
    bridge.workflow_executor = bridge.analysis_executor = SimpleNamespace(shutdown=noop)
    bridge.ui = bridge.connections = SimpleNamespace(close=noop)
    bridge.scripts = SimpleNamespace(shutdown=noop)
    bridge.subscriptions = SimpleNamespace(stop_all=noop)
    bridge.graphs = SimpleNamespace(cancel_all=noop)
    bridge.state_lock = StateDirLock(state)
    manager = TransferManager(state, noop, lambda *args: SimpleNamespace(kind="runtime", server_key="local:test"))
    bridge.transfers = manager
    released = threading.Event()
    actual_release = bridge.state_lock.release

    def release():
        actual_release()
        released.set()

    bridge.state_lock.release = release
    return state, bridge, manager, released


def assert_busy(state):
    with pytest.raises(BridgeError) as error:
        unexpected = StateDirLock(state)
        unexpected.release()
    assert error.value.code == "busy"


def test_shutdown_keeps_namespace_until_running_transfer_has_exited(tmp_path, monkeypatch):
    state, bridge, manager, released = bridge_with_transfers(tmp_path)
    entered, proceed = threading.Event(), threading.Event()
    source = tmp_path / "public-input.txt"
    source.write_text("public fixture", encoding="utf-8")

    def upload(record, backend):
        entered.set()
        assert proceed.wait(10)
        # Simulate the last journal write after a bounded stop has returned.
        record.update(bytes_done=source.stat().st_size, files_done=1)

    monkeypatch.setattr(manager, "_upload", upload)
    try:
        transfer = manager.start_upload("local", "workspace", source)
        assert entered.wait(5)
        worker = manager.threads[transfer["id"]]
        bridge.shutdown(grace=0)
        assert bridge.closed.is_set() and worker.is_alive()
        assert_busy(state)
        assert not released.is_set()
        proceed.set()
        assert released.wait(5)
        assert not worker.is_alive()
        with_lock = StateDirLock(state)
        try:
            restarted = TransferManager(state, lambda *args: None, manager.backend_for)
            try:
                assert restarted.load(transfer["id"])["state"] == "completed"
            finally:
                restarted.stop()
        finally:
            with_lock.release()
    finally:
        proceed.set()
        manager.stop()
        bridge.state_lock.release()


def test_shutdown_keeps_namespace_during_admitted_source_preparation(tmp_path, monkeypatch):
    state, bridge, manager, released = bridge_with_transfers(tmp_path)
    entered, proceed, finished = (threading.Event() for _ in range(3))
    source = tmp_path / "public-input.txt"
    source.write_text("public fixture", encoding="utf-8")
    actual_item = manager._upload_item
    errors = []

    def prepare(*args):
        entered.set()
        assert proceed.wait(10)
        return actual_item(*args)

    def start():
        try:
            manager.start_upload("local", "workspace", source)
        except BridgeError as error:
            errors.append(error.code)
        finally:
            finished.set()

    monkeypatch.setattr(manager, "_upload_item", prepare)
    caller = threading.Thread(target=start)
    caller.start()
    try:
        assert entered.wait(5)
        bridge.shutdown(grace=0)
        assert_busy(state)
        assert not released.is_set()
        proceed.set()
        assert finished.wait(5) and released.wait(5)
        caller.join(5)
        assert errors == ["shutting_down"]
        assert not manager.threads
    finally:
        proceed.set()
        caller.join(10)
        manager.stop()
        bridge.state_lock.release()


@pytest.mark.parametrize("operation", ["upload", "download", "resume", "cancel"])
def test_stop_closes_transfer_write_admission_without_new_io(tmp_path, operation):
    manager = TransferManager(tmp_path / "state", lambda *args: None,
                              lambda *args: pytest.fail("No backend lookup after stop"))
    before = {p.name: p.read_bytes() for p in manager.root.iterdir()}
    manager.stop(timeout=0)
    calls = {
        "upload": lambda: manager.start_upload("local", "workspace", tmp_path / "missing"),
        "download": lambda: manager.start_download("local", "workspace", "workspace", "file", tmp_path / "out"),
        "resume": lambda: manager.resume("0" * 32),
        "cancel": lambda: manager.cancel("0" * 32),
    }
    with pytest.raises(BridgeError) as error:
        calls[operation]()
    assert error.value.code == "shutting_down"
    assert {p.name: p.read_bytes() for p in manager.root.iterdir()} == before


def test_failed_worker_start_does_not_hold_namespace_forever(tmp_path, monkeypatch):
    state, bridge, manager, released = bridge_with_transfers(tmp_path)
    source = tmp_path / "public-input.txt"
    source.write_text("public fixture", encoding="utf-8")

    def fail_start(thread):
        raise RuntimeError("controlled thread start failure")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    try:
        with pytest.raises(RuntimeError, match="controlled thread start failure"):
            manager.start_upload("local", "workspace", source)
        bridge.shutdown(grace=0)
        assert released.is_set()
        assert not manager.threads
        available = StateDirLock(state)
        available.release()
    finally:
        bridge.state_lock.release()


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_interrupted_start_retains_a_worker_that_already_started(tmp_path, monkeypatch, failure):
    state, bridge, manager, released = bridge_with_transfers(tmp_path)
    source = tmp_path / "public-input.txt"
    source.write_text("public fixture", encoding="utf-8")
    entered, proceed = threading.Event(), threading.Event()
    actual_start = threading.Thread.start

    def upload(record, backend):
        entered.set()
        assert proceed.wait(10)

    def interrupted_start(thread):
        actual_start(thread)
        if thread.name.startswith("stk-transfer-"):
            raise failure("interrupted after native thread creation")

    monkeypatch.setattr(manager, "_upload", upload)
    monkeypatch.setattr(threading.Thread, "start", interrupted_start)
    try:
        with pytest.raises(failure):
            manager.start_upload("local", "workspace", source)
        assert entered.wait(5)
        bridge.shutdown(grace=0)
        assert_busy(state)
        assert not released.is_set()
        proceed.set()
        assert released.wait(5)
        assert all(not worker.is_alive() for worker in manager.threads.values())
    finally:
        proceed.set()
        manager.stop()
        bridge.state_lock.release()
