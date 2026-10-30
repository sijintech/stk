"""Authenticated peer project operations use real grants and shared SQLite state."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import inspect
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


def test_shared_paging_and_serialized_response_budgets_are_not_relaxed(access, monkeypatch):
    table, _, _ = schema(access)
    before = unchanged(access.store)
    service, target = access.projects, access.target
    for call in (lambda: service.catalog(access.context, access.project_id, limit=201, **target),
                 lambda: service.catalog(access.context, access.project_id, offset=1, **target),
                 lambda: service.read_table(access.context, access.project_id, table, expected_revision=1,
                                             limit=501, **target)):
        with pytest.raises(ProjectError):
            call()
    monkeypatch.setattr(catalog_module, "MAX_READ_BYTES", 64)
    for call in (lambda: service.catalog(access.context, access.project_id, **target),
                 lambda: service.read_table(access.context, access.project_id, table, expected_revision=1, **target)):
        with pytest.raises(ProjectError, match="Project read exceeds 8 MiB"):
            call()
    assert unchanged(access.store) == before


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


def test_legacy_project_reads_remain_supported_without_implicit_format_upgrade(access):
    with sqlite3.connect(access.store.path) as db:
        db.execute("DROP TABLE project_edit_operations")
        db.execute("PRAGMA user_version=14")
    assert access.projects.catalog(access.context, access.project_id, **access.target)["format_version"] == 14
    before = access.store.snapshot(), access.store.history()
    with pytest.raises(UnsupportedProjectFormat):
        access.apply()
    with pytest.raises(UnsupportedProjectFormat):
        access.get(str(uuid4()))
    assert (access.store.snapshot(), access.store.history()) == before
    assert access.store.info()["format_version"] == 14
