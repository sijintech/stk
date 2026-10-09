"""Per-row workflow runs: frozen plans, numbered attempts and an unbroken log (no execution here)."""
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from suan.graph.schema import canonical_json
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.analysis_runs import effective_parameters
from suan.project.store import UnsupportedProjectFormat
from suan.project.workflow_runs import WorkflowRunNotFound
from suan.workflows import muferro

VOLUME = json.loads((Path(__file__).resolve().parents[1] / "suan" / "graph" / "presets" / "volume.json").read_text())


@pytest.fixture
def project(tmp_path):
    """Cases (temperature in K, a text label, an energy in eV) with three rows, the volume analysis and a
    workflow cases -> simulate (demo-synthetic/1, temperature per row) -> temperature analysis."""
    store = ProjectStore.create(tmp_path / "project", "Runs")
    ids = {key: str(uuid4()) for key in ("cases", "temperature", "label", "energy", "analysis", "workflow")}
    ids["rows"] = [str(uuid4()) for _ in range(3)]
    commands = [{"op": "create_table", "id": ids["cases"], "name": "Cases"},
                {"op": "add_field", "id": ids["temperature"], "table_id": ids["cases"], "name": "T", "type": "number", "unit": "K"},
                {"op": "add_field", "id": ids["label"], "table_id": ids["cases"], "name": "Label", "type": "text"},
                {"op": "add_field", "id": ids["energy"], "table_id": ids["cases"], "name": "E", "type": "number", "unit": "eV"}]
    for row, temperature in zip(ids["rows"], (300, 325, 350)):
        commands += [{"op": "add_record", "id": row, "table_id": ids["cases"]},
                     {"op": "set_cell", "table_id": ids["cases"], "record_id": row, "field_id": ids["temperature"], "value": temperature},
                     {"op": "set_cell", "table_id": ids["cases"], "record_id": row, "field_id": ids["label"], "value": "viridis"}]
    revision = store.apply(commands, expected_revision=0)["revision"]
    revision = store.analyses.create("Temperature field", {"format": "stk.analysis-document/1", "graph": VOLUME["graph"],
                                     "parameters": {"path": "field.vtk"}, "outputs": ["view"]},
                                     analysis_id=ids["analysis"], expected_revision=revision)["revision"]
    store.workflows.create("Scan", workflow(ids), workflow_id=ids["workflow"], expected_revision=revision)
    return store, ids


def workflow(ids, **changes):
    steps = [{"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}},
             {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
              "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": ids["temperature"]}}},
             {"id": "temperature", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
              "inputs": {"data": {"from": "simulate.files"}},
              "parameters": {"colormap": {"$field": ids["label"]}, "opacity": [[0.0, 0.0], [1.0, 1.0]]}}]
    for step in steps:
        step.update(changes.get(step["id"], {}))
    return {"format": "stk.workflow/1", "steps": steps, "ui": {}}


def revision(store):
    return store.info()["revision"]


def prepare(store, ids, rows=None, run_id=None):
    return store.workflow_runs.prepare(ids["workflow"], ids["rows"] if rows is None else rows,
                                       run_id=run_id or str(uuid4()), expected_revision=revision(store))


def test_template_parameters_are_validated_like_analysis_parameters(project):
    store, ids = project
    assert store.workflows.validate(workflow(ids))["ok"]
    summary = store.workflows.validate(workflow(ids))["steps"][1]
    assert summary["parameters"] == [{"name": "temperature", "type": "number", "label": "Temperature", "unit": "K", "default": 300}]
    bad = workflow(ids, simulate={"parameters": {"temperature": {"$field": ids["label"]}, "pressure": 1}})
    codes = sorted((issue["code"], issue["path"]) for issue in store.workflows.validate(bad)["issues"])
    assert codes == [("parameter_type", "steps/1/parameters/temperature"), ("unknown_parameter", "steps/1/parameters/pressure")]
    units = workflow(ids, simulate={"parameters": {"temperature": {"$field": ids["energy"]}}})
    assert [issue["code"] for issue in store.workflows.validate(units)["issues"]] == ["unit_mismatch"]


def test_preparing_freezes_rows_values_analyses_and_order(project):
    store, ids = project
    before, history = store.snapshot(), store.history()
    run = prepare(store, ids, rows=[ids["rows"][2], ids["rows"][0]])
    assert store.snapshot() == before and store.history() == history  # no editable revision change
    assert run["status"] == "prepared" and not run["complete"]
    assert [(row["number"], row["values"][ids["temperature"]]) for row in run["rows"]] == [(3, 350), (1, 300)]
    assert run["order"] == ["simulate", "temperature"]
    assert run["parameters"]["simulate"][ids["rows"][2]] == {"temperature": 350}
    assert run["parameters"]["temperature"][ids["rows"][0]] == {"colormap": "viridis", "opacity": [[0.0, 0.0], [1.0, 1.0]]}
    analysis = store.analyses.get(ids["analysis"])["analysis"]["document"]
    frozen = run["steps"]["temperature"]
    assert frozen["sha256"] == hashlib.sha256(canonical_json(analysis)).hexdigest() and frozen["source"] == "simulate"
    assert run["steps"]["simulate"] == {"kind": "simulation", "template": "demo-synthetic/1", "outputs": ["field.vtk", "metrics.json"]}
    assert run["directory"] == f"results/workflow-runs/{run['id']}"
    assert [(task["step"], task["status"]) for task in run["tasks"]] == [("simulate", "pending"), ("temperature", "pending")] * 2
    # The same request again returns the same run; another request under its UUID is a conflict.
    assert prepare(store, ids, rows=[ids["rows"][2], ids["rows"][0]], run_id=run["id"])["plan_sha256"] == run["plan_sha256"]
    with pytest.raises(RevisionConflict, match="different preparation"):
        prepare(store, ids, rows=[ids["rows"][0]], run_id=run["id"])
    with pytest.raises(RevisionConflict):
        store.workflow_runs.prepare(ids["workflow"], ids["rows"], run_id=str(uuid4()), expected_revision=revision(store) - 1)
    listed = store.workflow_runs.list()
    assert [entry["id"] for entry in listed["runs"]] == [run["id"]] and listed["next_offset"] is None
    assert store.workflow_runs.list(workflow_id=str(uuid4()))["runs"] == []
    with pytest.raises(WorkflowRunNotFound):
        store.workflow_runs.get(str(uuid4()))


def muferro_workflow(ids):
    """A valid workflow over the MuFerro case table; its simulation step needs a Runtime connection."""
    return {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": muferro.TABLE_ID}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "muferro/1"}, "inputs": {"rows": {"from": "cases.rows"}}},
        {"id": "temperature", "kind": "analysis", "ref": {"analysis": ids["analysis"]}, "inputs": {"data": {"from": "simulate.files"}}}]}


@pytest.mark.parametrize("change, message", [
    (muferro_workflow, "Choose where to run"),  # MuFerro steps need a Runtime connection (W5)
    (lambda ids: workflow(ids, temperature={"parameters": {"nope": 1}}), "problems"),
    (lambda ids: {**workflow(ids), "steps": workflow(ids)["steps"] + [
        {"id": "other", "kind": "table", "ref": {"table": ids["cases"]}}]}, "exactly one parameter table"),
])
def test_runs_that_cannot_execute_are_refused_at_preparation(project, change, message):
    store, ids = project
    store.apply([{"op": "create_table", "id": muferro.TABLE_ID, "name": "MuFerro cases"}], expected_revision=revision(store))
    store.workflows.update(ids["workflow"], "Scan", change(ids), expected_revision=revision(store))
    if change is muferro_workflow:
        assert store.workflows.validate(change(ids))["ok"]  # only running it is refused
    with pytest.raises(ProjectError, match=message):
        prepare(store, ids)
    assert store.workflow_runs.list()["runs"] == []


def test_rows_must_belong_to_the_table_and_be_free_of_formula_errors(project):
    store, ids = project
    with pytest.raises(ProjectError, match="belong"):
        prepare(store, ids, rows=[str(uuid4())])
    store.apply([{"op": "set_expression", "table_id": ids["cases"], "record_id": ids["rows"][1],
                  "field_id": ids["temperature"], "expression": "1/0", "bindings": {}}], expected_revision=revision(store))
    with pytest.raises(ProjectError, match="Row 2 has a formula error"):
        prepare(store, ids)
    assert prepare(store, ids, rows=[ids["rows"][0]])["rows"][0]["number"] == 1


def test_attempts_are_numbered_and_only_the_latest_can_finish(project):
    store, ids = project
    runs = store.workflow_runs
    run = prepare(store, ids, rows=[ids["rows"][0]])
    row, executor, other = ids["rows"][0], str(uuid4()), str(uuid4())
    with pytest.raises(RevisionConflict):
        runs.begin_attempt(run["id"], "simulate", row, executor_id=executor)  # not started
    assert runs.start(run["id"], executor_id=executor)["status"] == "running"
    with pytest.raises(RevisionConflict, match="already has an executor"):
        runs.start(run["id"], executor_id=other)
    with pytest.raises(RevisionConflict):
        runs.begin_attempt(run["id"], "simulate", row, executor_id=other)
    assert runs.begin_attempt(run["id"], "simulate", row, executor_id=executor) == 1
    with pytest.raises(RevisionConflict, match="already running"):
        runs.begin_attempt(run["id"], "simulate", row, executor_id=executor)
    failed = runs.finish_attempt(run["id"], "simulate", row, 1, "failed", executor_id=executor,
                                 error={"code": "solver_failed", "message": "No field written"})
    assert failed["tasks"][0]["status"] == "failed" and failed["tasks"][0]["error"]["code"] == "solver_failed"
    assert runs.begin_attempt(run["id"], "simulate", row, executor_id=executor) == 2
    # The first attempt reporting late is refused: only attempt 2 can finish the task.
    with pytest.raises(RevisionConflict, match="stale"):
        runs.finish_attempt(run["id"], "simulate", row, 1, "succeeded", executor_id=executor)
    done = runs.finish_attempt(run["id"], "simulate", row, 2, "succeeded", executor_id=executor,
                               produced={"snapshot_id": str(uuid4())})
    assert done["tasks"][0] == {**done["tasks"][0], "attempt": 2, "status": "succeeded"}
    with pytest.raises(RevisionConflict, match="already succeeded"):
        runs.begin_attempt(run["id"], "simulate", row, executor_id=executor)
    assert runs.request_cancel(run["id"])["status"] == "cancel_requested"
    stopped = runs.stop(run["id"], executor_id=executor)
    assert stopped["status"] == "stopped" and stopped["counts"] == {"succeeded": 1, "pending": 1} and not stopped["complete"]
    # A stopped run starts again for its unfinished tasks only.
    assert runs.start(run["id"], executor_id=other)["executor_id"] == other


def test_a_vanished_executor_leaves_interrupted_attempts_and_a_restartable_run(project):
    store, ids = project
    runs = store.workflow_runs
    run = prepare(store, ids, rows=[ids["rows"][0]])
    executor = str(uuid4())
    runs.start(run["id"], executor_id=executor)
    runs.begin_attempt(run["id"], "simulate", ids["rows"][0], executor_id=executor)
    recovered = runs.interrupt(run["id"])
    assert recovered["status"] == "stopped" and recovered["tasks"][0]["status"] == "interrupted"
    assert recovered["tasks"][0]["error"]["code"] == "interrupted"
    assert runs.start(run["id"], executor_id=str(uuid4()))["status"] == "running"


def test_the_log_is_an_unbroken_chain(project):
    store, ids = project
    run = prepare(store, ids, rows=[ids["rows"][0]])
    store.workflow_runs.start(run["id"], executor_id=str(uuid4()))
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE workflow_run_events SET payload='{\"at\":\"x\"}' WHERE run_id=? AND status='started'", (run["id"],))
    with pytest.raises(ProjectError, match="unbroken chain"):
        store.workflow_runs.get(run["id"])


def test_older_projects_need_an_explicit_upgrade(project):
    store, ids = project
    with sqlite3.connect(store.path) as db:
        for table in ("project_labels", "project_archive", "workflow_run_events", "workflow_run_plans"):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=9")
    with pytest.raises(UnsupportedProjectFormat, match="format 10"):
        prepare(store, ids)
    upgraded = store.upgrade(expected_revision=revision(store))
    assert upgraded["format_version"] == 12 and upgraded["backup"]
    assert prepare(store, ids)["status"] == "prepared"


def test_analysis_runs_freeze_per_run_parameter_overrides(project, tmp_path):
    store, ids = project
    field = store.directory / "field.vtk"
    field.write_text("not read\n")
    indexed = store.files.index([str(field)], expected_revision=revision(store))
    snapshot = store.snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])["snapshot"]["id"]
    bindings = {"data": {"field.vtk": indexed["record_ids"][0]}}
    plain = store.analysis_runs.prepare(ids["analysis"], snapshot, bindings, run_id=str(uuid4()), expected_revision=revision(store))
    assert "parameter_overrides" not in plain and effective_parameters(plain) == {"path": "field.vtk"}
    run_id = str(uuid4())
    run = store.analysis_runs.prepare(ids["analysis"], snapshot, bindings, run_id=run_id, expected_revision=revision(store),
                                      parameter_overrides={"colormap": "cividis"})
    assert run["parameter_overrides"] == {"colormap": "cividis"}
    assert run["document"] == store.analyses.get(ids["analysis"])["analysis"]["document"]  # the saved analysis, verbatim
    assert effective_parameters(run) == {"path": "field.vtk", "colormap": "cividis"}
    assert store.analysis_runs.get(run_id)["parameter_overrides"] == {"colormap": "cividis"}
    with pytest.raises(RevisionConflict, match="different preparation"):
        store.analysis_runs.prepare(ids["analysis"], snapshot, bindings, run_id=run_id, expected_revision=revision(store),
                                    parameter_overrides={"colormap": "gray"})
    with pytest.raises(ProjectError, match="declared graph parameters"):
        store.analysis_runs.prepare(ids["analysis"], snapshot, bindings, run_id=str(uuid4()), expected_revision=revision(store),
                                    parameter_overrides={"undeclared": 1})


def codes_by_step(row):
    return {step: [reason["code"] for reason in reasons] for step, reasons in row["steps"].items() if reasons}


def test_staleness_names_the_changed_value_step_or_analysis_and_flows_downstream(project):
    store, ids = project
    run = prepare(store, ids)
    fresh = store.workflow_runs.stale(run["id"])
    assert fresh["stale_rows"] == [] and all(not row["stale"] for row in fresh["rows"])
    # One row's temperature: only that row, its simulation and (downstream) its analysis.
    store.apply([{"op": "set_cell", "table_id": ids["cases"], "record_id": ids["rows"][1], "field_id": ids["temperature"],
                  "value": 330}], expected_revision=revision(store))
    state = store.workflow_runs.stale(run["id"])
    assert state["stale_rows"] == [ids["rows"][1]]
    row = state["rows"][1]
    assert codes_by_step(row) == {"simulate": ["value_changed"], "temperature": ["upstream_changed"]}
    change = row["steps"]["simulate"][0]
    assert (change["name"], change["before"], change["after"]) == ("T", 325, 330)
    # The analysis changes: every row's analysis step, nothing upstream.
    document = store.analyses.get(ids["analysis"])["analysis"]["document"]
    document["parameters"]["path"] = "other.vtk"
    store.analyses.update(ids["analysis"], "Temperature field", document, expected_revision=revision(store))
    state = store.workflow_runs.stale(run["id"])
    assert codes_by_step(state["rows"][0]) == {"temperature": ["analysis_changed"]}
    # A changed step definition (not just its label) and a removed row.
    labelled = workflow(ids, temperature={"label": "Field view"})
    store.workflows.update(ids["workflow"], "Scan", labelled, expected_revision=revision(store))
    assert codes_by_step(store.workflow_runs.stale(run["id"])["rows"][0]) == {"temperature": ["analysis_changed"]}
    changed = workflow(ids, simulate={"parameters": {"temperature": 400}})
    store.workflows.update(ids["workflow"], "Scan", changed, expected_revision=revision(store))
    store.apply([{"op": "delete_record", "id": ids["rows"][2]}], expected_revision=revision(store))
    state = store.workflow_runs.stale(run["id"])
    assert codes_by_step(state["rows"][0]) == {"simulate": ["step_changed"], "temperature": ["analysis_changed", "upstream_changed"]}
    assert "row_removed" in [reason["code"] for reason in state["rows"][2]["steps"]["simulate"]]
    assert store.workflow_runs.get(run["id"])["rows"] == run["rows"]  # the run itself never changes
