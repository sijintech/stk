"""Workflow runs through the service: explicit start, rows in order, per-row values, retry, cancel, recover."""
import json
from pathlib import Path
import threading
import time
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.workflows import templates
from test_analysis_run_executor import value_result
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

VOLUME = json.loads((Path(__file__).resolve().parents[1] / "suan" / "graph" / "presets" / "volume.json").read_text())


class LevelWorker:
    """Stands in for the graph worker: echoes the evaluated `level` so per-row overrides are visible."""
    def __init__(self, gate=None):
        self.levels, self.gate = [], gate

    def evaluate(self, identity, work, cancel, events):
        if self.gate is not None:
            self.gate.wait(5)
        level = work["request"]["parameters"].get("level")
        self.levels.append(level)
        return value_result(work["request"]["graph"], parameters={"level": {"value": level}})


def analysis_document():
    return {"format": "stk.analysis-document/1", "graph": {"schema": "stk.graph/1",
            "parameters": [{"name": "level", "type": "number", "default": 1, "unit": "K"}],
            "nodes": [{"id": "src", "type": "stk.source.file@1", "params": {"binding": "data", "path": "field.vtk"}},
                      {"id": "n", "type": "fixture.test.value@1"}],
            "outputs": {"value": "n.value"}}, "parameters": {}, "outputs": ["value"]}


@pytest.fixture
def setup(inproc, tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Workflow runs")
    ids = {key: str(uuid4()) for key in ("cases", "temperature", "analysis", "workflow")}
    ids["rows"] = [str(uuid4()) for _ in range(3)]
    commands = [{"op": "create_table", "id": ids["cases"], "name": "Cases"},
                {"op": "add_field", "id": ids["temperature"], "table_id": ids["cases"], "name": "T", "type": "number", "unit": "K"}]
    for row, temperature in zip(ids["rows"], (300, 325, 350)):
        commands += [{"op": "add_record", "id": row, "table_id": ids["cases"]},
                     {"op": "set_cell", "table_id": ids["cases"], "record_id": row, "field_id": ids["temperature"], "value": temperature}]
    revision = store.apply(commands, expected_revision=0)["revision"]
    revision = store.analyses.create("Measure", analysis_document(), analysis_id=ids["analysis"], expected_revision=revision)["revision"]
    store.workflows.create("Scan", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": ids["temperature"]}}},
        {"id": "measure", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
         "inputs": {"data": {"from": "simulate.files"}}, "parameters": {"level": {"$field": ids["temperature"]}}}]},
        workflow_id=ids["workflow"], expected_revision=revision)
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    worker = LevelWorker()
    h.bridge.analysis_executor.worker = worker
    return h, store, ids, handle, worker


def prepare(h, store, ids, handle, rows=None):
    return h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": ids["workflow"],
        "rows": rows or ids["rows"], "run_id": str(uuid4()), "expected_revision": store.info()["revision"]})["run"]


def settled(h, handle, run_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = h.call("project.workflow_runs.get", {"handle": handle, "run_id": run_id})["run"]
        if run["status"] == "stopped" and not h.bridge.workflow_executor.active(h.bridge.projects._stores[handle], run_id):
            return run
        time.sleep(0.02)
    pytest.fail("workflow run did not settle")


def tasks(run):
    return {(task["step"], next(row["number"] for row in run["rows"] if row["id"] == task["row"])): task for task in run["tasks"]}


def test_rows_run_in_order_with_their_own_values_and_registered_outputs(setup):
    h, store, ids, handle, worker = setup
    methods = {"project.workflow_runs." + name for name in ("prepare", "get", "list", "start", "cancel", "recover")}
    assert methods <= set(h.call("hello", {"protocol": 1})["methods"])
    assert methods <= set(h.call("script.catalog")["operations"])
    run = prepare(h, store, ids, handle)
    assert run["status"] == "prepared" and worker.levels == []  # preparing runs nothing
    revision = store.info()["revision"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert done["complete"] and done["counts"] == {"succeeded": 6}
    assert worker.levels == [300, 325, 350]  # rows in order, each with its own frozen value
    by = tasks(done)
    for number, temperature in ((1, 300), (2, 325), (3, 350)):
        produced = by[("simulate", number)]["produced"]
        assert produced["directory"] == f"results/workflow-runs/{run['id']}/row-{number}/simulate/attempt-1"
        metrics = json.loads((store.directory / produced["directory"] / "metrics.json").read_text())
        assert metrics["temperature_K"] == temperature and metrics["synthetic"]
        analysis = store.analysis_runs.get(by[("measure", number)]["produced"]["analysis_run_id"])
        assert analysis["parameter_overrides"] == {"level": temperature} and analysis["status"] == "succeeded"
        assert analysis["snapshot_id"] == produced["snapshot_id"]
    # Registering outputs is two ordinary edits per row (index, capture), each announced to open handles.
    assert store.info()["revision"] == revision + 6
    assert h.events_of("project.changed")[-1]["revision"] == revision + 6
    listed = h.call("project.workflow_runs.list", {"handle": handle, "workflow_id": ids["workflow"]})["runs"]
    assert [(entry["id"], entry["complete"]) for entry in listed] == [(run["id"], True)]
    assert not h.violations


def test_a_failing_task_stops_only_its_row_and_starting_again_retries_only_it(setup, monkeypatch):
    h, store, ids, handle, worker = setup
    template = templates.LOCAL_TEMPLATES["demo-synthetic/1"]
    original, calls = template.run, []

    def flaky(parameters, directory):
        calls.append(parameters["temperature"])
        if parameters["temperature"] == 325 and calls.count(325) == 1:
            raise RuntimeError("solver crashed")
        return original(parameters, directory)
    monkeypatch.setattr(template, "run", flaky)
    run = prepare(h, store, ids, handle)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    first = settled(h, handle, run["id"])
    by = tasks(first)
    assert by[("simulate", 2)]["status"] == "failed" and by[("simulate", 2)]["error"]["message"] == "solver crashed"
    assert by[("measure", 2)]["status"] == "pending"  # blocked by its row's failed step
    assert by[("measure", 3)]["status"] == "succeeded" and not first["complete"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    second = settled(h, handle, run["id"])
    by = tasks(second)
    assert second["complete"] and by[("simulate", 2)]["attempt"] == 2 and by[("measure", 2)]["attempt"] == 1
    assert by[("simulate", 1)]["attempt"] == 1 and by[("measure", 3)]["attempt"] == 1  # nothing else redone
    assert calls == [300, 325, 350, 325] and worker.levels == [300, 350, 325]
    assert (store.directory / by[("simulate", 2)]["produced"]["directory"]).name == "attempt-2"


def test_cancel_keeps_finished_tasks_and_a_changed_analysis_is_never_run(setup):
    h, store, ids, handle, worker = setup
    gate = threading.Event()
    worker.gate = gate
    run = prepare(h, store, ids, handle)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    deadline = time.monotonic() + 10
    while not any(t["step"] == "measure" and t["status"] == "running"
                  for t in h.call("project.workflow_runs.get", {"handle": handle, "run_id": run["id"]})["run"]["tasks"]):
        assert time.monotonic() < deadline
        time.sleep(0.02)
    h.call("project.workflow_runs.cancel", {"handle": handle, "run_id": run["id"]})
    gate.set()
    cancelled = settled(h, handle, run["id"])
    by = tasks(cancelled)
    assert by[("simulate", 1)]["status"] == "succeeded" and by[("measure", 1)]["status"] in ("cancelled", "succeeded")
    assert by[("simulate", 2)]["status"] == "pending" and not cancelled["complete"]
    # The saved analysis changes before the run continues: its frozen document is never silently replaced.
    document = analysis_document()
    document["graph"]["parameters"][0]["default"] = 2
    store.analyses.update(ids["analysis"], "Measure", document, expected_revision=store.info()["revision"])
    worker.gate = None
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    after = settled(h, handle, run["id"])
    failures = [t for t in after["tasks"] if t["step"] == "measure" and t["status"] == "failed"]
    assert failures and all(t["error"]["code"] == "analysis_changed" for t in failures)


def test_recover_interrupts_attempts_without_a_live_executor(setup):
    h, store, ids, handle, worker = setup
    run = prepare(h, store, ids, handle, rows=[ids["rows"][0]])
    phantom = str(uuid4())  # an executor of a service that no longer runs
    store.workflow_runs.start(run["id"], executor_id=phantom)
    store.workflow_runs.begin_attempt(run["id"], "simulate", ids["rows"][0], executor_id=phantom)
    error = h.error("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    assert error["code"] == "conflict"
    recovered = h.call("project.workflow_runs.recover", {"handle": handle, "run_id": run["id"]})["run"]
    assert recovered["status"] == "stopped" and recovered["tasks"][0]["status"] == "interrupted"
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    assert settled(h, handle, run["id"])["complete"]


def test_the_real_volume_analysis_runs_on_the_synthetic_field(inproc, tmp_path):
    pytest.importorskip("vtkmodules")
    store = ProjectStore.create(tmp_path / "project", "Real")
    cases, temperature, row, analysis, workflow = (str(uuid4()) for _ in range(5))
    revision = store.apply([{"op": "create_table", "id": cases, "name": "Cases"},
                            {"op": "add_field", "id": temperature, "table_id": cases, "name": "T", "type": "number", "unit": "K"},
                            {"op": "add_record", "id": row, "table_id": cases},
                            {"op": "set_cell", "table_id": cases, "record_id": row, "field_id": temperature, "value": 340}],
                           expected_revision=0)["revision"]
    revision = store.analyses.create("Temperature field", {"format": "stk.analysis-document/1", "graph": VOLUME["graph"],
                                     "parameters": {"path": "field.vtk"}, "outputs": ["view"]},
                                     analysis_id=analysis, expected_revision=revision)["revision"]
    store.workflows.create("Scan", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": cases}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": temperature}}},
        {"id": "temperature", "kind": "analysis", "ref": {"analysis": analysis}, "inputs": {"data": {"from": "simulate.files"}}}]},
        workflow_id=workflow, expected_revision=revision)
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": workflow, "rows": [row],
                 "run_id": str(uuid4()), "expected_revision": store.info()["revision"]})["run"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"], timeout=120)
    assert done["complete"], done["tasks"]
    result = store.analysis_runs.get(tasks(done)[("temperature", 1)]["produced"]["analysis_run_id"])
    assert result["status"] == "succeeded" and result["result"]["has_payload"]
