"""Desktop-only peer owner actions, passive reopening and actual helper wiring."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
from uuid import uuid4

import pytest

from test_desktop_bridge import InProcessBridge, ProcessBridge, BridgeCallError
from suan.desktop_bridge.peer import PeerService, METHODS, request_sha256
from suan.peer.authority import PeerAuthority
from suan.peer.identity import LocalDeviceIdentity


def uid():
    return str(uuid4())


def test_original_hash_keeps_types_negative_zero_optional_presence_and_signal_digest():
    params = {"operation_id": "00000000-0000-0000-0000-000000000001", "timeout": 1}
    assert request_sha256("files.send", params) != request_sha256("files.send", {**params, "timeout": 1.0})
    assert request_sha256("files.send", {**params, "timeout": -0.0}) != request_sha256("files.send", {**params, "timeout": 0.0})
    assert request_sha256("files.send", params) != request_sha256("files.send", {**params, "resume": None})
    signal = {"operation_id": params["operation_id"], "connection_id": params["operation_id"], "signal_text": "ephemeral test"}
    reduced = {**signal, "signal_text": hashlib.sha256(signal["signal_text"].encode()).hexdigest()}
    encoded = json.dumps({"action": "connections.push_signal", "params": reduced}, sort_keys=True,
                         ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    assert request_sha256("connections.push_signal", signal) == hashlib.sha256(encoded).hexdigest()


def call(bridge, method, params=None):
    response = bridge.response(bridge.request(method, params))
    if "error" in response:
        raise BridgeCallError(response["error"])
    return response["result"]


def initialize(bridge, name):
    result = call(bridge, "peer.identity.initialize", {"operation_id": uid(), "display_name": name})
    assert result["operation"]["state"] == "completed"
    return result["operation"]["result"]["result"]


def wait_operation(bridge, operation_id, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = call(bridge, "peer.operations.get", {"operation_id": operation_id})["operation"]
        if result["state"] != "running":
            return result
        time.sleep(.02)
    pytest.fail("Explicit peer action did not finish within its test deadline")


def test_construct_info_and_absent_pages_do_not_initialize_identity_authority_or_helper(tmp_path, monkeypatch):
    def forbidden(*_, **__):
        pytest.fail("Passive observation started or constructed an Authority/helper")
    monkeypatch.setattr("suan.desktop_bridge.peer.PeerAuthority", forbidden)
    monkeypatch.setattr("suan.desktop_bridge.peer.NativeTransport", forbidden)
    service = PeerService(tmp_path / "state", None)
    assert service.call("info", {}) == {"identity": None, "connections": []}
    assert service.call("pins.list", {}) == {"pins": []}
    assert service.call("sessions.list", {}) == {"sessions": []}
    assert service.call("files.list", {"role": "receiver"}) == {"transfers": []}
    assert service.call("operations.list", {}) == {"operations": []}
    assert not (tmp_path / "state").exists()
    service.shutdown()


BLOCK_NUMPY = '''
import importlib.abc, sys
class RefuseNumPy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy' or fullname.startswith('numpy.'):
            raise ModuleNotFoundError('NumPy is absent in this startup proof', name='numpy')
sys.meta_path.insert(0, RefuseNumPy())
'''


def test_real_bridge_construction_and_shutdown_without_numpy_never_builds_materials(tmp_path):
    code = BLOCK_NUMPY + '''
import io
from pathlib import Path
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.protocol import BridgeError
root = Path(sys.argv[1])
bridge = Bridge(root, writer=io.BytesIO(), strict=True)
assert bridge._materials is None
assert bridge.peers.call('info', {}) == {'identity':None, 'connections':[]}
try:
    bridge.materials_call('jobs', {})
except BridgeError as error:
    assert error.code == 'unsupported'
else:
    raise AssertionError('Missing scientific dependency was not classified')
assert bridge._materials is None
bridge.shutdown()
assert not (root/'materials').exists() and not (root/'peer').exists()
assert 'numpy' not in sys.modules
'''
    env = dict(os.environ, STK_PROFILES_FILE=str(tmp_path / "profiles"), STK_STATE_DIR=str(tmp_path / "runtime"))
    subprocess.run([sys.executable, "-c", code, str(tmp_path / "state")], env=env,
                   check=True, capture_output=True, timeout=20)


def test_actual_stdio_peer_info_materials_unavailable_and_shutdown_without_numpy(tmp_path):
    code = BLOCK_NUMPY + '''
from suan.desktop_bridge.__main__ import main
main(['--stdio','--strict','--state-dir',sys.argv[1]])
'''
    bridge = ProcessBridge(tmp_path / "state", argv=[sys.executable, "-c", code, str(tmp_path / "state")])
    try:
        assert call(bridge, "peer.info") == {"identity": None, "connections": []}
        with pytest.raises(BridgeCallError) as error:
            call(bridge, "materials.jobs.list")
        assert error.value.code == "unsupported"
        assert call(bridge, "peer.info")["identity"] is None
        assert call(bridge, "shutdown") == {"ok": True}
        assert bridge.process.wait(timeout=10) == 0
    finally:
        bridge.close()
    assert not (tmp_path / "state/materials").exists()
    assert not (tmp_path / "state/peer").exists()


def test_authority_existing_open_is_read_only_and_missing_open_never_creates(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        PeerAuthority(tmp_path / "absent", owner_id=uid(), create=False)
    assert not (tmp_path / "absent").exists()
    owner = uid()
    authority = PeerAuthority(tmp_path / "authority", owner_id=owner)
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in authority.directory.iterdir()}
    import suan.peer.authority as module
    connect = module.sqlite3.connect
    modes = []
    def observe(path, **kwargs):
        modes.append(path)
        return connect(path, **kwargs)
    monkeypatch.setattr(module.sqlite3, "connect", observe)
    reopened = PeerAuthority(authority.directory, owner_id=owner, create=False)
    assert reopened.owner_id == owner and modes and all("?mode=ro" in p for p in modes)
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
             for p in authority.directory.iterdir()}
    assert before == after


def test_desktop_schema_registration_and_scripts_never_expose_peer_operations(tmp_path):
    from suan.agent.levels import DESKTOP_ONLY, OPERATIONS, TOOL_USES
    from suan.desktop_bridge import schema
    bridge = InProcessBridge(tmp_path / "state")
    try:
        names = {"project.peer.files.prepare" if a == "files.prepare" else "peer." + a for a in METHODS}
        assert names <= set(schema.method_names()) & set(bridge.bridge.methods) & set(DESKTOP_ONLY)
        assert not names & set(OPERATIONS)
        assert not names & set().union(*map(set, TOOL_USES.values()))
        assert not names & set(bridge.bridge.script_catalog()["operations"])
        assert call(bridge, "peer.info") == {"identity": None, "connections": []}
        for name in names:
            with pytest.raises(Exception):
                bridge.bridge.script_call(name, {})
        assert not (bridge.bridge.state_dir / "peer").exists()
    finally:
        bridge.close()


def test_identity_original_receipt_reopen_and_full_owner_pin_binding(tmp_path):
    bridges = [InProcessBridge(tmp_path / name) for name in ("first", "second")]
    try:
        first, second = bridges
        params = {"operation_id": uid(), "display_name": "First device"}
        original = call(first, "peer.identity.initialize", params)
        assert original["operation"]["request_sha256"] == request_sha256("identity.initialize", params)
        assert call(first, "peer.identity.initialize", params) == original
        with pytest.raises(BridgeCallError) as error:
            call(first, "peer.identity.initialize", {**params, "display_name": "Different request"})
        assert error.value.code == "conflict"
        remote = initialize(second, "Second device")["card"]
        pin_params = {"operation_id": uid(), "card": remote, "expected_peer_id": remote["peer_id"]}
        verified = call(first, "peer.pins.verify", pin_params)
        assert verified["operation"]["state"] == "completed"
        substituted = {**remote, "owner_id": uid()}
        denied = call(first, "peer.pins.verify", {**pin_params, "operation_id": uid(), "card": substituted})
        assert denied["operation"]["state"] == "uncertain"
        card = call(first, "peer.pins.list")["pins"][0]["card"]
        assert card == remote
        first.close();bridges.remove(first)
        reopened = InProcessBridge(tmp_path / "first");bridges.append(reopened)
        assert call(reopened, "peer.operations.get", {"operation_id": params["operation_id"]}) == original
        assert call(reopened, "peer.info")["connections"] == []
        assert call(reopened, "peer.pins.list")["pins"][0]["card"] == remote
    finally:
        for bridge in bridges:bridge.close()


def test_unfinished_intent_reopen_is_observation_never_autoqueue(tmp_path, monkeypatch):
    root = tmp_path / "state"
    service = PeerService(root, None)
    operation_id = uid()
    # A process stopping after FULL admission but before identity key generation.
    params = {"operation_id": operation_id, "display_name": "Not generated"}
    row, fresh = service._reserve("identity.initialize", params)
    assert fresh and row["state"] == "running"
    before = service.path.read_bytes()
    reopened = PeerService(root, None)
    def forbidden(*_, **__):pytest.fail("Old intent was executed again")
    monkeypatch.setattr(reopened, "_mutate", forbidden)
    observed = reopened.call("operations.get", {"operation_id": operation_id})
    assert observed["operation"]["state"] == "uncertain"
    assert reopened.call("identity.initialize", params) == observed
    assert before == service.path.read_bytes()
    assert not (root / "device").exists()
    service.shutdown();reopened.shutdown()


@pytest.mark.parametrize("fault", ["before_authority", "outer_receipt"])
def test_explicit_identity_recovery_adopts_exact_committed_key_without_regeneration(tmp_path, monkeypatch, fault):
    bridge = InProcessBridge(tmp_path / "state")
    try:
        service = bridge.bridge.peers
        operation_id = uid()
        with monkeypatch.context() as patch:
            if fault == "before_authority":
                def fail(*_, **__):raise OSError("Synthetic Authority initialization fault")
                patch.setattr("suan.desktop_bridge.peer.PeerAuthority", fail)
            else:
                def fail(*_, **__):raise OSError("Synthetic outer receipt fault")
                patch.setattr(service, "_finish", fail)
            result = call(bridge, "peer.identity.initialize", {"operation_id": operation_id, "display_name": "Recover exact"})
        assert result["operation"]["state"] == "uncertain"
        public = service.identity.info()
        domain = service.identity.operation(operation_id)
        assert domain["result"] == public
        def no_keygen(*_, **__):pytest.fail("Recovery replayed identity lifecycle")
        for name in ("initialize", "rotate", "revoke"):
            monkeypatch.setattr(service.identity, name, no_keygen)
        recovered = call(bridge, "peer.identity.recover", {"operation_id": uid(), "original_operation_id": operation_id})["operation"]
        assert recovered["state"] == "completed" and recovered["result"]["identity"] == public
        assert service.identity.info() == public
        assert service._services()[0].owner_id == public["card"]["owner_id"]
        original = call(bridge, "peer.operations.get", {"operation_id": operation_id})["operation"]
        assert original["state"] == "completed" and original["result"] == domain
    finally:
        bridge.close()


def test_identity_recovery_rejects_newer_generation_and_does_not_close_it(tmp_path, monkeypatch):
    bridge = InProcessBridge(tmp_path / "state")
    try:
        public = initialize(bridge, "Generation fences")
        service = bridge.bridge.peers
        with monkeypatch.context() as patch:
            patch.setattr(service, "_finish", lambda *_, **__: (_ for _ in ()).throw(OSError("Synthetic outer receipt fault")))
            old_id = uid()
            call(bridge, "peer.identity.rotate", {"operation_id": old_id, "expected_generation": public["generation"]})
        newer = call(bridge, "peer.identity.rotate", {"operation_id": uid(), "expected_generation": public["generation"] + 1})
        assert newer["operation"]["state"] == "completed"
        monkeypatch.setattr(service, "_close_connections", lambda **_: pytest.fail("Old recovery closed newer-generation connections"))
        result = call(bridge, "peer.identity.recover", {"operation_id": uid(), "original_operation_id": old_id})
        assert result["operation"]["state"] == "uncertain"
        assert call(bridge, "peer.operations.get", {"operation_id": old_id})["operation"]["state"] == "uncertain"
    finally:
        monkeypatch.undo()
        bridge.close()


def test_shutdown_cannot_miss_a_connection_open_blocked_in_installation_check(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    import suan.peer.helper_installation as installation
    bridges = [InProcessBridge(tmp_path / name) for name in ("first", "second")]
    entered, release = threading.Event(), threading.Event()
    try:
        for b in bridges:initialize(b, "Device")
        first, second = bridges
        remote = call(second, "peer.info")["identity"]["card"]
        call(first, "peer.pins.verify", {"operation_id": uid(), "card": remote, "expected_peer_id": remote["peer_id"]})
        def blocked(*_, **__):
            entered.set();assert release.wait(5)
            return SimpleNamespace(executable=tmp_path / "never-started")
        monkeypatch.setattr(installation, "load_helper_installation", blocked)
        monkeypatch.setattr("suan.desktop_bridge.peer.NativeTransport", lambda *_, **__: pytest.fail("Helper started after shutdown"))
        service = first.bridge.peers
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(service.call, "connections.open", {"operation_id": uid(), "peer_id": remote["peer_id"],
                                 "helper_prefix": str(tmp_path), "offerer": True, "route": "udp"})
            assert entered.wait(5)
            service.shutdown();release.set()
            assert future.result(timeout=5)["operation"]["state"] == "uncertain"
        assert service._connections == {}
    finally:
        release.set()
        for b in bridges:b.close()


def test_signal_hash_never_keeps_raw_signal_in_original_journal_or_errors(tmp_path, capsys):
    service = PeerService(tmp_path, None)
    marker = "ephemeral-signal-marker"
    params = {"operation_id": uid(), "connection_id": uid(), "signal_text": marker}
    result = service.call("connections.push_signal", params)
    assert result["operation"]["state"] == "uncertain"
    assert marker.encode() not in service.path.read_bytes()
    assert marker not in json.dumps(result)
    assert marker not in capsys.readouterr().err
    service.shutdown()


class MetadataOnlyTransport:
    """Cleanup-only synthetic connection row: never authentication evidence."""
    def close(self):
        pass


def admission_service(tmp_path):
    """Real persistent identity, full pin and journal; no ready channel/context."""
    service = PeerService(tmp_path / "bridge", None)
    initialized = service.call("identity.initialize", {"operation_id": uid(), "display_name": "Admission fault test"})
    assert initialized["operation"]["state"] == "completed"
    card = LocalDeviceIdentity(tmp_path / "remote").initialize(uid(), "Isolated remote public pin")["result"]["card"]
    verified = service.call("pins.verify", {"operation_id": uid(), "card": card, "expected_peer_id": card["peer_id"]})
    assert verified["operation"]["state"] == "completed"
    connection_id = uid()
    service._connections[connection_id] = {"connection_id": connection_id, "peer_id": card["peer_id"],
        "state": "signaling", "error": None, "pin": card, "endpoint": None, "transport": MetadataOnlyTransport(),
        "identity_generation": service.identity.info()["generation"]}
    return service, connection_id


class RejectingExecutor:
    def __init__(self, **_):
        self.submissions = 0
    def submit(self, *_, **__):
        self.submissions += 1
        raise RuntimeError("Synthetic executor rejected submission")
    def shutdown(self, **_):
        pass


@pytest.mark.parametrize("fault", ["constructor", "submit"])
def test_executor_admission_failure_retains_uncertainty_without_leaking_capacity(tmp_path, monkeypatch, fault):
    service, connection_id = admission_service(tmp_path)
    attempts = []
    def factory(**kwargs):
        attempts.append("constructor")
        if fault == "constructor":
            raise RuntimeError("Synthetic executor creation failure")
        return RejectingExecutor(**kwargs)
    monkeypatch.setattr("suan.desktop_bridge.peer.ThreadPoolExecutor", factory)
    try:
        for _ in range(3):
            params = {"operation_id": uid(), "connection_id": connection_id}
            result = service.call("connections.authenticate", params)
            op = result["operation"]
            assert op["state"] == "uncertain" and op["result"] is None and op["error"]["code"] == "unavailable"
            assert not service._running
            with service._db() as db:
                assert service._get(db, params["operation_id"])["state"] == "uncertain"
            before = len(attempts), 0 if service._pool is None else service._pool.submissions
            assert service.call("connections.authenticate", params) == result
            assert before == (len(attempts), 0 if service._pool is None else service._pool.submissions)
        assert service._connections[connection_id]["endpoint"] is None
    finally:
        service.shutdown()


def test_real_executor_item_queued_before_thread_start_failure_never_executes_after_rejection(tmp_path, monkeypatch):
    service, connection_id = admission_service(tmp_path)
    pool = RealThreadPoolExecutor(max_workers=2)
    service._pool = pool
    effects = []
    monkeypatch.setattr(service, "_mutate", lambda *_, **__: effects.append("unexpected business action"))
    params = {"operation_id": uid(), "connection_id": connection_id}
    try:
        with monkeypatch.context() as patch:
            def refuse_thread():
                raise RuntimeError("Synthetic failure while starting a thread")
            patch.setattr(pool, "_adjust_thread_count", refuse_thread)
            result = service.call("connections.authenticate", params)
        assert result["operation"]["state"] == "uncertain" and not service._running
        assert not pool._work_queue.empty() and not pool._threads
        # A real worker now drains the retained dispatcher before this sentinel.
        # This is queue-order evidence, not an authenticated peer/helper fixture.
        assert pool.submit(lambda: "queue drained").result(timeout=5) == "queue drained"
        assert effects == []
        assert service.call("operations.get", {"operation_id": params["operation_id"]}) == result
        assert service.call("connections.authenticate", params) == result
        assert service._connections[connection_id]["endpoint"] is None
    finally:
        service.shutdown()


def test_rejection_journal_failure_still_releases_live_slot_and_old_uuid_never_requeues(tmp_path, monkeypatch):
    service, connection_id = admission_service(tmp_path)
    pool = RejectingExecutor()
    service._pool = pool
    def fail_receipt(*_, **__):
        raise OSError("Synthetic failure while recording executor rejection")
    monkeypatch.setattr(service, "_finish", fail_receipt)
    params = {"operation_id": uid(), "connection_id": connection_id}
    try:
        result = service.call("connections.authenticate", params)
        assert result["operation"]["state"] == "uncertain" and not service._running
        # Only the original FULL intent survived. Its live observation is still
        # uncertain, rather than incorrectly claiming a nonexistent worker runs.
        with service._db() as db:
            assert service._get(db, params["operation_id"])["state"] == "running"
        assert service.call("operations.get", {"operation_id": params["operation_id"]})["operation"]["state"] == "uncertain"
        assert service.call("connections.authenticate", params)["operation"]["state"] == "uncertain"
        assert pool.submissions == 1
    finally:
        service.shutdown()


@pytest.fixture
def installed_helper():
    # Explicit acceptance artifact only. No source/PATH/env product fallback.
    value = os.environ.get("STK_TEST_PEER_INSTALLATION")
    if not value:
        pytest.skip("An explicit installed helper acceptance prefix is required")
    from suan.peer.helper_installation import load_helper_installation
    prefix = Path(value)
    assert prefix.is_absolute()
    load_helper_installation(prefix)
    return prefix


def connect_bridges(bridges, prefix):
    cards = [call(b, "peer.info")["identity"]["card"] for b in bridges]
    connection_ids = []
    for i, bridge in enumerate(bridges):
        remote = cards[1-i]
        verified = call(bridge, "peer.pins.verify", {"operation_id": uid(), "card": remote,
                        "expected_peer_id": remote["peer_id"]})
        assert verified["operation"]["state"] == "completed"
        operation_id = uid()
        opened = call(bridge, "peer.connections.open", {"operation_id": operation_id, "peer_id": remote["peer_id"],
                      "helper_prefix": str(prefix), "offerer": i == 0, "route": "udp"})["operation"]
        assert opened["state"] == "completed"
        connection_ids.append(opened["result"]["connection_id"])
    auth_ids = []
    for bridge, connection in zip(bridges, connection_ids):
        operation_id = uid();auth_ids.append(operation_id)
        assert call(bridge, "peer.connections.authenticate", {"operation_id": operation_id,
                    "connection_id": connection})["operation"]["state"] == "running"
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        for i, bridge in enumerate(bridges):
            signal = call(bridge, "peer.connections.signals", {"connection_id": connection_ids[i]})["signal_text"]
            if signal is not None:
                pushed = call(bridges[1-i], "peer.connections.push_signal", {"operation_id": uid(),
                              "connection_id": connection_ids[1-i], "signal_text": signal})
                assert pushed["operation"]["state"] == "completed"
        results = [call(b, "peer.operations.get", {"operation_id": op})["operation"] for b, op in zip(bridges, auth_ids)]
        if all(r["state"] == "completed" for r in results):
            return connection_ids
        assert all(r["state"] in {"running", "completed"} for r in results)
    pytest.fail("Two actual installed helpers did not authenticate")


def prepare_transfer(bridges, connection_ids, tmp_path):
    from suan.project import ProjectStore
    from suan.peer.file_protocol import CHUNK_BYTES
    project = ProjectStore.create(tmp_path / "source", "Explicit bridge source")
    body = bytes(range(256)) * ((2 * CHUNK_BYTES + 256) // 256)
    (project.directory / "selected.bin").write_bytes(body)
    ids = project.files.index([str(project.directory / "selected.bin")], expected_revision=0)["record_ids"]
    snapshot = project.snapshots.capture(ids, expected_revision=1)["snapshot"]
    host, recipient = bridges
    handle = call(host, "project.open", {"directory": str(project.directory)})["project"]["handle"]
    session = call(host, "peer.sessions.host", {"operation_id": uid(), "connection_id": connection_ids[0],
                   "lifetime": 300, "session_id": None})["operation"]["result"]["result"]["offer"]
    plan = call(host, "project.peer.files.prepare", {"operation_id": uid(), "handle": handle,
                "expected_revision": project.info()["revision"], "snapshot_id": snapshot["id"],
                "record_ids": ids, "names": {ids[0]: "数据/selected.bin"}})["operation"]["result"]
    offered = call(host, "peer.files.offer", {"operation_id": uid(), "connection_id": connection_ids[0],
                   "plan_id": plan["plan_id"], "database_generation": plan["database_generation"],
                   "session_id": session["session_id"], "transfer_id": None})["operation"]["result"]
    assert call(recipient, "peer.sessions.list")["sessions"] == []
    discovered = call(recipient, "peer.files.list", {"role": "receiver"})["transfers"]
    assert [t["transfer_id"] for t in discovered] == [offered["transfer_id"]]
    reviewed = call(recipient, "peer.files.get", {"role": "receiver", "transfer_id": offered["transfer_id"]})
    assert reviewed["manifest"] == plan["manifest"]
    assert reviewed["offer"]["offer_operation_id"] == offered["operation"]["operation_id"]
    assert not (tmp_path / "received").exists()
    accepted = call(recipient, "peer.files.accept", {"operation_id": uid(), "connection_id": connection_ids[1],
                    "transfer_id": offered["transfer_id"], "offer_operation_id": reviewed["offer"]["offer_operation_id"],
                    "target": str(tmp_path / "received")})["operation"]["result"]["result"]
    return offered, accepted, body


def test_actual_bridge_installed_helpers_file_job_returns_promptly_and_completes(tmp_path, installed_helper):
    bridges = [InProcessBridge(tmp_path / name) for name in ("host", "recipient")]
    try:
        for i, bridge in enumerate(bridges):initialize(bridge, "Device " + str(i))
        connections = connect_bridges(bridges, installed_helper)
        offered, accepted, body = prepare_transfer(bridges, connections, tmp_path)
        params = {"operation_id": uid(), "connection_id": connections[0], "transfer_id": offered["transfer_id"],
                  "grant_id": accepted["grant_id"], "resume": False, "timeout": 300}
        started = time.monotonic()
        admitted = call(bridges[0], "peer.files.send", params)
        assert time.monotonic() - started < 1
        assert admitted["operation"]["state"] == "running"
        final = wait_operation(bridges[0], params["operation_id"])
        assert final["state"] == "completed" and final["result"]["state"] == "complete"
        assert (tmp_path / "received/数据/selected.bin").read_bytes() == body
        before = bridges[0].bridge.peers._connections[connections[0]]["endpoint"]._request_count
        assert call(bridges[0], "peer.files.send", params)["operation"] == final
        assert before == bridges[0].bridge.peers._connections[connections[0]]["endpoint"]._request_count
        assert "source_directory" not in json.dumps(call(bridges[0], "peer.operations.list"))
    finally:
        for bridge in bridges:bridge.close()


def test_actual_bridge_receipt_wait_allows_passive_poll_and_explicit_revoke(tmp_path, installed_helper, monkeypatch):
    bridges = [InProcessBridge(tmp_path / name) for name in ("host", "recipient")]
    accepted_block, release = threading.Event(), threading.Event()
    try:
        for i, bridge in enumerate(bridges):initialize(bridge, "Device " + str(i))
        connections = connect_bridges(bridges, installed_helper)
        offered, accepted, _body = prepare_transfer(bridges, connections, tmp_path)
        endpoint = bridges[0].bridge.peers._connections[connections[0]]["endpoint"]
        send = endpoint.send_file_data
        def hold(frame, **kwargs):
            receipt = send(frame, **kwargs)
            accepted_block.set()
            assert release.wait(10)
            return receipt
        monkeypatch.setattr(endpoint, "send_file_data", hold)
        params = {"operation_id": uid(), "connection_id": connections[0], "transfer_id": offered["transfer_id"],
                  "grant_id": accepted["grant_id"], "resume": False, "timeout": 300}
        assert call(bridges[0], "peer.files.send", params)["operation"]["state"] == "running"
        assert accepted_block.wait(10)
        assert call(bridges[0], "peer.files.send", params)["operation"]["state"] == "running"
        started = time.monotonic()
        revoked = call(bridges[0], "peer.files.revoke", {"operation_id": uid(), "role": "sender",
                       "transfer_id": offered["transfer_id"]})
        assert revoked["operation"]["state"] == "completed" and time.monotonic() - started < 1
        assert call(bridges[0], "peer.info")["identity"]["active"]
        release.set()
        final = wait_operation(bridges[0], params["operation_id"])
        assert final["state"] == "uncertain"
        status = call(bridges[0], "peer.files.get", {"role": "sender", "transfer_id": offered["transfer_id"]})["transfer"]
        assert not status["active"] and status["state"] == "cancelled"
        assert not (tmp_path / "received").exists()
    finally:
        release.set()
        for bridge in bridges:bridge.close()
