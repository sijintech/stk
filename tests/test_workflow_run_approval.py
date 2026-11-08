"""First-start approval binding of WorkflowRuns.start (CL-S2C-FIRST-CLAIM-06).

``approval`` is a precondition and audit record checked inside the same write transaction that appends
``started``: it never authenticates anyone and is never reusable. Runs use the local demo-synthetic
template only; nothing executes a step, contacts a Runtime or a model.
"""
import json
import multiprocessing
import os
from pathlib import Path
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import archive as archive_module

VOLUME = json.loads((Path(__file__).resolve().parents[1] / "suan" / "graph" / "presets" / "volume.json").read_text())


@pytest.fixture
def project(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Approvals")
    ids = {key: str(uuid4()) for key in ("cases", "temperature", "label", "analysis", "workflow")}
    ids["rows"] = [str(uuid4()) for _ in range(2)]
    commands = [{"op": "create_table", "id": ids["cases"], "name": "Cases"},
                {"op": "add_field", "id": ids["temperature"], "table_id": ids["cases"], "name": "T", "type": "number",
                 "unit": "K"},
                {"op": "add_field", "id": ids["label"], "table_id": ids["cases"], "name": "Label", "type": "text"}]
    for row, temperature in zip(ids["rows"], (300, 325)):
        commands += [{"op": "add_record", "id": row, "table_id": ids["cases"]},
                     {"op": "set_cell", "table_id": ids["cases"], "record_id": row, "field_id": ids["temperature"],
                      "value": temperature},
                     {"op": "set_cell", "table_id": ids["cases"], "record_id": row, "field_id": ids["label"],
                      "value": "viridis"}]
    revision = store.apply(commands, expected_revision=0)["revision"]
    revision = store.analyses.create("Temperature field", {"format": "stk.analysis-document/1", "graph": VOLUME["graph"],
                                     "parameters": {"path": "field.vtk"}, "outputs": ["view"]},
                                     analysis_id=ids["analysis"], expected_revision=revision)["revision"]
    steps = [{"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}},
             {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
              "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": ids["temperature"]}}},
             {"id": "temperature", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
              "inputs": {"data": {"from": "simulate.files"}},
              "parameters": {"colormap": {"$field": ids["label"]}, "opacity": [[0.0, 0.0], [1.0, 1.0]]}}]
    store.workflows.create("Scan", {"format": "stk.workflow/1", "steps": steps, "ui": {}}, workflow_id=ids["workflow"],
                           expected_revision=revision)
    return store, ids


def prepare(store, ids):
    return store.workflow_runs.prepare(ids["workflow"], [ids["rows"][0]], run_id=str(uuid4()),
                                       expected_revision=store.info()["revision"])


def approval_for(store, run_id, **changes):
    """What a decision layer would bind: stored plan/request hashes and the current project revision."""
    with store._connect() as db:
        plan_sha, request_sha = tuple(db.execute("SELECT sha256, request_sha256 FROM workflow_run_plans WHERE id=?",
                                                 (run_id,)).fetchone())
    value = {"approval_id": str(uuid4()), "plan_sha256": plan_sha, "request_sha256": request_sha,
             "expected_revision": store.info()["revision"]}
    value.update(changes)
    return value


def run_events(store, run_id):
    with store._connect() as db:
        return [event for event in store.workflow_runs._read(db, run_id)[1] if event["step"] == ""]


def started(store, run_id):
    return [event for event in run_events(store, run_id) if event["status"] == "started"]


# --- the first approved claim -----------------------------------------------------------------------


def test_first_approved_start_records_a_copy_of_the_approval(project):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    assert approval["plan_sha256"] == run["plan_sha256"]
    executor = str(uuid4())
    result = store.workflow_runs.start(run["id"], executor_id=executor, owner={"host": "h", "pid": 1}, approval=approval)
    assert result["status"] == "running" and result["executor_id"] == executor
    events = started(store, run["id"])
    assert len(events) == 1 and events[0]["approval"] == approval and events[0]["executor_id"] == executor
    # mutating the caller's envelope afterwards cannot change the saved event
    approval["approval_id"], approval["expected_revision"] = str(uuid4()), 999
    assert started(store, run["id"])[0]["approval"] != approval
    with store._connect() as db:  # the chain still verifies
        store.workflow_runs._read(db, run["id"])


def test_approved_start_does_not_change_the_editable_revision(project):
    store, ids = project
    run = prepare(store, ids)
    before = store.info()["revision"]
    store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=approval_for(store, run["id"]))
    assert store.info()["revision"] == before


# --- malformed or mismatched envelopes leave the log untouched ---------------------------------------


def _bad_envelopes(good):
    yield "list", []
    yield "tuple", tuple(good.items())
    yield "missing", {k: v for k, v in good.items() if k != "request_sha256"}
    yield "extra", {**good, "by": "someone"}
    yield "id_not_uuid", {**good, "approval_id": "not-a-uuid"}
    yield "id_uppercase", {**good, "approval_id": good["approval_id"].upper()}
    yield "id_int", {**good, "approval_id": 7}
    yield "sha_upper", {**good, "plan_sha256": good["plan_sha256"].upper()}
    yield "sha_short", {**good, "plan_sha256": good["plan_sha256"][:63]}
    yield "sha_bytes", {**good, "request_sha256": good["request_sha256"].encode()}
    yield "rev_bool", {**good, "expected_revision": True}
    yield "rev_float", {**good, "expected_revision": float(good["expected_revision"])}
    yield "rev_negative", {**good, "expected_revision": -1}
    yield "rev_str", {**good, "expected_revision": str(good["expected_revision"])}


def test_malformed_envelopes_are_refused_without_writing(project):
    store, ids = project
    run = prepare(store, ids)
    good = approval_for(store, run["id"])
    before = run_events(store, run["id"])
    for label, envelope in _bad_envelopes(good):
        with pytest.raises(ProjectError):
            store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=envelope)
        assert run_events(store, run["id"]) == before, label
    # the untouched run can still be started by the good approval
    assert store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=good)["status"] == "running"


@pytest.mark.parametrize("field", ["plan_sha256", "request_sha256", "expected_revision"])
def test_mismatched_envelopes_are_conflicts_without_writing(project, field):
    store, ids = project
    run = prepare(store, ids)
    good = approval_for(store, run["id"])
    wrong = {"plan_sha256": "0" * 64, "request_sha256": "f" * 64, "expected_revision": good["expected_revision"] + 1}
    before = run_events(store, run["id"])
    with pytest.raises(RevisionConflict):
        store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval={**good, field: wrong[field]})
    assert run_events(store, run["id"]) == before


def test_another_runs_hashes_do_not_approve_this_run(project):
    store, ids = project
    first, second = prepare(store, ids), prepare(store, ids)
    foreign = approval_for(store, second["id"])
    with pytest.raises(RevisionConflict, match="does not match"):
        store.workflow_runs.start(first["id"], executor_id=str(uuid4()), approval=foreign)
    assert started(store, first["id"]) == []


def test_revision_moved_after_approval_is_refused(project):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    store.apply([{"op": "set_cell", "table_id": ids["cases"], "record_id": ids["rows"][1], "field_id": ids["label"],
                  "value": "magma"}], expected_revision=store.info()["revision"])
    with pytest.raises(RevisionConflict, match="expected revision"):
        store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=approval)
    assert started(store, run["id"]) == []


# --- single use: never a restart under an approval ----------------------------------------------------


def test_approved_start_stop_then_approved_restart_is_denied(project):
    store, ids = project
    runs = store.workflow_runs
    run = prepare(store, ids)
    executor = str(uuid4())
    runs.start(run["id"], executor_id=executor, approval=approval_for(store, run["id"]))
    runs.stop(run["id"], executor_id=executor)
    for approval in (approval_for(store, run["id"]), started(store, run["id"])[0]["approval"]):  # fresh or replayed
        with pytest.raises(RevisionConflict, match="already been started"):
            runs.start(run["id"], executor_id=str(uuid4()), approval=approval)
    assert len(started(store, run["id"])) == 1 and runs.get(run["id"])["status"] == "stopped"


def test_manual_start_stop_then_approved_start_is_denied(project):
    store, ids = project
    runs = store.workflow_runs
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])  # decided before a person started it from the editor
    executor = str(uuid4())
    runs.start(run["id"], executor_id=executor)
    runs.stop(run["id"], executor_id=executor)
    with pytest.raises(RevisionConflict, match="already been started"):
        runs.start(run["id"], executor_id=str(uuid4()), approval=approval)
    assert len(started(store, run["id"])) == 1


def test_approved_start_of_a_running_run_is_refused(project):
    store, ids = project
    runs = store.workflow_runs
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    runs.start(run["id"], executor_id=str(uuid4()))
    with pytest.raises(RevisionConflict):
        runs.start(run["id"], executor_id=str(uuid4()), approval=approval)


def test_manual_restart_without_approval_is_unchanged(project):
    store, ids = project
    runs = store.workflow_runs
    run = prepare(store, ids)
    first = str(uuid4())
    runs.start(run["id"], executor_id=first, approval=approval_for(store, run["id"]))
    runs.stop(run["id"], executor_id=first)
    second = str(uuid4())
    restarted = runs.start(run["id"], executor_id=second)  # a person's explicit editor restart
    assert restarted["status"] == "running" and restarted["executor_id"] == second
    events = started(store, run["id"])
    assert len(events) == 2 and "approval" not in events[1]


# --- archive ------------------------------------------------------------------------------------------


def test_archived_run_is_refused_with_and_without_approval(project):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    store.archive.set([{"kind": "workflow_run", "id": run["id"]}], archived=True)
    for envelope in (None, approval):
        with pytest.raises(archive_module.Archived):
            store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=envelope)
    assert started(store, run["id"]) == []


def test_archive_is_rechecked_inside_the_claim_transaction(project, monkeypatch):
    """A run archived after the early check (simulated by skipping it) is still refused under the write lock."""
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    store.archive.set([{"kind": "workflow_run", "id": run["id"]}], archived=True)
    monkeypatch.setattr(archive_module.Archive, "require_active", lambda self, kind, object_id, action: None)
    with pytest.raises(archive_module.Archived):
        store.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=approval)
    assert started(store, run["id"]) == []


# --- concurrent claims --------------------------------------------------------------------------------


def test_independent_store_instances_cannot_both_claim_first_start(project):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    a, b = ProjectStore(store.directory), ProjectStore(store.directory)
    a.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval=approval)
    with pytest.raises(RevisionConflict):
        b.workflow_runs.start(run["id"], executor_id=str(uuid4()), approval={**approval, "approval_id": str(uuid4())})
    assert len(started(store, run["id"])) == 1


def _claim(directory, run_id, approval, gate, results):
    """Child process: wait for the shared gate, then try to claim the run once."""
    from suan.project import ProjectError as Error, ProjectStore as Store
    store = Store(directory)
    gate.wait(30)
    try:
        if approval is None:
            store.workflow_runs.start(run_id, executor_id=str(uuid4()))
        else:
            store.workflow_runs.start(run_id, executor_id=str(uuid4()), approval=approval)
        results.put(("ok", "approved" if approval else "manual", os.getpid()))
    except Error as exc:
        results.put(("refused", type(exc).__name__, str(exc)[:120]))


@pytest.mark.parametrize("mix", ["approved_only", "approved_against_manual"])
def test_cross_process_race_allows_exactly_one_first_claim(project, mix):
    """Real separate processes, separate SQLite connections, released together: one claim wins."""
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    context = multiprocessing.get_context("spawn")
    gate, results = context.Event(), context.Queue()
    envelopes = [{**approval, "approval_id": str(uuid4())} for _ in range(4)]
    if mix == "approved_against_manual":
        envelopes = envelopes[:2] + [None, None]
    processes = [context.Process(target=_claim, args=(str(store.directory), run["id"], envelope, gate, results))
                 for envelope in envelopes]
    for process in processes:
        process.start()
    gate.set()
    outcomes = [results.get(timeout=60) for _ in processes]
    for process in processes:
        process.join(30)
        assert process.exitcode == 0
    winners = [outcome for outcome in outcomes if outcome[0] == "ok"]
    assert len(winners) == 1, outcomes
    assert all(outcome[1] in ("RevisionConflict",) for outcome in outcomes if outcome[0] == "refused"), outcomes
    events = started(store, run["id"])
    assert len(events) == 1
    assert ("approval" in events[0]) == (winners[0][1] == "approved")
