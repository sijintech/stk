"""Explicit edit identities survive lost replies, crashes and later undo operations."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import edit_operations as operations
from suan.project import store as storage
from suan.project import workspace_bundle
from suan.project.edit_operations import OperationNotFound
from suan.project.store import UnsupportedProjectFormat


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


@pytest.fixture
def store(tmp_path):
    return ProjectStore.create(tmp_path / "project", "Atomic edits")


def apply(store, operation_id=None, *, expected_revision=None, commands=None, scope="local"):
    return store.edit_operations.apply_once(
        [{"op": "create_table", "name": "参数表"}] if commands is None else commands,
        operation_id=str(uuid4()) if operation_id is None else operation_id,
        expected_revision=store.info()["revision"] if expected_revision is None else expected_revision,
        scope=scope,
    )


def rows(store):
    with sqlite3.connect(store.path) as db:
        return db.execute("SELECT count(*) FROM project_edit_operations").fetchone()[0]


def unchanged(store):
    return store.snapshot(), store.history(), rows(store)


def test_receipt_binds_original_request_and_actual_generated_ids(store):
    identity = str(uuid4())
    commands = [{"op": "create_table", "name": "参数表"}]
    result = apply(store, identity, expected_revision=0, commands=commands)
    receipt = result["receipt"]
    assert result["replayed"] is False and commands == [{"op": "create_table", "name": "参数表"}]
    assert set(receipt) == {"format", "project_id", "scope", "operation_id", "request_sha256", "base_revision",
                            "applied_revision", "commands", "created_at", "sha256"}
    assert receipt["format"] == "stk.project-edit-receipt/1"
    assert receipt["project_id"] == store.info()["id"]
    assert receipt["operation_id"] == identity and receipt["scope"] == "local"
    assert (receipt["base_revision"], receipt["applied_revision"]) == (0, 1)
    assert receipt["commands"] == store.history()[0]["commands"]
    assert receipt["commands"][0]["id"] == store.snapshot()["tables"][0]["id"]
    request = {"project_id": receipt["project_id"], "scope": "local", "operation_id": identity,
               "expected_revision": 0, "commands": commands}
    assert receipt["request_sha256"] == checksum(request)
    assert receipt["sha256"] == checksum({k: v for k, v in receipt.items() if k != "sha256"})
    with sqlite3.connect(store.path) as db:
        original, saved = db.execute("SELECT request,receipt FROM project_edit_operations").fetchone()
    assert original.encode() == canonical(request) and saved.encode() == canonical(receipt)
    assert store.edit_operations.get(identity) == receipt


def test_lost_reply_reopen_undo_redo_and_new_branch_do_not_reexecute(store):
    identity = str(uuid4())
    first = apply(store, identity, expected_revision=0)
    reopened = ProjectStore(store.directory)
    assert apply(reopened, identity, expected_revision=0) == {**first, "replayed": True}
    reopened.undo(expected_revision=1)
    before = unchanged(reopened)
    assert reopened.snapshot()["tables"] == []
    assert apply(reopened, identity, expected_revision=0) == {**first, "replayed": True}
    assert unchanged(reopened) == before
    reopened.redo(expected_revision=2)
    assert reopened.edit_operations.get(identity) == first["receipt"]
    reopened.undo(expected_revision=3)
    reopened.apply([{"op": "create_table", "name": "New branch"}], expected_revision=4)
    assert reopened.snapshot()["edit_history"]["redo_revision"] is None
    before = unchanged(reopened)
    assert apply(reopened, identity, expected_revision=0) == {**first, "replayed": True}
    assert unchanged(reopened) == before and reopened.info()["revision"] == 5


@pytest.mark.parametrize("changed", [
    {"commands": [{"op": "create_table", "name": "Other"}]},
    {"expected_revision": 1},
    {"commands": [{"op": "bad"}]},
])
def test_same_identity_different_request_conflicts_before_rebasing(store, changed):
    identity = str(uuid4())
    apply(store, identity, expected_revision=0)
    before = unchanged(store)
    with pytest.raises(RevisionConflict, match="different request"):
        apply(store, identity, **{"expected_revision": 0, **changed})
    assert unchanged(store) == before


@pytest.mark.parametrize("original,value", [(1, 1.0), (1, True), (-0.0, 0.0)])
def test_request_digest_does_not_merge_equal_python_numbers_or_booleans(store, original, value):
    table, field, record = (str(uuid4()) for _ in range(3))
    store.apply([{"op": "create_table", "id": table, "name": "Values"},
                 {"op": "add_field", "id": field, "table_id": table, "name": "JSON", "type": "json"},
                 {"op": "add_record", "id": record, "table_id": table}], expected_revision=0)
    command = {"op": "set_cell", "table_id": table, "field_id": field, "record_id": record, "value": original}
    identity = str(uuid4())
    apply(store, identity, expected_revision=1, commands=[command])
    before = unchanged(store)
    with pytest.raises(RevisionConflict, match="different request"):
        apply(store, identity, expected_revision=1, commands=[{**command, "value": value}])
    assert unchanged(store) == before


def test_scope_names_separate_identical_operation_ids_without_using_sessions(store):
    identity = str(uuid4())
    first = apply(store, identity, expected_revision=0, scope="owner-a/client")
    second = apply(store, identity, expected_revision=1, scope="owner-b/client")
    assert second["receipt"]["commands"][0]["id"] != first["receipt"]["commands"][0]["id"]
    assert rows(store) == 2
    for scope, expected in (("owner-a/client", first), ("owner-b/client", second)):
        assert store.edit_operations.get(identity, scope=scope) == expected["receipt"]
    with pytest.raises(OperationNotFound):
        store.edit_operations.get(identity)


@pytest.mark.parametrize("identity", ["", "not-a-uuid", "A" * 36, "e69714e530254e98a86f4f7145a6a304",
                                      "E69714E5-3025-4E98-A86F-4F7145A6A304", None, 1])
def test_operation_identity_must_be_explicit_and_canonical(store, identity):
    before = unchanged(store)
    with pytest.raises(ProjectError, match="canonical UUID"):
        store.edit_operations.apply_once([{"op": "create_table", "name": "x"}],
                                         operation_id=identity, expected_revision=0)
    with pytest.raises(ProjectError, match="canonical UUID"):
        store.edit_operations.get(identity)
    assert unchanged(store) == before


@pytest.mark.parametrize("scope", ["", "汉", "a" * 257, "with space", "\0", "line\n", "\t", "\x7f", None, 1])
def test_invalid_scope_never_edits_or_creates_a_receipt(store, scope):
    before = unchanged(store)
    with pytest.raises(ProjectError, match="scope"):
        apply(store, scope=scope)
    with pytest.raises(ProjectError, match="scope"):
        store.edit_operations.get(str(uuid4()), scope=scope)
    assert unchanged(store) == before


def test_maximum_scope_and_missing_read_have_no_implicit_side_effects(store):
    before = unchanged(store)
    identity, scope = str(uuid4()), "x" * 256
    with pytest.raises(OperationNotFound):
        store.edit_operations.get(identity, scope=scope)
    assert unchanged(store) == before
    result = apply(store, identity, scope=scope)
    assert store.edit_operations.get(identity, scope=scope) == result["receipt"]


@pytest.mark.parametrize("commands", [[], [{"op": "bad"}], [{"op": "create_table", "name": "partial"}, {"op": "bad"}],
    [{"op": "create_table", "name": "x"}] * 1001, [{"op": "create_table", "name": "\ud800"}],
    [{"op": "set_cell", "value": float("nan")}], [{"op": "set_cell", "value": float("inf")}], [None]])
def test_invalid_commands_roll_back_everything(store, commands):
    before = unchanged(store)
    with pytest.raises(ProjectError):
        apply(store, commands=commands)
    assert unchanged(store) == before


def test_two_connections_same_identity_apply_once(store):
    identity, ready = str(uuid4()), threading.Barrier(2)

    def write(_):
        other = ProjectStore(store.directory)
        ready.wait(timeout=5)
        return apply(other, identity, expected_revision=0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert results[0]["receipt"] == results[1]["receipt"]
    assert store.info()["revision"] == 1 and rows(store) == 1 and len(store.history()) == 1


def test_two_different_operations_at_the_same_revision_have_one_winner(store):
    ready = threading.Barrier(2)

    def write(_):
        other = ProjectStore(store.directory)
        ready.wait(timeout=5)
        try:
            return apply(other, expected_revision=0)
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert sum(r is not None for r in results) == 1
    assert store.info()["revision"] == 1 and rows(store) == 1 and len(store.snapshot()["tables"]) == 1


def test_separate_processes_recover_the_same_success(store, tmp_path):
    identity, barrier = str(uuid4()), tmp_path / "start"
    code = """
import json, sys, time
from pathlib import Path
from suan.project import ProjectStore
store = ProjectStore(sys.argv[1])
while not Path(sys.argv[3]).exists(): time.sleep(0.01)
print(json.dumps(store.edit_operations.apply_once([{'op':'create_table','name':'shared'}],
      operation_id=sys.argv[2], expected_revision=0)), flush=True)
"""
    processes = [subprocess.Popen([sys.executable, "-c", code, str(store.directory), identity, str(barrier)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    try:
        barrier.write_bytes(b"go")
        results = []
        for process in processes:
            output, error = process.communicate(timeout=20)
            assert process.returncode == 0, error
            results.append(json.loads(output))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert results[0]["receipt"] == results[1]["receipt"]
    assert store.info()["revision"] == 1 and rows(store) == 1


@pytest.mark.parametrize("failure", ["insert", "commit"])
def test_receipt_insert_or_real_commit_failure_rolls_back_edit_history_and_ids(store, failure):
    identity = str(uuid4())
    with sqlite3.connect(store.path) as db:
        if failure == "insert":
            db.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON project_edit_operations
                          BEGIN SELECT RAISE(ABORT, 'receipt unavailable'); END""")
        else:
            db.execute("""CREATE TABLE deferred_guard (revision INTEGER REFERENCES changes(revision)
                          DEFERRABLE INITIALLY DEFERRED)""")
            db.execute("""CREATE TRIGGER reject_receipt AFTER INSERT ON project_edit_operations
                          BEGIN INSERT INTO deferred_guard VALUES (999999); END""")
    before = unchanged(store)
    with pytest.raises(ProjectError, match="receipt unavailable|FOREIGN KEY"):
        apply(store, identity, expected_revision=0)
    assert unchanged(store) == before
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER reject_receipt")
        if failure == "commit":
            assert db.execute("SELECT count(*) FROM deferred_guard").fetchone()[0] == 0
    assert apply(store, identity, expected_revision=0)["replayed"] is False


@pytest.mark.parametrize("phase", ["after_edit", "after_receipt", "after_commit"])
def test_process_exit_around_commit_never_leaves_a_partial_success(store, phase):
    identity = str(uuid4())
    if phase == "after_receipt":
        with sqlite3.connect(store.path) as db:
            db.execute("""CREATE TRIGGER crash_after_receipt AFTER INSERT ON project_edit_operations
                          BEGIN SELECT crash_now(); END""")
    code = """
from contextlib import contextmanager
import os, sys
from suan.project import ProjectStore
store = ProjectStore(sys.argv[1])
phase = sys.argv[3]
if phase == 'after_edit':
    original = store._apply
    def edit(db, *args):
        original(db, *args)
        os._exit(73)
    store._apply = edit
elif phase == 'after_receipt':
    original = store._connect
    @contextmanager
    def connection(*, write=False):
        with original(write=write) as db:
            if write: db.create_function('crash_now', 0, lambda: os._exit(74))
            yield db
    store._connect = connection
store.edit_operations.apply_once([{'op':'create_table','name':'crash-proof'}],
    operation_id=sys.argv[2], expected_revision=0)
os._exit(75)
"""
    result = subprocess.run([sys.executable, "-c", code, str(store.directory), identity, phase],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == {"after_edit": 73, "after_receipt": 74, "after_commit": 75}[phase], result.stderr
    reopened = ProjectStore(store.directory)
    if phase == "after_commit":
        receipt = reopened.edit_operations.get(identity)
        assert receipt["commands"] == reopened.history()[0]["commands"]
        assert reopened.info()["revision"] == 1 and rows(reopened) == 1
        assert reopened.edit_operations.apply_once([{"op": "create_table", "name": "crash-proof"}],
            operation_id=identity, expected_revision=0) == {"receipt": receipt, "replayed": True}
    else:
        assert reopened.info()["revision"] == 0 and reopened.history() == [] and rows(reopened) == 0
        assert reopened.snapshot()["tables"] == []
        with pytest.raises(OperationNotFound):
            reopened.edit_operations.get(identity)
        if phase == "after_receipt":
            with sqlite3.connect(store.path) as db:
                db.execute("DROP TRIGGER crash_after_receipt")
        assert apply(reopened, identity, expected_revision=0)["replayed"] is False


def test_request_and_receipt_byte_budgets_are_utf8_and_atomic(store, monkeypatch):
    assert operations.MAX_REQUEST_BYTES == 256 * 1024
    assert operations.MAX_RECEIPT_BYTES == 512 * 1024
    identity = str(uuid4())
    command = {"op": "create_table", "name": "汉" * 20}
    request = {"project_id": store.info()["id"], "scope": "local", "operation_id": identity,
               "expected_revision": 0, "commands": [command]}
    exact = len(canonical(request))
    before = unchanged(store)
    monkeypatch.setattr(operations, "MAX_REQUEST_BYTES", exact - 1)
    with pytest.raises(ProjectError, match="request exceeds"):
        apply(store, identity, expected_revision=0, commands=[command])
    assert unchanged(store) == before
    monkeypatch.setattr(operations, "MAX_REQUEST_BYTES", exact)
    monkeypatch.setattr(operations, "MAX_RECEIPT_BYTES", exact)
    with pytest.raises(ProjectError, match="receipt exceeds"):
        apply(store, identity, expected_revision=0, commands=[command])
    assert unchanged(store) == before
    monkeypatch.setattr(operations, "MAX_RECEIPT_BYTES", 512 * 1024)
    assert apply(store, identity, expected_revision=0, commands=[command])["replayed"] is False


def test_actual_request_budget_rejects_a_large_valid_json_cell_without_editing(store):
    table, field, record = (str(uuid4()) for _ in range(3))
    store.apply([{"op": "create_table", "id": table, "name": "Values"},
                 {"op": "add_field", "id": field, "table_id": table, "name": "JSON", "type": "json"},
                 {"op": "add_record", "id": record, "table_id": table}], expected_revision=0)
    before = unchanged(store)
    with pytest.raises(ProjectError, match="262144-byte"):
        apply(store, commands=[{"op": "set_cell", "table_id": table, "field_id": field,
                                "record_id": record, "value": "汉" * 90000}])
    assert unchanged(store) == before


@pytest.mark.parametrize("budget", ["count", "bytes"])
def test_total_receipt_limits_never_evict_old_identities_and_roll_back_new_edits(store, monkeypatch, budget):
    assert operations.MAX_OPERATIONS == 10000 and operations.MAX_TOTAL_BYTES == 64 * 1024 * 1024
    identity = str(uuid4())
    first = apply(store, identity)
    before = unchanged(store)
    if budget == "count":
        monkeypatch.setattr(operations, "MAX_OPERATIONS", 1)
    else:
        with sqlite3.connect(store.path) as db:
            total = db.execute("SELECT sum(length(CAST(request AS BLOB))+length(CAST(receipt AS BLOB))) "
                               "FROM project_edit_operations").fetchone()[0]
        monkeypatch.setattr(operations, "MAX_TOTAL_BYTES", total + 1)
    with pytest.raises(ProjectError, match="capacity|total byte budget"):
        apply(store)
    assert unchanged(store) == before
    assert apply(store, identity, expected_revision=0) == {**first, "replayed": True}
    assert store.edit_operations.get(identity) == first["receipt"]


@pytest.mark.parametrize("column,value", [
    ("request_sha256", "0" * 64), ("sha256", "0" * 64), ("request", "{}"), ("receipt", "{}"),
    ("receipt", '{"format":1,"format":2}'), ("request", "{"), ("created_at", "not-a-time"),
])
def test_damaged_stored_binding_is_not_returned_or_overwritten(store, column, value):
    identity = str(uuid4())
    apply(store, identity)
    with sqlite3.connect(store.path) as db:
        db.execute(f"UPDATE project_edit_operations SET {column}=?", (value,))
    before = unchanged(store)
    for call in (lambda: store.edit_operations.get(identity), lambda: apply(store, identity, expected_revision=0)):
        with pytest.raises(ProjectError, match="Stored edit operation receipt is invalid"):
            call()
    assert unchanged(store) == before


@pytest.mark.parametrize("damage", ["oversize", "duplicate", "nonfinite", "different"])
def test_damaged_or_oversized_history_is_bounded_and_rejected_without_changes(store, damage):
    identity = str(uuid4())
    apply(store, identity)
    value = {"oversize": " " * (operations.MAX_RECEIPT_BYTES + 1),
             "duplicate": '[{"op":"create_table","op":"create_table","name":"参数表"}]',
             "nonfinite": '[{"op":"create_table","name":NaN}]', "different": "[]"}[damage]
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE changes SET commands=? WHERE revision=1", (value,))
        before = db.execute("SELECT request,receipt FROM project_edit_operations").fetchone()
    for call in (lambda: store.edit_operations.get(identity), lambda: apply(store, identity, expected_revision=0)):
        with pytest.raises(ProjectError, match="Stored edit operation receipt is invalid"):
            call()
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT request,receipt FROM project_edit_operations").fetchone() == before
        assert db.execute("SELECT commands FROM changes WHERE revision=1").fetchone()[0] == value
    assert store.info()["revision"] == 1 and len(store.snapshot()["tables"]) == 1


def test_matching_receipt_hash_with_changed_commands_still_requires_original_history(store):
    identity = str(uuid4())
    receipt = apply(store, identity)["receipt"]
    receipt["commands"][0]["id"] = str(uuid4())
    receipt["sha256"] = checksum({k: v for k, v in receipt.items() if k != "sha256"})
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_edit_operations SET receipt=?, sha256=?",
                   (canonical(receipt).decode(), receipt["sha256"]))
    before = unchanged(store)
    with pytest.raises(ProjectError, match="Stored edit operation receipt is invalid"):
        store.edit_operations.get(identity)
    assert unchanged(store) == before


def old14(store):
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE project_edit_operations")
        db.execute("PRAGMA user_version=14")


def test_format14_stays_readable_and_writable_but_new_api_requires_explicit_upgrade(store, tmp_path):
    old14(store)
    store.apply([{"op": "create_table", "name": "Keep"}], expected_revision=0)
    before = store.snapshot()
    for call in (lambda: store.edit_operations.get(str(uuid4())), lambda: apply(store)):
        with pytest.raises(UnsupportedProjectFormat, match="format 15"):
            call()
    assert store.info()["format_version"] == 14 and store.snapshot() == before
    assert not (store.directory / "backups").exists()
    upgraded = store.upgrade(expected_revision=1)
    assert upgraded["format_version"] == 15 and upgraded["revision"] == 2
    assert upgraded["backup"]["format_version"] == 14
    restored = tmp_path / "backup"
    restored.mkdir()
    shutil.copyfile(upgraded["backup"]["path"], restored / storage.DATABASE_NAME)
    backup = ProjectStore(restored)
    assert backup.snapshot() == before
    store.undo(expected_revision=2)
    assert store.info()["format_version"] == 15 and store.snapshot()["tables"] == []
    assert apply(store, expected_revision=3)["receipt"]["applied_revision"] == 4


def test_failed_upgrade_keeps_old_database_and_verified_backup(store, monkeypatch):
    old14(store)
    before = store.snapshot()
    monkeypatch.setattr(storage, "_DDL_V15", (*storage._DDL_V15, "NOT VALID SQL"))
    with pytest.raises(ProjectError):
        store.upgrade(expected_revision=0)
    assert store.info()["format_version"] == 14 and store.snapshot() == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='project_edit_operations'").fetchone() is None
    backups = list((store.directory / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14


def test_backup_and_portable_workspace_preserve_original_receipts(store, tmp_path):
    identity = str(uuid4())
    first = apply(store, identity, scope="owner/client")
    backup_info = store.backup()
    backup_path = tmp_path / "backup"
    backup_path.mkdir()
    shutil.copyfile(backup_info["path"], backup_path / storage.DATABASE_NAME)
    backed = ProjectStore(backup_path)
    assert backed.edit_operations.get(identity, scope="owner/client") == first["receipt"]
    state = {"format": "stk.desktop.workspace-state", "version": 1, "windows": [], "app": {}}
    exported = workspace_bundle.export_workspace(store.directory, tmp_path / "edits.stkworkspace", state=state,
                                                expected_revision=1)
    imported = workspace_bundle.import_workspace(exported["path"], tmp_path / "imported",
                                                 expected_sha256=exported["sha256"])
    copied = ProjectStore(imported["project_directory"])
    assert copied.edit_operations.get(identity, scope="owner/client") == first["receipt"]
    before = unchanged(copied)
    assert apply(copied, identity, expected_revision=0, scope="owner/client") == {**first, "replayed": True}
    assert unchanged(copied) == before


def test_replaced_database_identity_cannot_inherit_old_store_operation_access(store, tmp_path):
    identity = str(uuid4())
    apply(store, identity)
    other = ProjectStore.create(tmp_path / "other", "Other")
    shutil.copyfile(other.path, store.path)
    with pytest.raises(ProjectError, match="replaced"):
        store.edit_operations.get(identity)


_SPILL_COMMANDS = [{"op": "create_table", "name": f"hot-spill-table-{i:04d}-" + "x" * 120} for i in range(800)]


def _physical(store):
    paths = [store.path, store.path.with_name(store.path.name + "-journal")]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.exists()}


def _spill(store, *, phase="after_edit", foreign=False):
    """Force a real hot rollback journal, including committed-file page spill."""
    identity = str(uuid4())
    request = {"project_id": store.info()["id"], "scope": "local", "operation_id": identity,
               "expected_revision": 0, "commands": _SPILL_COMMANDS}
    assert len(canonical(request)) < operations.MAX_REQUEST_BYTES
    if foreign:
        with sqlite3.connect(store.path) as db:
            db.execute("PRAGMA application_id=0")
    before = _physical(store)
    baseline_size = store.path.stat().st_size
    code = """
from contextlib import contextmanager
import json, os, sqlite3, sys
from pathlib import Path
from suan.project import ProjectStore
commands = [{'op':'create_table','name':f'hot-spill-table-{i:04d}-'+'x'*120} for i in range(800)]
directory, identity, phase, foreign = sys.argv[1:]
if foreign == 'yes':
    db = sqlite3.connect(str(Path(directory)/'project.sqlite3'), isolation_level=None)
    db.execute('PRAGMA cache_size=5'); db.execute('PRAGMA cache_spill=ON'); db.execute('BEGIN IMMEDIATE')
    for index, command in enumerate(commands): db.execute('INSERT INTO tables VALUES (?,?)',(str(index),command['name']))
    print(json.dumps({'cache_size':5,'foreign':True}), flush=True)
    os._exit(73)
store = ProjectStore(directory)
connection = store._connect
@contextmanager
def small_cache(*, write=False):
    with connection(write=write) as db:
        if write:
            db.execute('PRAGMA cache_size=5'); db.execute('PRAGMA cache_spill=ON')
        yield db
store._connect = small_cache
original = store._apply
def edit(db, *args):
    result = original(db, *args)
    if phase == 'after_edit':
        print(json.dumps({'cache_size':db.execute('PRAGMA cache_size').fetchone()[0],
              'cache_spill':db.execute('PRAGMA cache_spill').fetchone()[0]}), flush=True)
        os._exit(73)
    return result
store._apply = edit
store.edit_operations.apply_once(commands, operation_id=identity, expected_revision=0)
os._exit(75)
"""
    result = subprocess.run([sys.executable, "-c", code, str(store.directory), identity, phase,
                             "yes" if foreign else "no"], capture_output=True, text=True, timeout=30)
    assert result.returncode == (75 if phase == "after_commit" else 73), result.stderr
    assert b"hot-spill-table-" in store.path.read_bytes()  # Uncommitted rows reached the actual DB file.
    if phase == "after_edit":
        journal = store.path.with_name(store.path.name + "-journal")
        assert journal.exists() and journal.read_bytes()[:8] == bytes.fromhex("d9d505f920a163d7")
        assert store.path.stat().st_size > baseline_size
        settings = json.loads(result.stdout)
        assert settings["cache_size"] == 5
    return identity, before


@pytest.mark.parametrize("fresh", [False, True])
def test_forced_spill_recovers_on_normal_fresh_or_existing_store_reads(store, fresh):
    identity, before = _spill(store)
    assert _physical(store) != before
    reopened = ProjectStore(store.directory) if fresh else store
    with pytest.raises(OperationNotFound):
        reopened.edit_operations.get(identity)
    assert reopened.info()["revision"] == 0 and reopened.history() == [] and reopened.snapshot()["tables"] == []
    assert rows(reopened) == 0 and _physical(reopened) == before
    assert apply(reopened, identity, commands=_SPILL_COMMANDS, expected_revision=0)["replayed"] is False
    assert reopened.info()["revision"] == 1 and len(reopened.snapshot()["tables"]) == 800


def test_forced_spill_after_commit_returns_the_original_complete_success(store, monkeypatch):
    identity, _ = _spill(store, phase="after_commit")
    connection, opened = sqlite3.connect, []

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        return connection(database, *args, **kwargs)

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    reopened = ProjectStore(store.directory)
    first = reopened.edit_operations.get(identity)
    assert first["applied_revision"] == 1 and len(first["commands"]) == 800
    assert opened == [store.path.as_uri() + "?mode=ro"] * 2
    before = _physical(reopened)
    assert apply(reopened, identity, commands=_SPILL_COMMANDS, expected_revision=0) == {
        "receipt": first, "replayed": True}
    assert _physical(reopened) == before and reopened.info()["revision"] == 1
    assert not any("mode=rwc" in uri for uri in opened)
    # Explicit replay uses the ordinary write connection, but opening/reading needs no recovery.
    assert opened[2] == store.path.as_uri() + "?mode=rw"


def test_recovery_connection_is_query_only_and_original_read_reopens_readonly(store, monkeypatch):
    identity, before = _spill(store)
    connection, opened, query_flags = sqlite3.connect, [], []
    check = store._check_database

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        return connection(database, *args, **kwargs)

    def checked(db, application_id):
        flag = db.execute("PRAGMA query_only").fetchone()[0]
        query_flags.append(flag)
        if flag:
            with pytest.raises(sqlite3.OperationalError) as failure:
                db.execute("UPDATE project SET name='forbidden'")
            assert failure.value.sqlite_errorcode == sqlite3.SQLITE_READONLY
        check(db, application_id)

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    monkeypatch.setattr(store, "_check_database", checked)
    with pytest.raises(OperationNotFound):
        store.edit_operations.get(identity)
    assert opened == [store.path.as_uri() + suffix for suffix in ("?mode=ro", "?mode=rw", "?mode=ro")]
    assert query_flags == [1, 0] and _physical(store) == before


def test_non_stk_hot_journal_is_refused_before_any_writable_connection(store, monkeypatch):
    _spill(store, foreign=True)
    before = _physical(store)
    connection, opened = sqlite3.connect, []

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        return connection(database, *args, **kwargs)

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    with pytest.raises(ProjectError, match="STK database header"):
        ProjectStore(store.directory)
    assert opened == [store.path.as_uri() + "?mode=ro"] and _physical(store) == before


def test_unavailable_recovery_access_preserves_the_actual_hot_journal(store, monkeypatch):
    identity, _ = _spill(store)
    before = _physical(store)
    connection, opened = sqlite3.connect, []

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        if "mode=rw" in str(database):
            error = sqlite3.OperationalError("unable to open database file")
            error.sqlite_errorcode = sqlite3.SQLITE_CANTOPEN
            raise error
        return connection(database, *args, **kwargs)

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    with pytest.raises(ProjectError, match="writable database/directory access and a recovery lock"):
        store.edit_operations.get(identity)
    assert opened == [store.path.as_uri() + "?mode=ro", store.path.as_uri() + "?mode=rw"]
    assert _physical(store) == before


def test_final_lstat_failure_after_recovery_close_is_normalized_without_retrying(store, monkeypatch):
    identity, before = _spill(store)
    connection, opened, closed, faults = sqlite3.connect, [], [], []
    path_type, lstat = type(store.path), type(store.path).lstat

    class RecoveryConnection(sqlite3.Connection):
        def close(self):
            super().close()
            closed.append(True)

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        if "mode=rw" in str(database):
            kwargs["factory"] = RecoveryConnection
        return connection(database, *args, **kwargs)

    def final_lstat(path, *args, **kwargs):
        if path == store.path and closed:
            faults.append(True)
            raise PermissionError("injected final lstat failure")
        return lstat(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("A failed recovery identity check must not resume reads or replay edits")

    operation = store.edit_operations
    with monkeypatch.context() as patch:
        patch.setattr(storage.sqlite3, "connect", connect)
        patch.setattr(path_type, "lstat", final_lstat)
        patch.setattr(store, "_apply", forbidden)
        patch.setattr(operation, "_lookup", forbidden)
        with pytest.raises(ProjectError, match="Cannot recover the unfinished project transaction.*"
                           "injected final lstat failure") as failure:
            operation.get(identity)
        assert type(failure.value) is ProjectError
        assert closed == [True] and faults == [True]
        assert opened == [store.path.as_uri() + suffix for suffix in ("?mode=ro", "?mode=rw")]
    # SQLite physically recovered before the injected check failed; no business
    # transaction or requested read was retried, and a later explicit read is safe.
    assert _physical(store) == before
    assert store.info()["revision"] == 0 and store.history() == [] and store.snapshot()["tables"] == []
    assert rows(store) == 0
    with pytest.raises(OperationNotFound):
        store.edit_operations.get(identity)


@pytest.mark.parametrize("code", [sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_CANTOPEN])
def test_ordinary_sqlite_errors_do_not_open_a_recovery_connection(store, monkeypatch, code):
    before, opened = _physical(store), []

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        error = sqlite3.OperationalError("ordinary SQLite failure")
        error.sqlite_errorcode = code
        raise error

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    with pytest.raises(ProjectError, match="Cannot access project database: ordinary SQLite failure"):
        store.info()
    assert opened == [store.path.as_uri() + "?mode=ro"] and _physical(store) == before


def test_healthy_readonly_connection_does_not_attempt_writable_access(store, monkeypatch):
    before = _physical(store)
    connection, opened = sqlite3.connect, []

    def connect(database, *args, **kwargs):
        opened.append(str(database))
        assert "mode=ro" in str(database)
        return connection(database, *args, **kwargs)

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    assert ProjectStore(store.directory).info()["revision"] == 0
    assert opened == [store.path.as_uri() + "?mode=ro"] * 2 and _physical(store) == before


def test_readonly_rollback_after_connection_is_yielded_is_not_recovered(store, monkeypatch):
    before, recoveries = _physical(store), []
    monkeypatch.setattr(store, "_recover_readonly_database", lambda: recoveries.append(True))
    with pytest.raises(ProjectError, match="Cannot access project database: caller failure"):
        with store._connect():
            error = sqlite3.OperationalError("caller failure")
            error.sqlite_errorcode = 776
            raise error
    assert recoveries == [] and _physical(store) == before


def test_initial_hot_journal_recovery_is_attempted_at_most_once(store, monkeypatch):
    identity, _ = _spill(store)
    before, recoveries = _physical(store), []
    # Leave the actual hot journal in place: both read attempts receive real code 776.
    monkeypatch.setattr(store, "_recover_readonly_database", lambda: recoveries.append(True))
    with pytest.raises(ProjectError, match="Cannot access project database"):
        store.edit_operations.get(identity)
    assert recoveries == [True] and _physical(store) == before


def test_recovery_header_is_bounded_and_rejects_file_identity_change(store, monkeypatch):
    before, reads = _physical(store), []
    read, identity = storage.os.read, storage._recovery_identity

    def bounded(fd, size):
        reads.append(size)
        return read(fd, size)

    monkeypatch.setattr(storage.os, "read", bounded)
    expected = identity(store.path)
    assert storage._recovery_header(store.path) == expected and reads == [100]
    seen = []

    def replaced(path):
        seen.append(True)
        return expected if len(seen) == 1 else (expected[0], expected[1] + 1)

    monkeypatch.setattr(storage, "_recovery_identity", replaced)
    with pytest.raises(ProjectError, match="changed while checking its recovery header"):
        storage._recovery_header(store.path)
    assert _physical(store) == before


def test_recovery_header_rejects_nonordinary_files_before_reading(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A nonordinary recovery file must not be opened")

    monkeypatch.setattr(storage.os, "open", forbidden)
    with pytest.raises(ProjectError, match="non-ordinary project database"):
        storage._recovery_header(tmp_path)
