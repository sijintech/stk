"""Immutable analysis preparation, bounded sources and single-attempt lifecycle facts."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.graph.schema import graph_hash
from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project import analysis_runs as module
from suan.project.analyses import TABLE_ID, FIELD_IDS
from suan.project.analysis_runs import AnalysisRunNotFound
from suan.project.store import FORMAT_VERSION, UnsupportedProjectFormat


def document():
    return {"format": "stk.analysis-document/1", "graph": {"schema": "stk.graph/1",
        "nodes": [{"id": "source", "type": "missing.source.node@1", "params": {"binding": "data"}}],
        "outputs": {"view": "source.payload"}},
        "parameters": {"integer": 1, "float": 1.0, "nullable": None, "false": False}, "outputs": ["view"]}


@pytest.fixture
def model(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Analysis runs")
    file = store.directory / "场.vti"
    file.write_bytes(b"frozen sample")
    record_id = store.files.index([str(file)], expected_revision=0)["record_ids"][0]
    snapshot_id = store.snapshots.capture([record_id], expected_revision=1)["snapshot"]["id"]
    analysis_id = str(uuid4())
    store.analyses.create("Signed field", document(), analysis_id=analysis_id, expected_revision=2)
    return store, analysis_id, snapshot_id, record_id, file


def prepare(model, *, run_id=None, revision=3, bindings=None):
    store, analysis_id, snapshot_id, record_id, _ = model
    return store.analysis_runs.prepare(analysis_id, snapshot_id,
        {"data": {"field.vti": record_id}} if bindings is None else bindings,
        run_id=run_id or str(uuid4()), expected_revision=revision)


def claim(model, run):
    owner = str(uuid4())
    result, claimed = model[0].analysis_runs._claim(run["id"], executor_id=owner)
    assert claimed and result["status"] == "running"
    return owner


def result(run, *, errors=False):
    return {"directory": f".stk/analysis-runs/{run['id']}/result", "manifest_sha256": "a" * 64,
            "graph_hash": graph_hash(run["document"]["graph"]).removeprefix("sha256:"),
            "output_count": 1, "has_payload": True, "has_errors": errors, "size_bytes": 1000}


def test_prepare_freezes_typed_document_and_only_explicit_snapshot_metadata_without_io(model, monkeypatch):
    store, analysis_id, snapshot_id, record_id, file = model
    before, history = store.snapshot(), store.history()
    file.unlink()
    monkeypatch.setattr(store, "snapshot", lambda: pytest.fail("whole-project snapshot"))
    monkeypatch.setattr(type(store.snapshots), "resolve", lambda *a: pytest.fail("file IO"))
    run = prepare(model)
    assert set(run) == module._PLAN_KEYS | module._STATE_KEYS | {"plan_sha256"}
    assert run["source_revision"] == 3 and run["analysis_name"] == "Signed field"
    assert run["document"] == document()
    assert type(run["document"]["parameters"]["float"]) is float
    assert type(run["document"]["parameters"]["integer"]) is int
    assert run["bindings"] == {"data": {"field.vti": {"record_id": record_id,
        "sha256": hashlib.sha256(b"frozen sample").hexdigest(), "size": len(b"frozen sample")}}}
    assert run["profile"] == "desktop" and run["budget"] == module.BUDGET
    monkeypatch.undo()
    assert store.snapshot() == before and store.history() == history
    assert ProjectStore(store.directory).analysis_runs.get(run["id"]) == run


def test_identical_original_request_is_recoverable_after_definition_deleted_and_revision_advanced(model):
    store, analysis_id, *_ = model
    run = prepare(model)
    store.apply([{"op": "delete_record", "id": analysis_id}], expected_revision=3)
    assert prepare(model, run_id=run["id"]) == run
    with pytest.raises(RevisionConflict):
        prepare(model, run_id=run["id"], revision=4)
    with pytest.raises(RevisionConflict):
        prepare(model)
    assert store.analysis_runs.list()["runs"][0]["analysis_name"] == "Signed field"


def test_frozen_run_survives_undo_and_does_not_consume_redo(model):
    store = model[0]
    before = store.snapshot()
    run = prepare(model)
    store.undo(expected_revision=3)
    assert store.analysis_runs.get(run["id"]) == run
    assert store.snapshot()["edit_history"]["redo_revision"] == 3
    store.redo(expected_revision=4)
    assert store.snapshot()["tables"] == before["tables"]
    assert store.analysis_runs.get(run["id"]) == run


def test_prepare_concurrent_same_id_has_one_plan_and_one_event(model):
    identity, barrier = str(uuid4()), threading.Barrier(6)
    def work(_):
        barrier.wait()
        return prepare(model, run_id=identity)
    with ThreadPoolExecutor(max_workers=6) as pool:
        runs = list(pool.map(work, range(6)))
    assert all(run == runs[0] for run in runs)
    with sqlite3.connect(model[0].path) as db:
        assert db.execute("SELECT count(*) FROM analysis_run_plans").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM analysis_run_events").fetchone()[0] == 1


def test_claim_race_has_exactly_one_owner_and_terminal_retry_never_claims_again(model):
    store = model[0]
    run, barrier = prepare(model), threading.Barrier(6)
    def work(_):
        barrier.wait()
        return store.analysis_runs._claim(run["id"], executor_id=str(uuid4()))
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(work, range(6)))
    winners = [item for item, claimed in claims if claimed]
    assert len(winners) == 1
    owner = winners[0]["executor_id"]
    receipt = result(run)
    finished = store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=receipt)
    assert finished["status"] == "succeeded" and finished["finished_at"]
    assert store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=receipt) == finished
    assert store.analysis_runs._claim(run["id"], executor_id=str(uuid4())) == (finished, False)
    assert store.analysis_runs.cancel(run["id"]) == finished
    assert store.analysis_runs._recover(run["id"]) == finished
    with pytest.raises(RevisionConflict):
        store.analysis_runs._finish(run["id"], executor_id=owner, status="failed", error={"code": "failure", "message": "late"})


def test_prepared_cancel_has_no_executor_and_is_terminal(model):
    run = prepare(model)
    cancelled = model[0].analysis_runs.cancel(run["id"])
    assert cancelled["status"] == "cancelled" and cancelled["executor_id"] is None
    assert cancelled["cancel_requested_at"] and cancelled["finished_at"]
    assert model[0].analysis_runs.cancel(run["id"]) == cancelled
    assert model[0].analysis_runs._claim(run["id"], executor_id=str(uuid4())) == (cancelled, False)


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled", "unknown"])
def test_running_cancellation_retains_intent_for_every_confirmed_or_unknown_outcome(model, status):
    store, *_ = model
    run = prepare(model)
    owner = claim(model, run)
    cancelled = store.analysis_runs.cancel(run["id"])
    assert cancelled["status"] == "cancel_requested" and cancelled["finished_at"] is None
    assert store.analysis_runs.cancel(run["id"]) == cancelled
    kwargs = {"result": result(run)} if status == "succeeded" else {"error": {"code": "outcome", "message": "Outcome"}}
    finished = store.analysis_runs._finish(run["id"], executor_id=owner, status=status, **kwargs)
    assert finished["cancel_requested_at"] == cancelled["cancel_requested_at"]
    assert store.analysis_runs.get(run["id"]) == finished


def test_recovery_marks_unknown_without_replay_and_late_owner_cannot_publish(model):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    recovered = store.analysis_runs._recover(run["id"])
    assert recovered["status"] == "unknown" and recovered["error"]["code"] == "execution_interrupted"
    assert store.analysis_runs._recover(run["id"]) == recovered
    assert store.analysis_runs._claim(run["id"], executor_id=owner) == (recovered, False)
    with pytest.raises(RevisionConflict):
        store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=result(run))


def test_partial_archive_requires_failed_with_explicit_error_and_remains_readable(model):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    partial = result(run, errors=True)
    with pytest.raises(ProjectError):
        store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=partial)
    record = store.analysis_runs._finish(run["id"], executor_id=owner, status="failed", result=partial,
                                       error={"code": "output_failed", "message": "One requested output failed"})
    assert record["result"] == partial and store.analysis_runs.get(run["id"]) == record


def test_empty_outputs_and_unknown_node_are_saved_without_semantic_execution(model):
    store, identity, *_ = model
    doc = document()
    doc["outputs"] = []
    store.analyses.update(identity, "No outputs", doc, expected_revision=3)
    run = prepare(model, revision=4)
    assert run["document"]["outputs"] == []
    owner = claim(model, run)
    receipt = {**result(run), "output_count": 0, "has_payload": False}
    assert store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=receipt)["status"] == "succeeded"


@pytest.mark.parametrize("bindings", [None, [], {}, {"bad.name": {}}, {"data": {}}, {"": {"x": "x"}},
    {"Data": {"x": str(uuid4())}}, {"data-name": {"x": str(uuid4())}}, {"_data": {"x": str(uuid4())}},
    {"a": {"x": "x"}}, {"a": {"x": str(uuid4())}}, {"a": {"x": str(uuid4()).upper()}}])
def test_invalid_bindings_do_not_create_journal(model, bindings):
    store, analysis_id, snapshot_id, *_ = model
    with pytest.raises(ProjectError):
        store.analysis_runs.prepare(analysis_id, snapshot_id, bindings, run_id=str(uuid4()), expected_revision=3)
    assert store.analysis_runs.list()["runs"] == [] and store.info()["revision"] == 3


@pytest.mark.parametrize("path", ["../x", "/x", "x//y", "./x", "x/../y", "x\\y", "C:x", "NUL", "con.txt",
    "a/PRN.dat", "x.", "x ", "x?", "x\n", "x\0", "x/", "é" * 513, "x" * 256, "é" * 128, "\ud800"])
def test_portable_binding_paths_reject_escapes_and_unrepresentable_names(model, path):
    with pytest.raises(ProjectError):
        prepare(model, bindings={"data": {path: model[3]}})


@pytest.mark.parametrize("paths", [("a", "A"), ("a", "a/x"), ("a/x", "a"), ("é.vti", "e\u0301.vti")])
def test_binding_file_collisions_are_detected_on_all_platforms(model, paths):
    with pytest.raises(ProjectError, match="collide"):
        prepare(model, bindings={"data": {path: model[3] for path in paths}})


def test_binding_and_file_count_caps_allow_exact_limit_but_not_one_more(model):
    record = model[3]
    assert prepare(model, bindings={"data": {f"x{i}": record for i in range(100)}})["status"] == "prepared"
    for bindings in ({"data": {f"x{i}": record for i in range(101)}},
                     {f"data{i}": {"x": record} for i in range(33)},
                     {"data": {"x": record}, "DATA": {"x": record}}):
        with pytest.raises(ProjectError):
            prepare(model, bindings=bindings)


def test_logical_input_budget_counts_aliases_without_copying_large_file(model, monkeypatch):
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", len(b"frozen sample") * 2)
    assert prepare(model, bindings={"data": {"a": model[3], "b": model[3]}})["status"] == "prepared"
    with pytest.raises(ProjectError, match="logical input"):
        prepare(model, bindings={"data": {"a": model[3], "b": model[3], "c": model[3]}})


@pytest.mark.parametrize("revision", [True, -1, 2**63, 3.0, None])
def test_cas_revision_rejects_invalid_types_and_ranges(model, revision):
    with pytest.raises(ProjectError):
        prepare(model, revision=revision)


def test_owner_invalid_result_identity_and_counts_leave_running_unchanged(model):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    before = store.analysis_runs.get(run["id"])
    with pytest.raises(RevisionConflict):
        store.analysis_runs._finish(run["id"], executor_id=str(uuid4()), status="succeeded", result=result(run))
    for change in ({"graph_hash": "b" * 64}, {"graph_hash": "sha256:" + result(run)["graph_hash"]},
                   {"directory": "../elsewhere"}, {"manifest_sha256": "x"}, {"output_count": True},
                   {"output_count": 2}, {"output_count": 0}, {"has_payload": 1},
                   {"size_bytes": 0}, {"size_bytes": module.MAX_ARCHIVE_BYTES + 1}):
        with pytest.raises(ProjectError):
            store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result={**result(run), **change})
        assert store.analysis_runs.get(run["id"]) == before


def test_malformed_managed_definition_rejected_but_existing_historical_run_survives(model):
    store, identity, *_ = model
    run = prepare(model)
    store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                  "field_id": FIELD_IDS["format"], "value": "unknown"}], expected_revision=3)
    with pytest.raises(ProjectError, match="not readable"):
        prepare(model, revision=4)
    assert store.analysis_runs.get(run["id"]) == run


def test_plan_and_initial_event_are_atomic(model):
    store = model[0]
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON analysis_run_events BEGIN SELECT RAISE(ABORT,'blocked'); END")
    with pytest.raises(ProjectError, match="blocked"):
        prepare(model)
    assert store.analysis_runs.list() == {"runs": [], "next_offset": None}


def test_claim_and_settlement_failures_do_not_advance_lifecycle(model):
    store = model[0]
    run = prepare(model)
    def fail():
        with sqlite3.connect(store.path) as db:
            db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON analysis_run_events BEGIN SELECT RAISE(ABORT,'blocked'); END")
    def allow():
        with sqlite3.connect(store.path) as db:
            db.execute("DROP TRIGGER fail_event")
    fail()
    with pytest.raises(ProjectError, match="blocked"):
        store.analysis_runs._claim(run["id"], executor_id=str(uuid4()))
    assert store.analysis_runs.get(run["id"]) == run
    allow()
    owner = claim(model, run)
    running = store.analysis_runs.get(run["id"])
    fail()
    with pytest.raises(ProjectError, match="blocked"):
        store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=result(run))
    assert store.analysis_runs.get(run["id"]) == running


def test_publication_guard_observes_cancellation_after_sql_lock_wait_and_rolls_back(model):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    entered, cancelled = threading.Event(), threading.Event()
    class PublicationCancelled(Exception):
        pass
    def guard():
        if cancelled.is_set():
            raise PublicationCancelled
    def settle():
        entered.set()
        return store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=result(run), guard=guard)
    with sqlite3.connect(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(settle)
            assert entered.wait(2)
            cancelled.set()
            db.commit()
            with pytest.raises(PublicationCancelled):
                future.result(timeout=5)
    assert store.analysis_runs.get(run["id"])["status"] == "running"
    settled = store.analysis_runs._finish(run["id"], executor_id=owner, status="cancelled",
        error={"code": "cancelled", "message": "Cancelled before publication"})
    assert settled["status"] == "cancelled" and settled["result"] is None


def test_terminal_idempotent_retry_bypasses_new_publication_guard(model):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    settled = store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=result(run))
    def never():
        pytest.fail("terminal replay must not enter a new publication fence")
    assert store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=result(run), guard=never) == settled


@pytest.mark.parametrize("target", ["plan", "event", "bad_state_type", "duplicate_json_key", "wrong_snapshot_file"])
def test_stored_structure_and_snapshot_binding_checks_do_not_rely_on_checksum_alone(model, target):
    store = model[0]
    run = prepare(model)
    with sqlite3.connect(store.path) as db:
        if target in {"plan", "wrong_snapshot_file"}:
            raw, = db.execute("SELECT payload FROM analysis_run_plans").fetchone()
            plan = json.loads(raw)
            if target == "plan":
                plan["budget"]["max_seconds"] = True
            else:
                plan["bindings"]["data"]["field.vti"]["sha256"] = "f" * 64
            db.execute("UPDATE analysis_run_plans SET payload=?,sha256=?", (module._pack(plan, module.MAX_PLAN_BYTES), module._hash(plan)))
        else:
            raw, = db.execute("SELECT payload FROM analysis_run_events").fetchone()
            state = json.loads(raw)
            if target == "duplicate_json_key":
                raw = raw[:-1] + ',"status":"prepared"}'
            else:
                state["status"] = [] if target == "bad_state_type" else "running"
                raw = module._pack(state, module.MAX_EVENT_BYTES)
            digest = module._hash({"run_id": run["id"], "previous_sha256": "", "state": state})
            db.execute("UPDATE analysis_run_events SET payload=?,sha256=?", (raw, digest))
    with pytest.raises(ProjectError):
        store.analysis_runs.get(run["id"])


def test_preparation_and_claim_results_are_detached_copies(model):
    store = model[0]
    run = prepare(model)
    original = store.analysis_runs.get(run["id"])
    run["document"]["parameters"]["integer"] = 7
    run["bindings"]["data"]["field.vti"]["size"] = 999
    run["budget"]["max_seconds"] = 1
    assert store.analysis_runs.get(run["id"]) == original
    claimed, _ = store.analysis_runs._claim(run["id"], executor_id=str(uuid4()))
    claimed["document"]["outputs"] = []
    assert store.analysis_runs.get(run["id"])["document"]["outputs"] == ["view"]


@pytest.mark.parametrize("target", ["plan", "event", "request", "snapshot", "event_chain", "event_deleted"])
def test_read_and_idempotent_retry_reject_corruption(model, target):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    with sqlite3.connect(store.path) as db:
        if target == "plan":
            db.execute("UPDATE analysis_run_plans SET payload=replace(payload,'Signed field','Forged title')")
        elif target == "event":
            db.execute("UPDATE analysis_run_events SET payload=replace(payload,'running','unknown') WHERE status='running'")
        elif target == "request":
            db.execute("UPDATE analysis_run_plans SET request_sha256=?", ("b" * 64,))
        elif target == "snapshot":
            db.execute("UPDATE project_snapshots SET sha256=?", ("c" * 64,))
        elif target == "event_chain":
            db.execute("UPDATE analysis_run_events SET previous_sha256='' WHERE status='running'")
        else:
            db.execute("DELETE FROM analysis_run_events WHERE status='prepared'")
    for action in (lambda: store.analysis_runs.get(run["id"]), lambda: store.analysis_runs.list(),
                   lambda: prepare(model, run_id=run["id"]), lambda: store.analysis_runs.cancel(run["id"])):
        with pytest.raises(ProjectError):
            action()


def test_replacement_project_blocks_retained_executor_settlement(model, tmp_path):
    store = model[0]
    run = prepare(model)
    owner = claim(model, run)
    replacement = ProjectStore.create(tmp_path / "other", "Other")
    shutil.copyfile(replacement.path, store.path)
    with pytest.raises(ProjectError, match="replaced"):
        store.analysis_runs._finish(run["id"], executor_id=owner, status="succeeded", result=result(run))


def test_bounded_pagination_has_stable_order_without_large_fields(model):
    store = model[0]
    runs = [prepare(model) for _ in range(3)]
    first = store.analysis_runs.list(limit=2)
    second = store.analysis_runs.list(offset=first["next_offset"], limit=2)
    assert [r["id"] for r in first["runs"] + second["runs"]] == [r["id"] for r in runs]
    assert second["next_offset"] is None
    assert "document" not in first["runs"][0] and "bindings" not in first["runs"][0]
    for offset, limit in ((True, 1), (0, False), (-1, 1), (2**63, 1), (0, 0), (0, 101)):
        with pytest.raises(ProjectError):
            store.analysis_runs.list(offset=offset, limit=limit)
    with pytest.raises(AnalysisRunNotFound):
        store.analysis_runs.get(str(uuid4()))


def test_format8_requires_explicit_verified_backup_upgrade_and_preserves_undo_and_snapshots(model, tmp_path):
    store = model[0]
    with sqlite3.connect(store.path) as db:
        for table in ("project_archive", "workflow_run_events", "workflow_run_plans", "analysis_run_events", "analysis_run_plans"):
            db.execute(f"DROP TABLE {table}")  # a format-8 database (format 10 adds the workflow run tables)
        db.execute("PRAGMA user_version=8")
    before, history = store.snapshot(), store.history()
    with pytest.raises(UnsupportedProjectFormat, match="format 9"):
        prepare(model)
    assert store.snapshot() == before
    upgraded = store.upgrade(expected_revision=3)
    assert upgraded["format_version"] == FORMAT_VERSION == 11 and upgraded["revision"] == 4
    assert store.snapshot()["tables"] == before["tables"]
    assert store.snapshot()["edit_history"] == before["edit_history"]
    assert store.history()[:-1] == history
    backup = tmp_path / "restored"
    backup.mkdir()
    shutil.copyfile(upgraded["backup"]["path"], backup / "project.sqlite3")
    restored = ProjectStore(backup)
    assert restored.info()["format_version"] == 8 and restored.info()["revision"] == 3
    assert restored.analyses.get(model[1])["analysis"]["document"] == document()
    assert restored.snapshots.get(model[2])["id"] == model[2]
    with sqlite3.connect(restored.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'analysis_run_%'").fetchall() == []
    assert prepare(model, revision=4)["source_revision"] == 4


def test_format9_migration_failure_rolls_back_and_retains_verified_old_backup(model, monkeypatch):
    import suan.project.store as storage
    store = model[0]
    with sqlite3.connect(store.path) as db:
        for table in ("project_archive", "workflow_run_events", "workflow_run_plans", "analysis_run_events", "analysis_run_plans"):
            db.execute(f"DROP TABLE {table}")  # a format-8 database (format 10 adds the workflow run tables)
        db.execute("PRAGMA user_version=8")
    before = store.snapshot()
    monkeypatch.setattr(storage, "_DDL_V9", (*storage._DDL_V9, "bad SQL"))
    with pytest.raises(ProjectError):
        store.upgrade(expected_revision=3)
    assert store.snapshot() == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'analysis_run_%'").fetchall() == []
    backups = list((store.directory / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
