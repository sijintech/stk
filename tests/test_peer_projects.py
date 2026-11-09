"""Authenticated peer project operations use real grants and shared SQLite state."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import inspect
import os
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import catalog as catalog_module
from suan.project import edit_operations, workspace_bundle
from suan.project.edit_operations import OperationNotFound
from suan.project.store import UnsupportedProjectFormat
from suan.peer.projects import PeerProjects
from suan.peer.protocol import FORMAT, decode_message, encode_message
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_edit_operations import _physical, _spill


def authenticated(authority, private, peer_id, binding="b" * 64):
    from suan.peer.authority import auth_message
    challenge = authority.challenge(peer_id, channel_binding=binding)
    return authority.authenticate(challenge["challenge_id"], private.sign(auth_message(challenge)))


@dataclass
class Access:
    authority: object
    store: ProjectStore
    project_id: str
    owner_id: str
    private: object
    peer_id: str
    grant: dict
    context: object

    @property
    def target(self):
        return {key: self.grant[key] for key in ("grant_id", "database_generation")}

    @property
    def projects(self):
        return PeerProjects(self.authority)

    def apply(self, commands=None, *, operation_id=None, expected_revision=0):
        return self.projects.apply_once(self.context, self.project_id,
            [{"op": "create_table", "name": "Peer table"}] if commands is None else commands,
            operation_id=str(uuid4()) if operation_id is None else operation_id,
            expected_revision=expected_revision, **self.target)

    def get(self, operation_id):
        return self.projects.get(self.context, self.project_id, operation_id, **self.target)

    def reconnect(self, binding="c" * 64):
        self.context = authenticated(self.authority, self.private, self.peer_id, binding)


@pytest.fixture
def access(tmp_path):
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from suan.peer.authority import PeerAuthority, peer_id_for
    store = ProjectStore.create(tmp_path / "project", "Owner authorized project")
    owner_id = str(uuid4())
    authority = PeerAuthority(tmp_path / "authority", owner_id=owner_id)
    bound = authority.bind_project(store.directory)
    private = crypto.Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    peer_id = peer_id_for(public)
    authority.approve_peer(peer_id, public)
    grant = authority.grant(peer_id, bound["project_id"], ["project.read", "project.edit"])
    assert grant["database_generation"] == bound["database_generation"]
    return Access(authority, store, bound["project_id"], owner_id, private, peer_id,
                  grant, authenticated(authority, private, peer_id))


def unchanged(store):
    with sqlite3.connect(store.path) as db:
        receipts = db.execute("SELECT count(*) FROM project_edit_operations").fetchone()[0]
    return store.snapshot(), store.history(), receipts


def schema(access):
    table, other, field = (str(uuid4()) for _ in range(3))
    records = [str(uuid4()) for _ in range(3)]
    commands = [{"op": "create_table", "id": table, "name": "Records"},
                {"op": "create_table", "id": other, "name": "Other"},
                {"op": "add_field", "id": field, "table_id": table, "name": "Text", "type": "text"}]
    for index, record in enumerate(records):
        commands.extend([{"op": "add_record", "id": record, "table_id": table},
                         {"op": "set_cell", "table_id": table, "field_id": field,
                          "record_id": record, "value": f"record-{index}"}])
    access.apply(commands)
    return table, field, records


def test_authenticated_structure_and_record_pages_reuse_shared_revision_bounds(access):
    table, _, records = schema(access)
    service, target = access.projects, access.target
    before = unchanged(access.store)
    first = service.catalog(access.context, access.project_id, limit=1, **target)
    assert first["project"]["id"] == access.project_id and first["project"]["revision"] == 1
    assert len(first["tables"]) == 1 and "records" not in first["tables"][0]
    assert not {"directory", "path", "handle"} & first.keys()
    assert set(first["project"]) == {"id", "name", "revision"}
    second = service.catalog(access.context, access.project_id, expected_revision=1,
                             offset=first["next_offset"], limit=1, **target)
    assert second["total"] == 2 and second["next_offset"] is None
    page = service.read_table(access.context, access.project_id, table, expected_revision=1, limit=2, **target)
    assert page["revision"] == 1 and page["total"] == 3 and page["next_offset"] == 2
    assert [item["id"] for item in page["table"]["records"]] == records[:2]
    located = service.read_table(access.context, access.project_id, table, expected_revision=1,
                                record_id=records[-1], limit=2, **target)
    assert located["offset"] == 2 and [item["id"] for item in located["table"]["records"]] == records[-1:]
    assert unchanged(access.store) == before
    access.store.apply([{"op": "create_table", "name": "Local concurrent edit"}], expected_revision=1)
    for call in (lambda: service.catalog(access.context, access.project_id, expected_revision=1, **target),
                 lambda: service.read_table(access.context, access.project_id, table, expected_revision=1, **target)):
        with pytest.raises(RevisionConflict):
            call()


def test_bridge_and_peer_project_pages_and_scoped_receipts(access, inproc):
    table, _, _ = schema(access)
    bridge = inproc()
    handle = bridge.call("project.open", {"directory": str(access.store.directory)})["project"]["handle"]
    peer = access.projects
    target = access.target

    def peer_result(method, result):
        response = {"format": FORMAT, "id": str(uuid4()), "result": result}
        return decode_message(encode_message(response, method=method), method=method)["result"]

    before = unchanged(access.store)
    catalog = "project.catalog"
    read_table = "project.table.read"
    for offset, following in ((0, 1), (1, None)):
        page = {"offset": offset, "limit": 1, "expected_revision": 1}
        local_catalog = bridge.call(catalog, {"handle": handle, **page})
        remote_catalog = peer.catalog(access.context, access.project_id, **target, **page)
        assert local_catalog == peer_result(catalog, remote_catalog)
        assert local_catalog["next_offset"] == following
    for offset, following in ((0, 1), (1, 2), (2, None)):
        page = {"offset": offset, "limit": 1, "expected_revision": 1}
        local_table = bridge.call(read_table, {"handle": handle, "table_id": table, **page})
        remote_table = peer.read_table(access.context, access.project_id, table, **target, **page)
        assert local_table == peer_result(read_table, remote_table)
        assert local_table["next_offset"] == following
    assert unchanged(access.store) == before

    apply = "project.edit_operations.apply_once"
    get = "project.edit_operations.get"
    identity = str(uuid4())
    request = {"operation_id": identity, "expected_revision": 1,
               "commands": [{"op": "create_table", "name": "Local edit"}]}
    local = bridge.call(apply, {"handle": handle, **request})
    assert local["replayed"] is False and local["receipt"]["scope"] == "local"
    with pytest.raises(OperationNotFound):
        access.get(identity)
    peer_request = {"operation_id": identity, "expected_revision": 2,
                    "commands": [{"op": "create_table", "name": "Peer edit"}]}
    remote = peer_result(apply, access.apply(**peer_request))
    assert remote["replayed"] is False and remote["receipt"]["scope"] != local["receipt"]["scope"]
    assert peer_result(get, {"receipt": access.get(identity)}) == {"receipt": remote["receipt"]}
    assert bridge.call(get, {"handle": handle, "operation_id": identity}) == {"receipt": local["receipt"]}
    assert bridge.call(apply, {"handle": handle, **request}) == {"receipt": local["receipt"], "replayed": True}
    assert peer_result(apply, access.apply(**peer_request)) == {"receipt": remote["receipt"], "replayed": True}
    assert access.store.info()["revision"] == 3

    after = unchanged(access.store)
    stale = {"offset": 1, "limit": 1, "expected_revision": 1}
    assert bridge.error(catalog, {"handle": handle, **stale})["code"] == "conflict"
    with pytest.raises(RevisionConflict):
        peer.catalog(access.context, access.project_id, **target, **stale)
    assert bridge.error(read_table, {"handle": handle, "table_id": table, **stale})["code"] == "conflict"
    with pytest.raises(RevisionConflict):
        peer.read_table(access.context, access.project_id, table, **target, **stale)
    assert unchanged(access.store) == after
    bridge.assert_clean()


def test_current_authorized_file_index_content_is_identical_on_bridge_and_peer_until_revoked(access, inproc,
                                                                                             tmp_path):
    """CURRENT behavior (CP-0 F23, docs/design/cloud-project-service.md).

    An authorized table read returns ordinary file-index cell values unchanged, including an absolute
    external path; only protocol metadata is closed. This is the present adapter baseline. It neither
    chooses a future cloud content policy nor grants any file transfer right (the file is never read).
    """
    from suan.peer.authority import PeerDenied
    from suan.project import files
    outside = tmp_path / "outside-project"
    outside.mkdir()
    source = (outside / "synthetic-input.csv").resolve()
    source.write_text("synthetic,1\n", encoding="utf-8")
    assert not source.is_relative_to(access.store.directory)
    location = "external:windows" if os.name == "nt" else "external:posix"
    indexed = access.store.files.index([str(source)], expected_revision=0)
    assert indexed["revision"] == 1 and indexed["table_id"] == files.TABLE_ID
    record = indexed["record_ids"][0]

    bridge = inproc()
    handle = bridge.call("project.open", {"directory": str(access.store.directory)})["project"]["handle"]
    method = "project.table.read"
    page = {"table_id": files.TABLE_ID, "expected_revision": 1, "record_id": record}
    local = bridge.call(method, {"handle": handle, **page})
    remote = access.projects.read_table(access.context, access.project_id, **page, **access.target)
    response = {"format": FORMAT, "id": str(uuid4()), "result": remote}
    decoded = decode_message(encode_message(response, method=method), method=method)["result"]
    assert local == decoded == remote
    row = next(item for item in decoded["table"]["records"] if item["id"] == record)
    values = row["values"]
    assert values[files.FIELD_IDS["path"]] == str(source)
    assert values[files.FIELD_IDS["location"]] == location
    assert values[files.FIELD_IDS["name"]] == "synthetic-input.csv"
    # Protocol metadata stays closed; the path is only cell content of an authorized row.
    assert decoded["project_id"] == access.project_id and decoded["revision"] == 1
    assert not {"directory", "path", "handle"} & decoded.keys()
    assert set(decoded["table"]) == {"id", "name", "fields", "records"}
    catalog = access.projects.catalog(access.context, access.project_id, **access.target)
    assert set(catalog["project"]) == {"id", "name", "revision"}
    assert str(source) not in repr(catalog)

    before = unchanged(access.store)
    access.authority.revoke_grant(access.target["grant_id"])
    with pytest.raises(PeerDenied):
        access.projects.read_table(access.context, access.project_id, **page, **access.target)
    with pytest.raises(PeerDenied):
        access.projects.catalog(access.context, access.project_id, **access.target)
    assert unchanged(access.store) == before
    bridge.assert_clean()


def _receipt_rows(store):
    with sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True) as db:
        return db.execute("SELECT scope, operation_id FROM project_edit_operations ORDER BY scope").fetchall()


def test_bridge_and_peer_race_two_identities_at_one_revision_with_one_winner_and_no_loser_receipt(
        access, inproc, monkeypatch, request):
    """CP-0 F3/F11d: the strict local Bridge and the authenticated PeerProjects adapter, on one new project.

    Both workers release from the same barrier and send apply_once at revision 0 with their own new
    UUID. Without a held lock the Bridge won every sampled run, so the test holds the database write
    lock until both calls have reached the store's write entry (ProjectStore._connect(write=True)). That
    observation proves only arrival at the write entry, not that either call is already blocked in
    SQLite; after release, SQLite's own locking decides the winner. Assertions are symmetric and do not
    depend on which entry wins. Every wait in the test is bounded; the test itself never sleeps.
    """
    bridge = inproc()
    handle = bridge.call("project.open", {"directory": str(access.store.directory)})["project"]["handle"]
    apply, get = "project.edit_operations.apply_once", "project.edit_operations.get"
    assert access.store.info()["revision"] == 0 and _receipt_rows(access.store) == []
    names = {"bridge": "Bridge entry table", "peer": "Peer entry table"}
    identities = {entry: str(uuid4()) for entry in names}
    start = threading.Barrier(2, timeout=10)
    arrived = {entry: threading.Event() for entry in names}
    connect = ProjectStore._connect

    def observed_connect(self, *, write=False):
        if write:  # The Bridge runs each request on its own "stk-bridge-<method>" thread.
            arrived["bridge" if threading.current_thread().name.startswith("stk-bridge-") else "peer"].set()
        return connect(self, write=write)

    monkeypatch.setattr(ProjectStore, "_connect", observed_connect)
    holder = sqlite3.connect(access.store.path, isolation_level=None, timeout=10)
    holder.execute("BEGIN IMMEDIATE")  # A writer that reaches BEGIN IMMEDIATE meanwhile waits (10 s busy timeout).

    def bridge_write():
        start.wait()
        message = bridge.response(bridge.request(apply, {
            "handle": handle, "operation_id": identities["bridge"], "expected_revision": 0,
            "commands": [{"op": "create_table", "name": names["bridge"]}]}))
        return ("error", message["error"]["code"]) if "error" in message else ("result", message["result"])

    def peer_write():
        start.wait()
        try:
            return "result", access.apply([{"op": "create_table", "name": names["peer"]}],
                                          operation_id=identities["peer"], expected_revision=0)
        except RevisionConflict:
            return "error", "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {"bridge": pool.submit(bridge_write), "peer": pool.submit(peer_write)}
        try:
            assert all(event.wait(timeout=10) for event in arrived.values()), "both entries reach the write lock"
        finally:
            holder.execute("ROLLBACK")  # Release even on failure so neither writer waits out its timeout.
            holder.close()
        outcomes = {entry: future.result(timeout=60) for entry, future in futures.items()}
    monkeypatch.setattr(ProjectStore, "_connect", connect)
    winners =[entry for entry, (kind, _) in outcomes.items() if kind == "result"]
    assert len(winners) == 1, outcomes
    winner, = winners
    loser, = set(names) - {winner}
    request.node.user_properties.append(("race_winner", winner))  # JUnit evidence only; either entry may win
    assert outcomes[loser] == ("error", "conflict")  # Bridge error code and peer RevisionConflict alike
    won = outcomes[winner][1]
    assert won["replayed"] is False and won["receipt"]["base_revision"] == 0
    assert won["receipt"]["applied_revision"] == 1 and won["receipt"]["operation_id"] == identities[winner]
    assert (won["receipt"]["scope"] == "local") == (winner == "bridge")

    snapshot = access.store.snapshot()
    assert snapshot["project"]["revision"] == 1 and [t["name"] for t in snapshot["tables"]] == [names[winner]]
    assert len(access.store.history()) == 1
    assert _receipt_rows(access.store) == [(won["receipt"]["scope"], identities[winner])]

    def lookup(entry, identity):
        """The receipt through one entry's own scope, or None when that entry reports not_found."""
        if entry == "bridge":
            message = bridge.response(bridge.request(get, {"handle": handle, "operation_id": identity}))
            if "error" in message:
                assert message["error"]["code"] == "not_found"
                return None
            return message["result"]["receipt"]
        try:
            return access.get(identity)
        except OperationNotFound:
            return None

    assert lookup(winner, identities[winner]) == won["receipt"]
    assert lookup(loser, identities[loser]) is None  # the failed attempt left no receipt in its own scope
    assert lookup(loser, identities[winner]) is None  # and the winner's receipt belongs only to its scope

    # F11d on the same project, through both entries: a first write with a new UUID at the stale
    # revision conflicts, inserts no receipt and leaves nothing to look up.
    before = unchanged(access.store)
    stale = {entry: str(uuid4()) for entry in names}
    assert bridge.error(apply, {"handle": handle, "operation_id": stale["bridge"], "expected_revision": 0,
                                "commands": [{"op": "create_table", "name": "Stale bridge"}]})["code"] == "conflict"
    with pytest.raises(RevisionConflict):
        access.apply([{"op": "create_table", "name": "Stale peer"}], operation_id=stale["peer"], expected_revision=0)
    assert lookup("bridge", stale["bridge"]) is None and lookup("peer", stale["peer"]) is None
    assert unchanged(access.store) == before
    bridge.assert_clean()


def _stored_receipts(store):
    """Exact stored identities and bytes of every successful edit receipt (all scopes)."""
    with sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True) as db:
        return db.execute("SELECT scope, operation_id, base_revision, applied_revision, request, receipt, sha256 "
                          "FROM project_edit_operations ORDER BY applied_revision").fetchall()


@pytest.mark.parametrize("budget", ["count", "bytes_exhausted_before_write", "bytes_exceeded_by_new_edit"])
def test_bridge_and_peer_share_the_project_receipt_quota_without_evicting_original_receipts(
        access, inproc, monkeypatch, budget):
    """CP-0 F14 on one SQLite project: the strict local Bridge and the authenticated PeerProjects
    adapter share the project-wide receipt count and byte budgets (narrowed by monkeypatch only).

    "count" and "bytes_exhausted_before_write" are refused before any edit; "bytes_exceeded_by_new_edit"
    leaves the existing total below the budget, so the new edit is applied and then rolled back.
    """
    from suan.project import edit_operations as operations
    bridge = inproc()
    handle = bridge.call("project.open", {"directory": str(access.store.directory)})["project"]["handle"]
    apply, get = "project.edit_operations.apply_once", "project.edit_operations.get"
    local_request = {"handle": handle, "operation_id": str(uuid4()), "expected_revision": 0,
                     "commands": [{"op": "create_table", "name": "Bridge original"}]}
    local = bridge.call(apply, local_request)
    peer_request = {"commands": [{"op": "create_table", "name": "Peer original"}],
                    "operation_id": str(uuid4()), "expected_revision": 1}
    remote = access.apply(**peer_request)
    assert local["replayed"] is False and remote["replayed"] is False
    assert local["receipt"]["scope"] == "local" and remote["receipt"]["scope"] != "local"
    stored, before = _stored_receipts(access.store), unchanged(access.store)
    assert [row[:4] for row in stored] == [("local", local_request["operation_id"], 0, 1),
                                           (remote["receipt"]["scope"], peer_request["operation_id"], 1, 2)]
    total = sum(len(row[4].encode("utf-8")) + len(row[5].encode("utf-8")) for row in stored)
    if budget == "count":
        monkeypatch.setattr(operations, "MAX_OPERATIONS", 2)
        message = "receipt capacity is exhausted"
    elif budget == "bytes_exhausted_before_write":
        monkeypatch.setattr(operations, "MAX_TOTAL_BYTES", total)
        message = "receipt capacity is exhausted"
    else:
        monkeypatch.setattr(operations, "MAX_TOTAL_BYTES", total + 1)
        message = "receipts exceed their total byte budget"

    failed = {"bridge": str(uuid4()), "peer": str(uuid4())}
    error = bridge.error(apply, {"handle": handle, "operation_id": failed["bridge"], "expected_revision": 2,
                                 "commands": [{"op": "create_table", "name": "Bridge over quota"}]})
    assert error["code"] == "invalid_params" and message in error["message"]
    with pytest.raises(ProjectError, match=message):
        access.apply([{"op": "create_table", "name": "Peer over quota"}], operation_id=failed["peer"],
                     expected_revision=2)
    assert unchanged(access.store) == before and _stored_receipts(access.store) == stored
    assert access.store.info()["revision"] == 2
    assert bridge.error(get, {"handle": handle, "operation_id": failed["bridge"]})["code"] == "not_found"
    with pytest.raises(OperationNotFound):
        access.get(failed["peer"])

    # The original identities stay readable and exactly replayable in their own scopes.
    assert bridge.call(get, {"handle": handle, "operation_id": local_request["operation_id"]}) == {
        "receipt": local["receipt"]}
    assert access.get(peer_request["operation_id"]) == remote["receipt"]
    assert bridge.call(apply, local_request) == {"receipt": local["receipt"], "replayed": True}
    assert access.apply(**peer_request) == {"receipt": remote["receipt"], "replayed": True}
    assert unchanged(access.store) == before and _stored_receipts(access.store) == stored
    bridge.assert_clean()


def test_lost_reply_reconnect_and_authority_restart_keep_original_receipt_and_scope(access):
    from suan.peer.authority import PeerAuthority
    identity = str(uuid4())
    first = access.apply(operation_id=identity)
    assert first["replayed"] is False and first["receipt"]["commands"][0]["id"]
    assert first["receipt"]["scope"] != "local"
    access.store.apply([{"op": "create_table", "name": "Later local edit"}], expected_revision=1)
    before = unchanged(access.store)
    access.reconnect()
    assert access.get(identity) == first["receipt"]
    assert access.apply(operation_id=identity) == {**first, "replayed": True}
    access.authority = PeerAuthority(access.store.directory.parent / "authority", owner_id=access.owner_id)
    access.reconnect("d" * 64)
    assert access.get(identity) == first["receipt"]
    assert access.apply(operation_id=identity) == {**first, "replayed": True}
    assert unchanged(access.store) == before


def test_authenticated_retry_never_changes_original_request_or_cas(access):
    identity = str(uuid4())
    first = access.apply(operation_id=identity)
    before = unchanged(access.store)
    for commands, base in (([{"op": "create_table", "name": "Different request"}], 0), (None, 1)):
        with pytest.raises(RevisionConflict):
            access.apply(commands, operation_id=identity, expected_revision=base)
    missing = str(uuid4())
    with pytest.raises(RevisionConflict):
        access.apply(operation_id=missing, expected_revision=0)
    with pytest.raises(OperationNotFound):
        access.get(missing)
    assert access.get(identity) == first["receipt"] and unchanged(access.store) == before


def test_failed_receipt_lookup_records_revision_before_same_inode_restore(access):
    from suan.peer.authority import PeerDenied
    baseline = access.store.path.read_bytes()
    before = access.store.path.stat()
    access.store.apply([{"op": "create_table", "name": "Observed local edit"}], expected_revision=0)
    missing = str(uuid4())
    with pytest.raises(OperationNotFound):
        access.get(missing)  # The authorized lease has observed revision 1 even though this lookup failed.
    access.store.path.write_bytes(baseline)  # Real out-of-band in-place restore, preserving the inode.
    after = access.store.path.stat()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    with pytest.raises(PeerDenied):
        access.projects.catalog(access.context, access.project_id, **access.target)
    for call in (lambda: access.get(missing), lambda: access.apply(operation_id=missing)):
        with pytest.raises(PeerDenied):
            call()
    assert access.store.info()["revision"] == 0 and access.store.snapshot()["tables"] == []


def test_other_authenticated_caller_cannot_read_or_replay_first_callers_identity(access):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from suan.peer.authority import peer_id_for
    identity = str(uuid4())
    first = access.apply(operation_id=identity)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    peer_id = peer_id_for(public)
    access.authority.approve_peer(peer_id, public)
    grant = access.authority.grant(peer_id, access.project_id, ["project.read", "project.edit"])
    other = Access(access.authority, access.store, access.project_id, access.owner_id,
                   private, peer_id, grant, authenticated(access.authority, private, peer_id))
    with pytest.raises(OperationNotFound):
        other.get(identity)
    second = other.apply(operation_id=identity, expected_revision=1)
    assert second["replayed"] is False
    assert first["receipt"]["scope"] != second["receipt"]["scope"]
    assert access.get(identity) == first["receipt"] and other.get(identity) == second["receipt"]


def test_regrant_preserves_scope_but_read_only_grant_cannot_replay_a_write(access):
    from suan.peer.authority import PeerDenied
    identity = str(uuid4())
    first = access.apply(operation_id=identity)
    access.authority.revoke_grant(access.grant["grant_id"])
    access.grant = access.authority.grant(access.peer_id, access.project_id, ["project.read"])
    access.reconnect()
    before = unchanged(access.store)
    assert access.get(identity) == first["receipt"]
    assert access.projects.catalog(access.context, access.project_id, **access.target)["project"]["revision"] == 1
    with pytest.raises(PeerDenied):
        access.apply(operation_id=identity)
    assert unchanged(access.store) == before


@pytest.mark.parametrize("action", ["catalog", "read_table", "get", "apply_once"])
def test_revocation_rejects_existing_session_before_any_business_operation(access, action):
    from suan.peer.authority import PeerDenied
    identity = str(uuid4())
    first = access.apply(operation_id=identity)
    table = first["receipt"]["commands"][0]["id"]
    before = unchanged(access.store)
    access.authority.revoke_grant(access.grant["grant_id"])
    args = {"catalog": {}, "read_table": {"table_id": table, "expected_revision": 1},
            "get": {"operation_id": identity},
            "apply_once": {"commands": [{"op": "create_table", "name": "Peer table"}],
                           "operation_id": identity, "expected_revision": 0}}[action]
    with pytest.raises(PeerDenied):
        getattr(access.projects, action)(access.context, access.project_id, **access.target, **args)
    assert unchanged(access.store) == before


@pytest.mark.parametrize("field", ["grant_id", "database_generation"])
def test_wire_grant_and_generation_are_checked_even_for_existing_receipts(access, field):
    from suan.peer.authority import PeerDenied
    identity = str(uuid4())
    access.apply(operation_id=identity)
    target = {**access.target, field: str(uuid4())}
    before = unchanged(access.store)
    with pytest.raises(PeerDenied):
        access.projects.get(access.context, access.project_id, identity, **target)
    with pytest.raises(PeerDenied):
        access.projects.apply_once(access.context, access.project_id,
            [{"op": "create_table", "name": "Peer table"}], operation_id=identity, expected_revision=0, **target)
    assert unchanged(access.store) == before


@pytest.mark.parametrize("context", [None, {}, {"owner_id": "owner", "peer_id": "caller"}])
def test_only_authority_issued_authenticated_context_is_accepted(access, context):
    from suan.peer.authority import PeerDenied
    before = unchanged(access.store)
    with pytest.raises(PeerDenied):
        access.projects.catalog(context, access.project_id, **access.target)
    assert unchanged(access.store) == before


def test_disconnect_rejects_old_context_but_reauthentication_preserves_receipts(access):
    from suan.peer.authority import PeerDenied
    identity = str(uuid4())
    receipt = access.apply(operation_id=identity)["receipt"]
    access.authority.disconnect(access.context)
    with pytest.raises(PeerDenied):
        access.get(identity)
    access.reconnect()
    assert access.get(identity) == receipt


def test_workspace_restore_rotates_authority_generation_without_reusing_old_success(access, tmp_path):
    from suan.peer.authority import PeerDenied
    identity = str(uuid4())
    first = access.apply(operation_id=identity)
    state = {"format": "stk.desktop.workspace-state", "version": 1, "windows": [], "app": {}}
    exported = workspace_bundle.export_workspace(access.store.directory, tmp_path / "old.stkworkspace",
                                                 state=state, expected_revision=1)
    access.store.apply([{"op": "create_table", "name": "Later edit"}], expected_revision=1)
    imported = workspace_bundle.import_workspace(exported["path"], tmp_path / "restored",
                                                 expected_sha256=exported["sha256"])
    restored = ProjectStore(imported["project_directory"])
    assert restored.edit_operations.get(identity, scope=first["receipt"]["scope"]) == first["receipt"]
    old_target, old_context = access.target, access.context
    rebound = access.authority.rebind_project(access.project_id, restored.directory)
    assert rebound["database_generation"] != old_target["database_generation"]
    with pytest.raises(PeerDenied):
        access.get(identity)
    access.grant = access.authority.grant(access.peer_id, access.project_id, ["project.read", "project.edit"])
    access.reconnect()
    before = unchanged(restored)
    with pytest.raises(PeerDenied):
        access.projects.get(old_context, access.project_id, identity, **access.target)
    with pytest.raises(PeerDenied):
        access.projects.get(access.context, access.project_id, identity, **old_target)
    with pytest.raises(OperationNotFound):
        access.get(identity)
    with pytest.raises(RevisionConflict):
        access.apply(operation_id=identity)  # Keep the original revision, never infer success from revision 1.
    assert unchanged(restored) == before
    second = access.apply(operation_id=str(uuid4()), expected_revision=1)
    assert second["receipt"]["scope"] != first["receipt"]["scope"]
    assert restored.info()["revision"] == 2 and access.store.info()["revision"] == 2


def test_revoke_ack_waits_for_the_whole_authorized_store_call(access, monkeypatch):
    from suan.peer.authority import PeerDenied
    entered, release, revoking, revoked = (threading.Event() for _ in range(4))
    original = edit_operations.EditOperations.apply_once
    identity = str(uuid4())

    def paused(self, *args, **kwargs):
        entered.set()
        assert release.wait(5), "Timed out releasing the actual authorized SQLite edit"
        return original(self, *args, **kwargs)

    def revoke():
        revoking.set()
        access.authority.revoke_grant(access.grant["grant_id"])
        revoked.set()

    monkeypatch.setattr(edit_operations.EditOperations, "apply_once", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        editing = pool.submit(access.apply, operation_id=identity)
        assert entered.wait(5)
        revocation = pool.submit(revoke)
        try:
            assert revoking.wait(5) and not revoked.wait(0.10)
        finally:
            release.set()
        assert editing.result(timeout=5)["replayed"] is False
        revocation.result(timeout=5)
    assert revoked.is_set() and access.store.info()["revision"] == 1
    with pytest.raises(PeerDenied):
        access.get(identity)


@pytest.mark.parametrize("project_id", [None, "local-handle", "/tmp/private-project", "A" * 36, "x" * 10000])
def test_project_selector_is_a_canonical_uuid_never_a_path_or_handle(access, project_id):
    with pytest.raises(ProjectError, match="canonical UUID"):
        access.projects.catalog(access.context, project_id, **access.target)


def test_ungranted_canonical_project_id_is_not_an_open_by_identifier(access):
    from suan.peer.authority import PeerDenied
    with pytest.raises(PeerDenied):
        access.projects.catalog(access.context, str(uuid4()), **access.target)


def test_methods_do_not_accept_remote_identity_scope_path_handle_or_implicit_edit_identity(access):
    service = access.projects
    for action in ("catalog", "read_table", "apply_once", "get"):
        parameters = inspect.signature(getattr(service, action)).parameters
        assert not {"scope", "owner_id", "peer_id", "directory", "path", "handle"} & parameters.keys()
        assert parameters["grant_id"].default is inspect.Parameter.empty
        assert parameters["database_generation"].default is inspect.Parameter.empty
    for field in ("operation_id", "expected_revision"):
        args = {"operation_id": str(uuid4()), "expected_revision": 0}
        del args[field]
        with pytest.raises(TypeError):
            service.apply_once(access.context, access.project_id, [{"op": "create_table", "name": "x"}],
                               **access.target, **args)
    with pytest.raises(TypeError):
        service.catalog(access.context, access.project_id, scope="local", **access.target)


def test_shared_paging_and_serialized_response_budgets_are_not_relaxed(access, monkeypatch, inproc):
    """CP-0 F13: the same out-of-bounds reads fail on the authenticated peer adapter (ProjectError) and
    on the strict local Bridge (invalid_params), with no state change through either entry. The Bridge
    rejects limit 201/501 with its published params schema before dispatch; a continuation without
    expected_revision and the 8 MiB result budget fail in the shared store on both entries."""
    table, _, _ = schema(access)
    bridge = inproc()
    handle = bridge.call("project.open", {"directory": str(access.store.directory)})["project"]["handle"]
    before = unchanged(access.store)
    service, target = access.projects, access.target
    bounds = [("project.catalog", {"limit": 201}), ("project.catalog", {"offset": 1}),
              ("project.table.read", {"table_id": table, "expected_revision": 1, "limit": 501})]
    for call in (lambda: service.catalog(access.context, access.project_id, limit=201, **target),
                 lambda: service.catalog(access.context, access.project_id, offset=1, **target),
                 lambda: service.read_table(access.context, access.project_id, table, expected_revision=1,
                                             limit=501, **target)):
        with pytest.raises(ProjectError):
            call()
    for method, params in bounds:
        assert bridge.error(method, {"handle": handle, **params})["code"] == "invalid_params", (method, params)
    monkeypatch.setattr(catalog_module, "MAX_READ_BYTES", 64)
    for call in (lambda: service.catalog(access.context, access.project_id, **target),
                 lambda: service.read_table(access.context, access.project_id, table, expected_revision=1, **target)):
        with pytest.raises(ProjectError, match="Project read exceeds 8 MiB"):
            call()
    for method, params in (("project.catalog", {}), ("project.table.read", {"table_id": table, "expected_revision": 1})):
        error = bridge.error(method, {"handle": handle, **params})
        assert error["code"] == "invalid_params" and "Project read exceeds 8 MiB" in error["message"], method
    assert unchanged(access.store) == before
    bridge.assert_clean()


def test_original_core_command_and_utf8_request_limits_remain_atomic(access):
    table, field, records = schema(access)
    before = unchanged(access.store)
    cases = [([{"op": "create_table", "name": "x"}] * 1001, "1000 commands"),
             ([{"op": "set_cell", "table_id": table, "field_id": field,
                "record_id": records[0], "value": "字" * 90000}], "262144-byte limit"),
             ([{"op": "run", "command": "synthetic-command"}], "Unknown project command"),
             ([{"op": "model.generate"}], "Unknown project command")]
    for commands, message in cases:
        identity = str(uuid4())
        with pytest.raises(ProjectError, match=message):
            access.apply(commands, operation_id=identity, expected_revision=1)
        with pytest.raises(OperationNotFound):
            access.get(identity)
    assert unchanged(access.store) == before


def test_legacy_project_reads_remain_supported_without_implicit_format_upgrade(access, inproc):
    """CP-0 F15: a format-14 project stays readable through both entries; the receipt API needs an
    explicit upgrade (peer UnsupportedProjectFormat, Bridge unsupported) and nothing upgrades implicitly."""
    with sqlite3.connect(access.store.path) as db:
        db.execute("DROP TABLE project_edit_operations")
        db.execute("PRAGMA user_version=14")
    assert access.projects.catalog(access.context, access.project_id, **access.target)["format_version"] == 14
    bridge = inproc()
    handle = bridge.call("project.open", {"directory": str(access.store.directory)})["project"]["handle"]
    assert bridge.call("project.catalog", {"handle": handle})["format_version"] == 14
    before = access.store.snapshot(), access.store.history()
    with pytest.raises(UnsupportedProjectFormat):
        access.apply()
    with pytest.raises(UnsupportedProjectFormat):
        access.get(str(uuid4()))
    write = {"handle": handle, "operation_id": str(uuid4()), "expected_revision": 0,
             "commands": [{"op": "create_table", "name": "Bridge legacy write"}]}
    assert bridge.error("project.edit_operations.apply_once", write)["code"] == "unsupported"
    assert bridge.error("project.edit_operations.get",
                        {"handle": handle, "operation_id": write["operation_id"]})["code"] == "unsupported"
    assert (access.store.snapshot(), access.store.history()) == before
    assert access.store.info()["format_version"] == 14
    bridge.assert_clean()


# CP-0 F5b/F5c (docs/design/cloud-project-service.md): the two peer paths currently treat a physical hot
# rollback journal differently. These tests pin the CURRENT behavior of this base; they are not a cloud
# project ownership or recovery policy, which R2/R3 have not decided.


def _registry(access):
    """Byte digests of every file of the owner authority registry (rollback-journal mode, no WAL)."""
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(access.authority.directory.iterdir()) if path.is_file()}


def _registered_revision(access):
    with sqlite3.connect(access.authority.path.as_uri() + "?mode=ro", uri=True) as db:
        return db.execute("SELECT revision FROM projects WHERE project_id=?", (access.project_id,)).fetchone()[0]


def _hot_journal(access):
    """A real SQLite hot rollback journal from a killed apply_once (shared _spill), not a mocked error code.

    _spill's child process opens the store, forces cache spill, writes 800 uncommitted tables at revision 0
    and exits before commit. It already asserts the journal magic, the uncommitted rows in the database file
    and its growth. The killed operation used scope "local", so no peer scope could ever own its receipt;
    the receipt table must therefore be empty in every scope.
    """
    assert access.store.info()["revision"] == 0 and _registered_revision(access) == 0
    before = unchanged(access.store)
    operation, original = _spill(access.store)
    journal = access.store.path.with_name(access.store.path.name + "-journal")
    hot = _physical(access.store)
    assert set(original) == {str(access.store.path)} and set(hot) == {str(access.store.path), str(journal)}
    assert hot[str(access.store.path)] != original[str(access.store.path)]
    return operation, original, hot, before


@pytest.mark.parametrize("cached", [False, True], ids=["first_owner_observation", "cached_owner_store"])
def test_current_bound_owner_observation_refuses_a_physical_hot_journal_without_any_write(access, cached):
    """CURRENT behavior (CP-0 F5b): the owner's bound observation fails closed.

    bound_project uses _BoundProjectStore, whose read-only recovery hook refuses; the database, the hot
    journal and the authority registry keep their exact bytes, and the grant is not revoked.
    """
    from suan.peer.authority import PeerDenied
    generation = access.target["database_generation"]
    if cached:  # The same owner store object is reused for an unchanged generation, inode and directory.
        assert access.authority.bound_project(access.project_id, generation).info()["revision"] == 0
    _, _, hot, _ = _hot_journal(access)
    registry = _registry(access)
    with pytest.raises(PeerDenied, match="Bound project is unavailable") as refused:
        access.authority.bound_project(access.project_id, generation)
    assert "explicit local recovery" in str(refused.value.__context__)  # the recovery hook, not another check
    assert _physical(access.store) == hot and _registry(access) == registry
    assert _registered_revision(access) == 0
    with sqlite3.connect(access.authority.path.as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("SELECT active FROM grants WHERE grant_id=?",
                          (access.target["grant_id"],)).fetchone()[0] == 1


def test_current_peer_catalog_physically_recovers_the_preimage_without_a_receipt(access):
    """CURRENT behavior (CP-0 F5c): peer project methods open an ordinary ProjectStore.

    The authenticated catalog therefore lets SQLite roll back the hot journal (store recovery path) and
    returns the old revision and contents. The killed operation leaves no receipt in any scope; the grant
    and the registered revision watermark stay valid at revision 0.
    """
    operation, original, _, before = _hot_journal(access)
    page = access.projects.catalog(access.context, access.project_id, **access.target)
    assert page["project"]["revision"] == 0 and page["tables"] == [] and page["total"] == 0
    assert _physical(access.store) == original  # journal gone and database bytes equal to the preimage
    assert unchanged(access.store) == before and before[1] == [] and before[2] == 0
    with pytest.raises(OperationNotFound):
        access.store.edit_operations.get(operation, scope="local")
    with pytest.raises(OperationNotFound):
        access.get(operation)
    assert _registered_revision(access) == 0
    assert access.projects.catalog(access.context, access.project_id, **access.target)["project"]["revision"] == 0
