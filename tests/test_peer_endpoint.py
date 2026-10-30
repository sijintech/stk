"""Real native WebRTC + mutual Ed25519 + authorized shared-store RPC acceptance.

No key is serialized. Native tests require an explicit optional helper and fail,
rather than skip, if that configured helper is unusable.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import importlib
import os
from pathlib import Path
import sqlite3
import threading
import time
from uuid import uuid4

import pytest

from suan.peer.authority import PeerAuthority, auth_message, peer_id_for
from suan.peer.endpoint import (AUTH_FORMAT, MAX_AUTH_BYTES, PeerCallUncertain,
                                PeerEndpoint, _auth_frame)
from suan.peer.protocol import (FORMAT, METHODS, PeerProtocolError, decode_message,
                                encode_message, negotiate_hello)
from suan.peer.transport import NativeTransport, TransportError
from suan.project import ProjectStore


def uuid():
    return str(uuid4())


@pytest.fixture
def native_helper():
    value = os.environ.get("STK_PEER_TEST_HELPER")
    if not value:
        pytest.skip("explicit optional native helper not provided")
    path = Path(value)
    assert path.is_file(), "explicit helper must exist"
    return path


@dataclass
class Side:
    authority: object
    key: object
    peer_id: str
    public: bytes
    store: object
    target: dict


@pytest.fixture
def sides(tmp_path):
    try:
        ed = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
    except ImportError:
        if os.environ.get("STK_PEER_TEST_HELPER"):
            pytest.fail("explicit native endpoint acceptance requires the optional peer crypto dependency")
        pytest.skip("optional peer crypto dependency not installed")
    values = []
    for name in ("a", "b"):
        key = ed.Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes_raw()
        authority = PeerAuthority(tmp_path / name / "authority", owner_id=uuid())
        store = ProjectStore.create(tmp_path / name / "project", "Authorized peer project")
        values.append(Side(authority, key, peer_id_for(public), public, store, {}))
    for own, remote in (values, values[::-1]):
        own.authority.approve_peer(remote.peer_id, remote.public)
        bound = own.authority.bind_project(own.store.directory)
        grant = own.authority.grant(remote.peer_id, bound["project_id"], ["project.read", "project.edit"])
        own.target = {key: grant[key] for key in ("grant_id", "database_generation")}
        own.target["project_id"] = bound["project_id"]
    return values


@pytest.fixture
def links(native_helper):
    active = []
    def connect(route="udp"):
        a = NativeTransport(native_helper, offerer=True, route=route).start()
        b = NativeTransport(native_helper, offerer=False, route=route).start()
        stop = threading.Event()
        errors = []
        def forward(source, target):
            while not stop.is_set():
                try:
                    target.accept_signal(source.next_signal(timeout=.2))
                except TimeoutError:
                    continue
                except TransportError:
                    return
                except Exception:
                    errors.append("native signaling failed")
                    return
        pumps = [threading.Thread(target=forward, args=pair, daemon=True) for pair in ((a, b), (b, a))]
        for pump in pumps:
            pump.start()
        active.append((a, b, stop, pumps))
        info = [a.wait_ready(timeout=15), b.wait_ready(timeout=15)]
        assert a.channel_binding == b.channel_binding
        for endpoint_info in info:
            for candidate in endpoint_info["selected_pair"]:
                assert candidate["transport"].startswith("TCP") if route == "tcp" else candidate["transport"] == "UDP"
                if route == "ipv6":
                    assert candidate["family"] == "ipv6"
        assert not errors
        return a, b
    yield connect
    for a, b, stop, pumps in active:
        stop.set()
        a.close()
        b.close()
        for pump in pumps:
            pump.join(timeout=1)


def endpoints(transports, sides, options=None):
    options = options or {}
    result = []
    for index, (own, remote) in enumerate((sides, sides[::-1])):
        extra = dict(options.get(index, {}))
        result.append(PeerEndpoint(transports[index], own.authority, public_key=own.public,
            sign=extra.pop("sign", own.key.sign), remote_peer_id=extra.pop("remote_peer_id", remote.peer_id),
            remote_owner_id=extra.pop("remote_owner_id", remote.authority.owner_id), **extra))
    return result


def start_pair(pair, timeout=8):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(endpoint.start, timeout=timeout) for endpoint in pair]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=timeout + 3))
            except Exception as error:
                outcomes.append(error)
        return outcomes


def scripted_spec_peer(transport, own, remote, *, ack_mode="verified"):
    """Independent auth peer: literal wire frames, no PeerEndpoint/auth-codec reuse."""
    def send(kind, **fields):
        frame = {"format": "stk.peer-auth-channel/1", "type": kind, **fields}
        transport.send_control(json.dumps(frame, sort_keys=True, separators=(",", ":")).encode("ascii"), timeout=2)
    def receive(kind, fields):
        raw = transport.recv_control(timeout=2)
        assert len(raw) <= 4096
        frame = json.loads(raw.decode("utf-8"))
        assert set(frame) == {"format", "type", *fields}
        assert frame["format"] == "stk.peer-auth-channel/1" and frame["type"] == kind
        return frame
    context = None
    try:
        binding = transport.channel_binding
        issued = own.authority.challenge(remote.peer_id, channel_binding=binding)
        send("challenge", challenge=issued)
        received = receive("challenge", {"challenge"})["challenge"]
        signing_bytes = auth_message(received)
        assert received["owner_id"] == remote.authority.owner_id
        assert received["peer_id"] == own.peer_id and received["channel_binding"] == binding
        assert received["challenge_id"] != issued["challenge_id"]
        send("proof", challenge_id=received["challenge_id"], signature=own.key.sign(signing_bytes).hex())
        proof = receive("proof", {"challenge_id", "signature"})
        assert proof["challenge_id"] == issued["challenge_id"]
        context = own.authority.authenticate(proof["challenge_id"], bytes.fromhex(proof["signature"]))
        # Normative role: acknowledge the challenge whose proof WE verified.
        ack_id = issued["challenge_id"] if ack_mode == "verified" else (
            received["challenge_id"] if ack_mode == "signed_instead" else uuid())
        send("accepted", challenge_id=ack_id)
        accepted = receive("accepted", {"challenge_id"})
        # The other side must acknowledge the challenge WE signed for it.
        assert accepted["challenge_id"] == received["challenge_id"]
        if ack_mode != "verified":
            return {"sent_wrong_ack": True, "received_correct_ack": True}
        hello_id = uuid()
        transport.send_control(encode_message({"format": FORMAT, "id": hello_id, "method": "peer.hello",
            "params": {"protocols": [1], "capabilities": {"peer.hello": 1}}}), timeout=2)
        got_request = got_response = False
        while not (got_request and got_response):
            message = decode_message(transport.recv_control(timeout=2), method="peer.hello")
            if "method" in message:
                assert message["method"] == "peer.hello" and not got_request
                got_request = True
                result = negotiate_hello(message["params"], capabilities={"peer.hello": 1})
                transport.send_control(encode_message({"format": FORMAT, "id": message["id"],
                    "result": result}, method="peer.hello"), timeout=2)
            else:
                assert message["id"] == hello_id and "result" in message and not got_response
                assert message["result"]["capabilities"] == {"peer.hello": 1}
                got_response = True
        return {"sent_ack": issued["challenge_id"], "received_ack": received["challenge_id"],
                "both_proofs_verified": True, "hello_completed": True}
    finally:
        if context is not None:
            own.authority.disconnect(context)


@pytest.mark.parametrize("endpoint_index", [0, 1])
def test_real_handshake_interoperates_with_independent_spec_ack_peer_in_either_transport_role(links, sides, endpoint_index):
    transports = links()
    index = endpoint_index
    own, remote = sides[index], sides[1 - index]
    endpoint = PeerEndpoint(transports[index], own.authority, public_key=own.public, sign=own.key.sign,
        remote_peer_id=remote.peer_id, remote_owner_id=remote.authority.owner_id)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            starting = pool.submit(endpoint.start, timeout=3)
            scripted = pool.submit(scripted_spec_peer, transports[1 - index], remote, own)
            result = scripted.result(timeout=4)
            assert starting.result(timeout=4) is endpoint
        assert result["both_proofs_verified"] and result["hello_completed"]
        assert result["sent_ack"] != result["received_ack"]
        assert endpoint.capabilities == {"peer.hello": 1}
    finally:
        endpoint.close()


@pytest.mark.parametrize("ack_mode", ["signed_instead", "unrelated"])
def test_real_independent_peer_ack_must_confirm_the_challenge_this_endpoint_signed(links, sides, ack_mode):
    transports = links()
    own, remote = sides
    endpoint = PeerEndpoint(transports[0], own.authority, public_key=own.public, sign=own.key.sign,
        remote_peer_id=remote.peer_id, remote_owner_id=remote.authority.owner_id)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            starting = pool.submit(endpoint.start, timeout=3)
            scripted = pool.submit(scripted_spec_peer, transports[1], remote, own, ack_mode=ack_mode)
            assert scripted.result(timeout=4) == {"sent_wrong_ack": True, "received_correct_ack": True}
            with pytest.raises(PeerProtocolError) as error:
                starting.result(timeout=4)
            assert error.value.code == "unauthorized"
        assert endpoint._closed.is_set() and not endpoint._ready.is_set()
        assert all(side.store.info()["revision"] == 0 for side in sides)
    finally:
        endpoint.close()


@pytest.fixture
def connected(links, sides):
    active = []
    def connect(route="udp", options=None):
        pair = endpoints(links(route), sides, options=options)
        active.extend(pair)
        assert start_pair(pair) == pair
        return pair
    yield connect
    for endpoint in active:
        endpoint.close()


@pytest.mark.parametrize("route", ["udp", "tcp", "ipv6"])
def test_real_two_endpoints_mutual_auth_capabilities_both_directions_and_atomic_receipt(connected, sides, route):
    a, b = connected(route)
    assert set(a.capabilities) == set(b.capabilities) == METHODS
    detached = a.capabilities
    detached.clear()
    assert a.capabilities
    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(a.request, "project.catalog", sides[1].target)
        right = pool.submit(b.request, "project.catalog", sides[0].target)
        assert left.result(timeout=5)["project"]["id"] == sides[1].target["project_id"]
        assert right.result(timeout=5)["project"]["id"] == sides[0].target["project_id"]
    operation = uuid()
    params = {**sides[1].target, "operation_id": operation, "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Across native transport"}]}
    result = a.request("project.edit_operations.apply_once", params)
    assert not result["replayed"]
    receipt = result["receipt"]
    assert receipt["base_revision"] == 0 and receipt["applied_revision"] == 1
    table_id = receipt["commands"][0]["id"]
    assert sides[1].store.info()["revision"] == 1
    assert a.request("project.edit_operations.apply_once", params) == {"receipt": receipt, "replayed": True}
    assert a.request("project.edit_operations.get", {**sides[1].target, "operation_id": operation}) == {"receipt": receipt}
    page = a.request("project.table.read", {**sides[1].target, "table_id": table_id, "expected_revision": 1})
    assert page["table"]["id"] == table_id and page["table"]["records"] == []
    assert "directory" not in receipt and "handle" not in page and "pid" not in a.capabilities


def test_real_cas_same_operation_changed_request_and_unknown_receipt(connected, sides):
    a, _ = connected()
    target = sides[1].target
    params = {**target, "operation_id": uuid(), "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "First"}]}
    a.request("project.edit_operations.apply_once", params)
    for changed in ({**params, "expected_revision": 1},
                    {**params, "commands": [{"op": "create_table", "name": "Changed"}]},
                    {**params, "operation_id": uuid()}):
        with pytest.raises(PeerProtocolError) as error:
            a.request("project.edit_operations.apply_once", changed)
        assert error.value.code == "conflict"
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.edit_operations.get", {**target, "operation_id": uuid()})
    assert error.value.code == "not_found"
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.table.read", {**target, "table_id": uuid(), "expected_revision": 1})
    assert error.value.code == "not_found"
    assert sides[1].store.info()["revision"] == 1


def test_real_native_endpoint_retains_existing_large_shared_read_page_budget(connected, sides):
    store = sides[1].store
    table, field = uuid(), uuid()
    store.apply([{"op": "create_table", "id": table, "name": "Large bounded page"},
                 {"op": "add_field", "id": field, "table_id": table, "name": "Text", "type": "text"}],
                expected_revision=0)
    text = "x" * 15000
    revision = 1
    # Real shared edits create the synthetic data; no fake service or response.
    for _ in range(20):
        commands = []
        for _ in range(25):
            record = uuid()
            commands.extend([{"op": "add_record", "id": record, "table_id": table},
                             {"op": "set_cell", "table_id": table, "field_id": field,
                              "record_id": record, "value": text}])
        store.apply(commands, expected_revision=revision)
        revision += 1
    a, _ = connected()
    result = a.request("project.table.read", {**sides[1].target, "table_id": table,
        "expected_revision": revision, "limit": 500}, timeout=30)
    assert len(result["table"]["records"]) == result["total"] == 500
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    assert 7 * 1024 * 1024 < len(encoded) < 8 * 1024 * 1024
    assert text.encode() in encoded and store.info()["revision"] == revision


def test_real_grant_revocation_generation_and_peer_revocation_are_checked_each_request(connected, sides):
    a, _ = connected()
    target = sides[1].target
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.catalog", {**target, "database_generation": uuid()})
    assert error.value.code == "forbidden"
    sides[1].authority.revoke_grant(target["grant_id"])
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.catalog", target)
    assert error.value.code == "forbidden"
    refreshed = a.request("peer.hello", {"protocols": [1], "capabilities": {method: 1 for method in METHODS}})
    assert refreshed["capabilities"] == {"peer.hello": 1}
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.catalog", target)
    assert error.value.code == "unsupported"
    sides[1].authority.revoke_peer(sides[0].peer_id)
    with pytest.raises(PeerProtocolError) as error:
        a.request("peer.hello", {"protocols": [1], "capabilities": {"peer.hello": 1}})
    assert error.value.code == "forbidden"


def test_real_lost_reply_disconnect_does_not_replay_and_reconnect_get_retains_generated_uuid(connected, sides, monkeypatch):
    a, b = connected()
    committed = threading.Event()
    original = b._projects.apply_once
    def commit_then_disconnect(*args, **kwargs):
        result = original(*args, **kwargs)
        b._abort()  # Real native link closes after commit and before sending its reply.
        committed.set()
        return result
    monkeypatch.setattr(b._projects, "apply_once", commit_then_disconnect)
    operation = uuid()
    params = {**sides[1].target, "operation_id": operation, "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Committed without reply"}]}
    with pytest.raises(PeerCallUncertain) as error:
        a.request("project.edit_operations.apply_once", params, timeout=3)
    assert committed.wait(timeout=3)
    assert error.value.operation_id == operation and error.value.expected_revision == 0
    assert sides[1].store.info()["revision"] == 1
    with pytest.raises(PeerProtocolError):
        a.request("project.edit_operations.apply_once", params)
    for side in sides:
        # Reopen durable owner approvals, grants and database generation; contexts
        # are fresh and cannot be adopted from the lost connection.
        side.authority = PeerAuthority(side.authority.directory, owner_id=side.authority.owner_id)
    a2, _ = connected()
    receipt = a2.request("project.edit_operations.get", {**sides[1].target, "operation_id": operation})["receipt"]
    assert receipt["base_revision"] == 0
    assert a2.request("project.edit_operations.apply_once", params) == {"receipt": receipt, "replayed": True}
    assert sides[1].store.info()["revision"] == 1
    assert sides[1].store.catalog()["tables"][0]["id"] == receipt["commands"][0]["id"]


def test_real_post_commit_authority_metadata_failure_is_uncertain_and_new_connection_gets_original_receipt(connected, sides, monkeypatch):
    a, b = connected()
    operation = uuid()
    original_connect = sqlite3.connect
    authority_uri = sides[1].authority.path.as_uri()
    injected, wire_errors = [], []
    class MetadataFailure:
        def __init__(self, connection):
            self.connection = connection
        @property
        def row_factory(self):
            return self.connection.row_factory
        @row_factory.setter
        def row_factory(self, value):
            self.connection.row_factory = value
        def __getattr__(self, name):
            return getattr(self.connection, name)
        def execute(self, sql, *args, **kwargs):
            if sql.startswith("UPDATE projects SET revision=") and not injected:
                # This is after the independent project edit transaction returned.
                assert sides[1].store.info()["revision"] == 1
                injected.append(True)
                raise sqlite3.OperationalError("private authority metadata diagnostic")
            return self.connection.execute(sql, *args, **kwargs)
    def connect(database, *args, **kwargs):
        connection = original_connect(database, *args, **kwargs)
        return MetadataFailure(connection) if str(database).startswith(authority_uri + "?") else connection
    original_send = b._transport.send_control
    def capture(raw, **kwargs):
        message = json.loads(raw)
        if "error" in message:
            wire_errors.append(message["error"])
        return original_send(raw, **kwargs)
    monkeypatch.setattr(b._transport, "send_control", capture)
    params = {**sides[1].target, "operation_id": operation, "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Committed before authority cleanup"}]}
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        with pytest.raises(PeerCallUncertain) as error:
            a.request("project.edit_operations.apply_once", params)
        assert error.value.operation_id == operation and error.value.expected_revision == 0
    assert injected == [True]
    assert wire_errors == [{"code": "unavailable", "message": "Peer request was rejected"}]
    a.close()
    b.close()
    for side in sides:
        side.authority = PeerAuthority(side.authority.directory, owner_id=side.authority.owner_id)
    a2, _ = connected()
    # No changed scope/grant/generation, no second apply and no automatic retry.
    receipt = a2.request("project.edit_operations.get", {**sides[1].target, "operation_id": operation})["receipt"]
    assert receipt["base_revision"] == 0 and receipt["applied_revision"] == 1
    assert sides[1].store.info()["revision"] == 1
    assert sides[1].store.catalog()["tables"][0]["id"] == receipt["commands"][0]["id"]


def test_real_post_commit_response_schema_failure_is_server_error_and_preserves_uncertain_receipt(connected, sides, monkeypatch):
    a, b = connected()
    original_apply, original_send = b._projects.apply_once, b._transport.send_control
    errors = []
    def corrupt_result(*args, **kwargs):
        result = original_apply(*args, **kwargs)
        result["receipt"]["project_id"] = "invalid-response-uuid"
        return result
    def capture(raw, **kwargs):
        message = json.loads(raw)
        if "error" in message:
            errors.append(message["error"])
        return original_send(raw, **kwargs)
    monkeypatch.setattr(b._projects, "apply_once", corrupt_result)
    monkeypatch.setattr(b._transport, "send_control", capture)
    operation = uuid()
    params = {**sides[1].target, "operation_id": operation, "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Commit preceded encoding failure"}]}
    with pytest.raises(PeerCallUncertain) as error:
        a.request("project.edit_operations.apply_once", params)
    assert error.value.operation_id == operation and error.value.expected_revision == 0
    assert errors == [{"code": "internal_error", "message": "Peer request was rejected"}]
    assert sides[1].store.info()["revision"] == 1
    receipt = a.request("project.edit_operations.get", {**sides[1].target, "operation_id": operation})["receipt"]
    assert receipt["project_id"] == sides[1].target["project_id"]
    assert sides[1].store.catalog()["tables"][0]["id"] == receipt["commands"][0]["id"]


def test_real_read_timeout_closes_one_use_connection_and_cannot_dispatch_more(connected, sides, monkeypatch):
    a, b = connected()
    entered, release = threading.Event(), threading.Event()
    original = b._projects.catalog
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)
    monkeypatch.setattr(b._projects, "catalog", blocked)
    try:
        before = time.monotonic()
        with pytest.raises(PeerProtocolError) as error:
            a.request("project.catalog", sides[1].target, timeout=.15)
        assert error.value.code == "unavailable" and entered.is_set()
        assert time.monotonic() - before < 2
        with pytest.raises(PeerProtocolError):
            a.start()
    finally:
        release.set()


def test_real_local_request_budget_exhaustion_is_definite_and_does_not_mark_unsent_write_uncertain(connected, sides, monkeypatch):
    a, _ = connected()
    monkeypatch.setattr("suan.peer.endpoint.MAX_CONNECTION_REQUESTS", 1)  # The startup hello used the one ID.
    params = {**sides[1].target, "operation_id": uuid(), "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Must remain unsent"}]}
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.edit_operations.apply_once", params)
    assert error.value.code == "limit_exceeded" and not isinstance(error.value, PeerCallUncertain)
    assert not a._closed.is_set() and sides[1].store.info()["revision"] == 0


def test_real_authentication_deadline_closes_silent_peer_without_signing(links, sides):
    a, _ = endpoints(links(), sides)
    calls = []
    a._sign = lambda message: calls.append(message)
    before = time.monotonic()
    try:
        with pytest.raises(PeerProtocolError) as error:
            a.start(timeout=.15)  # The other NativeTransport is ready but has no running endpoint.
        assert error.value.code == "unauthorized" and calls == []
        assert time.monotonic() - before < 2 and a._closed.is_set()
    finally:
        a.close()


def test_real_bounded_bidirectional_workers_and_pending_capacity(connected, sides, monkeypatch):
    a, b = connected(options={1: {"max_workers": 1}, 0: {"max_inflight": 1}})
    entered, release = threading.Event(), threading.Event()
    original = b._projects.catalog
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)
    monkeypatch.setattr(b._projects, "catalog", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(a.request, "project.catalog", sides[1].target, timeout=2)
        try:
            assert entered.wait(timeout=3)
            with pytest.raises(PeerProtocolError) as error:
                a.request("project.catalog", sides[1].target)
            assert error.value.code == "busy"
            # The blocked incoming worker does not monopolize the single reader.
            assert b.request("project.catalog", sides[0].target)["project"]["id"] == sides[0].target["project_id"]
        finally:
            release.set()
        assert first.result(timeout=5)["project"]["revision"] == 0


def test_real_incoming_worker_capacity_returns_busy_without_queuing_or_blocking_reverse_requests(connected, sides, monkeypatch):
    a, b = connected(options={1: {"max_workers": 1}})
    entered, release = threading.Event(), threading.Event()
    original = b._projects.catalog
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)
    monkeypatch.setattr(b._projects, "catalog", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(a.request, "project.catalog", sides[1].target)
        try:
            assert entered.wait(timeout=3)
            with pytest.raises(PeerProtocolError) as error:
                a.request("project.catalog", sides[1].target)
            assert error.value.code == "busy"
            assert b.request("project.catalog", sides[0].target)["project"]["revision"] == 0
        finally:
            release.set()
        assert first.result(timeout=5)["project"]["revision"] == 0


def test_real_hello_cannot_block_reader_behind_an_accepted_project_lease(connected, sides, monkeypatch):
    import suan.peer.endpoint as endpoint_module
    a, b = connected(options={1: {"max_workers": 1}})
    entered, release, hello_received = threading.Event(), threading.Event(), threading.Event()
    original_catalog = ProjectStore.catalog
    original_decode = endpoint_module.decode_message
    def held_catalog(store, **kwargs):
        if store.path == sides[1].store.path:
            # This is the real store invocation *inside* authority.project_access.
            entered.set()
            assert release.wait(timeout=5)
        return original_catalog(store, **kwargs)
    def observe_wire(raw, **kwargs):
        message = original_decode(raw, **kwargs)
        if threading.current_thread() is b._reader and message.get("method") == "peer.hello":
            hello_received.set()
        return message
    monkeypatch.setattr(ProjectStore, "catalog", held_catalog)
    monkeypatch.setattr(endpoint_module, "decode_message", observe_wire)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(a.request, "project.catalog", sides[1].target)
        try:
            assert entered.wait(timeout=3)
            hello = pool.submit(a.request, "peer.hello", {"protocols": [1],
                "capabilities": {method: 1 for method in METHODS}}, timeout=2)
            assert hello_received.wait(timeout=3)
            # This reply must be dispatched while B's accepted store read is
            # still holding its authority lease and A's hello has reached B.
            assert b.request("project.catalog", sides[0].target, timeout=.5)["project"]["revision"] == 0
            with pytest.raises(PeerProtocolError) as error:
                hello.result(timeout=1)
            assert error.value.code == "busy"
        finally:
            release.set()
        assert first.result(timeout=5)["project"]["revision"] == 0


def test_real_concurrent_hello_is_busy_until_prior_reply_preserves_matching_capability_snapshot(connected, monkeypatch):
    a, b = connected()
    entered, release = threading.Event(), threading.Event()
    original_send = b._send
    def delay_first_hello(raw, deadline):
        message = json.loads(raw)
        if "protocol" in message.get("result", {}) and not entered.is_set():
            entered.set()
            assert release.wait(timeout=5)
        return original_send(raw, deadline)
    monkeypatch.setattr(b, "_send", delay_first_hello)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(a.request, "peer.hello", {"protocols": [1],
            "capabilities": {method: 1 for method in METHODS}}, timeout=3)
        try:
            assert entered.wait(timeout=2)
            with pytest.raises(PeerProtocolError) as error:
                a.request("peer.hello", {"protocols": [1], "capabilities": {"peer.hello": 1}}, timeout=1)
            assert error.value.code == "busy"
        finally:
            release.set()
        assert set(first.result(timeout=2)["capabilities"]) == METHODS
    assert set(a.capabilities) == set(b._inbound_capabilities) == METHODS


def test_real_project_dispatch_waits_for_local_hello_completion_in_both_directions(links, sides, monkeypatch):
    a, b = endpoints(links(), sides)
    entered, release = threading.Event(), threading.Event()
    original_send = b._send
    def delay_reply_to_a(raw, deadline):
        message = json.loads(raw)
        if "protocol" in message.get("result", {}) and not entered.is_set():
            entered.set()
            assert release.wait(timeout=5)
        return original_send(raw, deadline)
    monkeypatch.setattr(b, "_send", delay_reply_to_a)
    params = {**sides[0].target, "operation_id": uuid(), "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Wait for both hello directions"}]}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            starting_a = pool.submit(a.start, timeout=4)
            starting_b = pool.submit(b.start, timeout=4)
            try:
                assert entered.wait(timeout=2)
                assert starting_b.result(timeout=2) is b
                assert b._ready.is_set() and not a._ready.is_set()
                with pytest.raises(PeerProtocolError) as error:
                    b.request("project.edit_operations.apply_once", params, timeout=1)
                assert error.value.code == "busy"
                assert sides[0].store.info()["revision"] == 0
            finally:
                release.set()
            assert starting_a.result(timeout=2) is a
        assert not b.request("project.edit_operations.apply_once", params)["replayed"]
        assert sides[0].store.info()["revision"] == 1
    finally:
        a.close()
        b.close()


def test_real_method_bound_response_validation_rejects_local_metadata_on_wire(connected, sides, monkeypatch):
    a, b = connected()
    original = b._transport.send_control
    def corrupt(raw, **kwargs):
        message = json.loads(raw)
        if "result" in message and "project" in message["result"]:
            message["result"]["project"]["directory"] = "/private/owner/project"
            raw = json.dumps(message).encode()
        return original(raw, **kwargs)
    monkeypatch.setattr(b._transport, "send_control", corrupt)
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.catalog", sides[1].target)
    assert error.value.code == "unavailable" and a._closed.is_set()
    assert "private" not in str(error.value)


def test_real_duplicate_transport_request_id_closes_connection_without_reexecuting_write(connected, sides, monkeypatch):
    a, b = connected()
    sent = []
    original = a._transport.send_control
    def capture(raw, **kwargs):
        if json.loads(raw).get("method") == "project.edit_operations.apply_once":
            sent.append(raw)
        return original(raw, **kwargs)
    monkeypatch.setattr(a._transport, "send_control", capture)
    params = {**sides[1].target, "operation_id": uuid(), "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "No transport replay"}]}
    assert not a.request("project.edit_operations.apply_once", params)["replayed"]
    assert len(sent) == 1
    original(sent[0], timeout=2)
    assert b._closed.wait(timeout=2)
    # A remote close need not immediately notify an otherwise idle UDP link.
    # Its next bounded request still fails and is never retried.
    with pytest.raises(PeerProtocolError):
        a.request("project.catalog", sides[1].target, timeout=.2)
    assert a._closed.is_set()
    assert sides[1].store.info()["revision"] == 1


def test_real_single_direction_grant_is_independent_from_reverse_capability_offers(connected, sides):
    # A authorizes B; B authorizes no project access by A.
    sides[1].authority.revoke_grant(sides[1].target["grant_id"])
    a, b = connected()
    assert a.capabilities == {"peer.hello": 1}
    assert set(b.capabilities) == METHODS
    result = b.request("project.edit_operations.apply_once", {**sides[0].target,
        "operation_id": uuid(), "expected_revision": 0,
        "commands": [{"op": "create_table", "name": "One direction only"}]})
    assert not result["replayed"] and sides[0].store.info()["revision"] == 1
    assert b.request("project.catalog", sides[0].target)["project"]["revision"] == 1
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.catalog", sides[1].target)
    assert error.value.code == "unsupported"
    assert sides[1].store.info()["revision"] == 0


def test_real_rebind_invalidates_old_context_and_generation_without_automatic_reauthentication(connected, sides):
    a, _ = connected()
    old = dict(sides[1].target)
    assert a.request("project.catalog", old)["project"]["revision"] == 0
    rebound = sides[1].authority.rebind_project(old["project_id"], sides[1].store.directory)
    grant = sides[1].authority.grant(sides[0].peer_id, old["project_id"], ["project.read", "project.edit"])
    assert rebound["database_generation"] != old["database_generation"]
    new = {key: grant[key] for key in ("grant_id", "database_generation")}
    new["project_id"] = old["project_id"]
    for target in (old, new):
        with pytest.raises(PeerProtocolError) as error:
            a.request("project.catalog", target)
        assert error.value.code == "forbidden"
    a2, _ = connected()
    assert a2.request("project.catalog", new)["project"]["revision"] == 0
    with pytest.raises(PeerProtocolError) as error:
        a2.request("project.catalog", old)
    assert error.value.code == "forbidden"


class AlterControl:
    """Fault injector around an actual native encrypted link; never a replacement transport."""
    def __init__(self, transport, mutate):
        self.transport, self.mutate = transport, mutate
    def __getattr__(self, name):
        return getattr(self.transport, name)
    def send_control(self, payload, **kwargs):
        return self.transport.send_control(self.mutate(payload), **kwargs)


@pytest.mark.parametrize("fault", ["binding", "owner", "peer", "nonce", "expires", "unknown",
                                   "signature", "challenge_id", "preauth_rpc"])
def test_real_auth_rejects_wrong_identity_binding_signature_and_pre_auth_rpc_without_sign_oracle(links, sides, fault):
    transports = list(links())
    sign_calls = []
    def sign(message):
        sign_calls.append(True)
        return sides[0].key.sign(message)
    def mutate(raw):
        value = json.loads(raw)
        if value.get("type") == "challenge":
            if fault in {"binding", "peer"}:
                value["challenge"]["channel_binding" if fault == "binding" else "peer_id"] = "f" * 64
            elif fault == "owner":
                value["challenge"]["owner_id"] = uuid()
            elif fault == "nonce":
                value["challenge"]["nonce"] = "not-a-canonical-nonce"
            elif fault == "expires":
                value["challenge"]["expires_in"] = True
            elif fault == "unknown":
                value["challenge"]["sign_this"] = "arbitrary-message"
            elif fault == "preauth_rpc":
                return encode_message({"format": FORMAT, "id": uuid(), "method": "peer.hello",
                                       "params": {"protocols": [1], "capabilities": {"peer.hello": 1}}})
        if value.get("type") == "proof":
            if fault == "signature":
                value["signature"] = "00" * 64
            elif fault == "challenge_id":
                value["challenge_id"] = uuid()
        return json.dumps(value).encode()
    transports[1] = AlterControl(transports[1], mutate)
    pair = endpoints(transports, sides, options={0: {"sign": sign}})
    try:
        results = start_pair(pair, timeout=2)
        assert all(isinstance(result, PeerProtocolError) and result.code == "unauthorized" for result in results)
        if fault in {"binding", "owner", "peer", "nonce", "expires", "unknown", "preauth_rpc"}:
            assert sign_calls == []
        assert all(endpoint._closed.is_set() for endpoint in pair)
        assert all(side.store.info()["revision"] == 0 for side in sides)
    finally:
        for endpoint in pair:
            endpoint.close()


def test_real_pinned_remote_public_identity_cannot_be_substituted(links, sides):
    pair = endpoints(links(), sides, options={0: {"remote_peer_id": "f" * 64}})
    try:
        assert all(isinstance(result, PeerProtocolError) for result in start_pair(pair, timeout=1))
        assert all(side.store.info()["revision"] == 0 for side in sides)
    finally:
        for endpoint in pair:
            endpoint.close()


def test_real_fixed_error_mapping_hides_local_paths_and_sql(connected, sides, monkeypatch):
    a, b = connected()
    def fail(*args, **kwargs):
        raise RuntimeError("/private/owner/project.sqlite3 SELECT private_column")
    monkeypatch.setattr(b._projects, "catalog", fail)
    with pytest.raises(PeerProtocolError) as error:
        a.request("project.catalog", sides[1].target)
    assert error.value.code == "internal_error"
    assert str(error.value) == "Peer request was rejected"


@pytest.mark.parametrize("raw", [b"", b"{}", b"a" * (MAX_AUTH_BYTES + 1), b"\xff", b"\xef\xbb\xbf{}",
    b'{"format":"stk.peer-auth-channel/1","type":"accepted","challenge_id":"x","type":"proof"}',
    b"[" * 9 + b"]" * 9, b'{"format":"stk.peer-auth-channel/1","type":NaN}',
    b'{"format":"stk.peer-auth-channel/1","type":"accepted","challenge_id":1}',
    b'{"format":"stk.peer-auth-channel/1","type":"proof","challenge_id":{},"signature":"x"}'])
def test_auth_frames_have_separate_strict_byte_depth_type_and_duplicate_key_limits(raw):
    with pytest.raises(PeerProtocolError) as error:
        _auth_frame(raw)
    assert error.value.code == "unauthorized"
    assert str(error.value) == "Peer authentication failed"


def test_construction_is_passive_private_key_not_persisted_and_identity_pins_explicit(sides, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("endpoint construction cannot start anything")
    monkeypatch.setattr(threading.Thread, "start", forbidden)
    a = PeerEndpoint(object(), sides[0].authority, public_key=sides[0].public, sign=sides[0].key.sign,
                     remote_peer_id=sides[1].peer_id, remote_owner_id=sides[1].authority.owner_id)
    assert repr(a) == "<PeerEndpoint>" and a._context is None and a._pool is None
    for options in ({"max_inflight": 9}, {"max_workers": 5}, {"remote_owner_id": "self-asserted"}):
        kwargs = dict(public_key=sides[0].public, sign=sides[0].key.sign,
                      remote_peer_id=sides[1].peer_id, remote_owner_id=sides[1].authority.owner_id)
        with pytest.raises(PeerProtocolError):
            PeerEndpoint(object(), sides[0].authority, **(kwargs | options))
