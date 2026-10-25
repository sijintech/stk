"""Versioned workflow boundaries, immutable expansion and execution of repeated subflows."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from suan.project import ProjectError, RevisionConflict
from suan.project import workflows
from suan.project import workflow_composition as composition
from test_workflow_runs import project, revision  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_bridge_workflow_runs import setup, settled  # noqa: F401


def document(steps, *, inputs=None, outputs=None, parameters=None):
    return {"format": "stk.workflow/2", "steps": steps, "ui": {}, "interface": {
        "inputs": inputs or {}, "outputs": outputs or {}, "parameters": parameters or []}}


def child_document():
    return document([
        {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "$input.rows"}}, "parameters": {"temperature": {"$param": "temperature"}}},
    ], inputs={"rows": {"type": "rows"}}, outputs={"files": {"type": "files", "from": "simulate.files"}},
       parameters=[{"name": "temperature", "type": "number", "unit": "K", "default": 300, "minimum": 1}])


def write(store, doc, identity=None):
    identity = identity or str(uuid4())
    store.workflows.create("Reusable", doc, workflow_id=identity, expected_revision=revision(store))
    return identity


def call(child, name="nested", *, after=None):
    return {"id": name, "kind": "workflow", "ref": {"workflow": child},
            "inputs": {"rows": {"from": "cases.rows"}}, "after": after or []}


def parent_document(ids, child):
    invocation = call(child)
    invocation["parameters"] = {"temperature": {"$field": ids["temperature"]}}
    return document([{"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}}, invocation,
                     {"id": "view", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
                      "inputs": {"data": {"from": "nested.files"}}}])


def prepare(store, ids, doc):
    parent = write(store, doc)
    run = store.workflow_runs.prepare(parent, ids["rows"], run_id=str(uuid4()), expected_revision=revision(store))
    return parent, run


def test_interface_roundtrip_undo_and_read_only_validation(project):
    store, ids = project
    child = child_document()
    identity = write(store, child)
    baseline, history = store.snapshot(), store.history()
    assert store.workflows.get(identity)["workflow"]["document"] == child
    assert store.workflows.validate(child)["ok"]
    assert store.snapshot() == baseline and store.history() == history
    changed = deepcopy(child)
    changed["interface"]["parameters"][0]["default"] = 9007199254740993
    store.workflows.update(identity, "Updated", changed, expected_revision=revision(store))
    assert store.workflows.get(identity)["workflow"]["document"] == changed
    store.undo(expected_revision=revision(store))
    assert store.workflows.get(identity)["workflow"]["document"] == child
    store.redo(expected_revision=revision(store))
    assert store.workflows.get(identity)["workflow"]["document"] == changed


def test_preparation_freezes_interfaces_instances_and_row_bindings(project):
    store, ids = project
    child = write(store, child_document())
    doc = parent_document(ids, child)
    checked = store.workflows.validate(doc)
    assert checked["ok"], checked
    assert checked["steps"][1]["kind"] == "workflow"
    assert checked["steps"][1]["inputs"] == [{"name": "rows", "type": "rows", "required": True}]
    parent, run = prepare(store, ids, doc)
    simulate = next(k for k, p in run["composition"]["step_paths"].items() if p == ["nested", "simulate"])
    assert run["order"] == [simulate, "view"]
    assert run["workflow_document"] == doc
    assert run["composition"]["sources"][child]["document"] == child_document()
    assert run["steps"]["view"]["source"] == simulate
    assert [run["parameters"][simulate][r]["temperature"] for r in ids["rows"]] == [300, 325, 350]
    assert store.workflow_runs.stale(run["id"])["stale_rows"] == []
    changed = child_document()
    changed["steps"][0]["parameters"]["temperature"] = 400
    store.workflows.update(child, "Edited", changed, expected_revision=revision(store))
    assert store.workflow_runs.get(run["id"])["plan_sha256"] == run["plan_sha256"]
    assert store.workflow_runs.stale(run["id"])["stale_rows"] == ids["rows"]
    newer = store.workflow_runs.prepare(parent, ids["rows"], run_id=str(uuid4()), expected_revision=revision(store))
    assert newer["parameters"][simulate][ids["rows"][0]]["temperature"] == 400


@pytest.mark.parametrize("marker", ["$field", "$param", "$literal"])
def test_json_interface_defaults_keep_literal_identity_across_nested_calls(project, marker):
    store, ids = project
    literal = {marker: ids["label"]}
    declaration = {"name": "payload", "type": "json", "default": literal}
    analysis = store.analyses.get(ids["analysis"])["analysis"]["document"]
    analysis["graph"]["parameters"].append({"name": "payload", "type": "json", "default": {}})
    store.analyses.update(ids["analysis"], "JSON method", analysis, expected_revision=revision(store))
    inputs = {"data": {"type": "files"}}
    outputs = {"view": {"type": "result", "from": "view.view"}}
    leaf = write(store, document([{"id": "view", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
        "inputs": {"data": {"from": "$input.data"}}, "parameters": {"payload": {"$param": "payload"}}}],
        inputs=inputs, outputs=outputs, parameters=[declaration]))
    outer = write(store, document([{"id": "view", "kind": "workflow", "ref": {"workflow": leaf},
        "inputs": {"data": {"from": "$input.data"}}, "parameters": {"payload": {"$param": "payload"}}}],
        inputs=inputs, outputs=outputs, parameters=[declaration]))
    root = store.workflows.get(ids["workflow"])["workflow"]["document"]
    root["steps"][-1] = {"id": "nested", "kind": "workflow", "ref": {"workflow": outer},
        "inputs": {"data": {"from": "simulate.files"}}, "parameters": {"payload": {"$param": "payload"}}}
    root = document(root["steps"], parameters=[declaration])
    checked = store.workflows.validate(root)
    assert checked["ok"], checked
    _, run = prepare(store, ids, root)
    view = next(k for k, path in run["composition"]["step_paths"].items() if path == ["nested", "view", "view"])
    assert all(values["payload"] == literal for values in run["parameters"][view].values())
    assert all(ids["label"] not in row["values"] for row in run["rows"])
    assert store.workflow_runs.stale(run["id"])["stale_rows"] == []
    # Removing the public parameter can encode its former default explicitly at the call site.
    root["interface"]["parameters"] = []
    root["steps"][-1]["parameters"]["payload"] = {"$literal": literal}
    _, direct = prepare(store, ids, root)
    assert all(values["payload"] == literal for values in direct["parameters"][view].values())
    assert all(ids["label"] not in row["values"] for row in direct["rows"])
    assert store.workflow_runs.stale(direct["id"])["stale_rows"] == []


def test_repeated_nested_instances_have_stable_distinct_tasks(project):
    store, ids = project
    inner = write(store, child_document())
    middle = child_document()
    middle["steps"] = [{"id": "inner", "kind": "workflow", "ref": {"workflow": inner},
        "inputs": {"rows": {"from": "$input.rows"}}, "parameters": {"temperature": {"$param": "temperature"}}}]
    middle["interface"]["outputs"]["files"]["from"] = "inner.files"
    outer = write(store, middle)
    doc = parent_document(ids, outer)
    doc["steps"].insert(2, call(outer, "again", after=["nested"]))
    _, run = prepare(store, ids, doc)
    paths = run["composition"]["step_paths"]
    first = next(k for k, p in paths.items() if p == ["nested", "inner", "simulate"])
    second = next(k for k, p in paths.items() if p == ["again", "inner", "simulate"])
    assert first != second and len(first) <= 64
    assert run["order"].index(first) < run["order"].index(second)
    _, repeat = prepare(store, ids, doc)
    assert repeat["order"] == run["order"]
    assert run["parameters"][first][ids["rows"][1]]["temperature"] == 325
    assert run["parameters"][second][ids["rows"][1]]["temperature"] == 300


@pytest.mark.parametrize("case,code", [
    ("missing_input", "workflow_inputs"), ("unknown_input", "unknown_input"),
    ("port_type", "interface_port"), ("parameter_type", "parameter_interface"),
    ("parameter_unit", "parameter_interface"), ("unknown_parameter", "unknown_parameter"),
    ("missing_output", "interface_port"), ("cycle", "workflow_cycle"),
])
def test_invalid_compositions_cannot_prepare_or_change_revision(project, case, code):
    store, ids = project
    child = child_document()
    child_id = str(uuid4())
    parent = parent_document(ids, child_id)
    if case == "missing_input":
        parent["steps"][1]["inputs"] = {}
    elif case == "unknown_input":
        child["steps"][0]["inputs"]["rows"]["from"] = "$input.absent"
    elif case == "port_type":
        child["interface"]["outputs"]["files"]["type"] = "rows"
    elif case == "parameter_type":
        parent["steps"][1]["parameters"]["temperature"] = "hot"
    elif case == "parameter_unit":
        parent["steps"][1]["parameters"]["temperature"] = {"$field": ids["energy"]}
    elif case == "unknown_parameter":
        parent["steps"][1]["parameters"]["other"] = 300
    elif case == "missing_output":
        child["interface"]["outputs"]["files"]["from"] = "missing.files"
    elif case == "cycle":
        child["steps"].append({"id": "recursive", "kind": "workflow", "ref": {"workflow": child_id},
                               "inputs": {"rows": {"from": "$input.rows"}}})
    write(store, child, child_id)
    identity = write(store, parent)
    before = revision(store)
    checked = store.workflows.validate(parent)
    assert not checked["ok"] and code in {item["code"] for item in checked["issues"]}, checked
    assert [step["id"] for step in checked["steps"]] == [step["id"] for step in parent["steps"]]
    with pytest.raises(ProjectError, match="problems"):
        store.workflow_runs.prepare(identity, ids["rows"], run_id=str(uuid4()), expected_revision=before)
    assert revision(store) == before and store.workflow_runs.list()["runs"] == []


def test_interface_constraints_apply_to_frozen_row_values(project):
    store, ids = project
    child = child_document()
    child["interface"]["parameters"][0]["maximum"] = 310
    identity = write(store, parent_document(ids, write(store, child)))
    assert store.workflows.validate(store.workflows.get(identity)["workflow"]["document"])["ok"]
    with pytest.raises(ProjectError, match="Workflow parameter"):
        store.workflow_runs.prepare(identity, ids["rows"], run_id=str(uuid4()), expected_revision=revision(store))
    assert store.workflow_runs.list()["runs"] == []


def test_expansion_limits_and_revision_drift_are_rejected(project, monkeypatch):
    store, ids = project
    child = write(store, child_document())
    doc = parent_document(ids, child)
    monkeypatch.setattr(composition, "MAX_DEPTH", 0)
    assert store.workflows.validate(doc)["issues"][0]["code"] == "workflow_depth"
    monkeypatch.setattr(composition, "MAX_DEPTH", 8)
    monkeypatch.setattr(composition, "MAX_EXPANDED_STEPS", 1)
    assert store.workflows.validate(doc)["issues"][0]["code"] == "workflow_size"
    monkeypatch.setattr(composition, "MAX_EXPANDED_STEPS", 1000)
    original = workflows.Workflows.get

    def changed(service, identity):
        result = original(service, identity)
        result["revision"] += 1
        return result

    monkeypatch.setattr(workflows.Workflows, "get", changed)
    with pytest.raises(RevisionConflict, match="changed"):
        store.workflows.validate(doc)


def test_frozen_nested_run_executes_after_child_definition_is_deleted(setup):
    h, store, ids, handle, worker = setup
    child = write(store, child_document())
    parent = parent_document(ids, child)
    parent["steps"][2]["parameters"] = {"level": {"$field": ids["temperature"]}}
    identity = write(store, parent)
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": identity,
        "rows": ids["rows"], "run_id": str(uuid4()), "expected_revision": revision(store)})["run"]
    assert worker.levels == []
    store.apply([{"op": "delete_record", "id": child}], expected_revision=revision(store))
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert done["complete"] and done["counts"] == {"succeeded": 6}
    assert worker.levels == [300, 325, 350]
    simulate = run["order"][0]
    for task in done["tasks"]:
        if task["step"] == simulate:
            metrics = json.loads((store.directory / task["produced"]["directory"] / "metrics.json").read_text())
            assert metrics["temperature_K"] in (300, 325, 350)
    assert not h.violations


def test_old_managed_table_upgrades_only_with_explicit_write_and_undo_restores_it(project):
    store, ids = project
    interface_id = workflows.FIELD_IDS["interface"]
    store.apply([{"op": "delete_field", "id": interface_id}], expected_revision=revision(store))
    old = store.workflows.get(ids["workflow"])["workflow"]["document"]
    before = store.snapshot()
    assert store.workflows.validate(old)["ok"]
    assert store.snapshot() == before
    updated = document(old["steps"])
    start = revision(store)
    store.workflows.update(ids["workflow"], "Version 2", updated, expected_revision=start)
    assert revision(store) == start + 1
    assert store.workflows.get(ids["workflow"])["workflow"]["document"] == updated
    with pytest.raises(ProjectError, match="downgraded"):
        store.workflows.update(ids["workflow"], "Old", old, expected_revision=revision(store))
    store.undo(expected_revision=revision(store))
    assert store.workflows.get(ids["workflow"])["workflow"]["document"] == old
    table = next(t for t in store.snapshot()["tables"] if t["id"] == workflows.TABLE_ID)
    assert interface_id not in {f["id"] for f in table["fields"]}


def test_missing_child_marks_only_its_branch_stale_and_layout_changes_do_not(project):
    store, ids = project
    first, second = write(store, child_document()), write(store, child_document())
    doc = parent_document(ids, first)
    doc["steps"].insert(2, call(second, "independent"))
    _, run = prepare(store, ids, doc)
    layout = child_document()
    layout["ui"] = {"positions": {"simulate": [500, 300]}}
    layout["steps"][0]["label"] = "New label"
    store.workflows.update(first, "New name", layout, expected_revision=revision(store))
    assert store.workflow_runs.stale(run["id"])["stale_rows"] == []
    store.apply([{"op": "delete_record", "id": first}], expected_revision=revision(store))
    state = store.workflow_runs.stale(run["id"])
    unaffected = next(k for k, p in run["composition"]["step_paths"].items() if p == ["independent", "simulate"])
    assert state["stale_rows"] == ids["rows"]
    assert all(not row["steps"][unaffected] for row in state["rows"])
    assert all(any(r["code"] == "upstream_changed" for r in row["steps"]["view"]) for row in state["rows"])


def test_passthrough_subflow_preserves_ordering_without_executable_children(project):
    store, ids = project
    passthrough = document([], inputs={"rows": {"type": "rows"}},
                           outputs={"rows": {"type": "rows", "from": "$input.rows"}})
    child = write(store, passthrough)
    doc = document([
        {"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}},
        {"id": "before", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "cases.rows"}}},
        call(child, "pass_rows", after=["before"]),
        {"id": "after", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "pass_rows.rows"}}}])
    _, run = prepare(store, ids, doc)
    assert run["order"] == ["before", "after"]
    after = next(s for s in run["document"]["steps"] if s["id"] == "after")
    assert "before" in after["after"]
    assert after["inputs"]["rows"]["from"] == "cases.rows"


def test_real_worker_evaluates_nested_simulation_output(project, inproc):
    pytest.importorskip("vtkmodules")
    store, ids = project
    child = child_document()
    child["steps"].append({"id": "temperature", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
                           "inputs": {"data": {"from": "simulate.files"}}})
    child["interface"]["outputs"]["view"] = {"type": "result", "from": "temperature.view"}
    child_id = write(store, child)
    doc = parent_document(ids, child_id)
    doc["steps"].pop()  # Both computation and analysis are inside the reusable method.
    parent = write(store, doc)
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": parent,
        "rows": ids["rows"][:1], "run_id": str(uuid4()), "expected_revision": revision(store)})["run"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"], timeout=120)
    assert done["complete"] and done["counts"] == {"succeeded": 2}, done["tasks"]
    task = next(t for t in done["tasks"] if "analysis_run_id" in (t["produced"] or {}))
    result = store.analysis_runs.get(task["produced"]["analysis_run_id"])
    assert result["status"] == "succeeded" and result["result"]["has_payload"]
    assert not h.violations


def test_composite_document_roundtrips_through_bridge_and_choices(setup):
    h, store, ids, handle, worker = setup
    child, identity = child_document(), str(uuid4())
    h.call("project.workflows.create", {"handle": handle, "workflow_id": identity, "name": "Child",
        "document": child, "expected_revision": revision(store)})
    assert h.call("project.workflows.get", {"handle": handle, "workflow_id": identity})["workflow"]["document"] == child
    checked = h.call("project.workflows.validate", {"handle": handle, "document": child})
    assert checked["ok"], checked
    choices = h.call("project.workflows.choices", {"handle": handle})
    assert choices["workflows"] == [{"id": identity, "name": "Child"}] and choices["omitted_workflows"] == 0
    child["interface"]["parameters"][0]["default"] = 310
    h.call("project.workflows.update", {"handle": handle, "workflow_id": identity, "name": "Child 2",
        "document": child, "expected_revision": revision(store)})
    assert h.call("project.workflows.get", {"handle": handle, "workflow_id": identity})["workflow"]["document"] == child
    assert not worker.levels and not h.violations


@pytest.mark.parametrize("key,value", [("unit", {}), ("minimum", "0"), ("maximum", None),
                                       ("choices", "hot"), ("default", True), ("name", "Invalid")])
def test_malformed_interface_parameter_metadata_never_enters_storage(project, key, value):
    store, _ = project
    child = child_document()
    child["interface"]["parameters"][0][key] = value
    before = revision(store)
    with pytest.raises(ProjectError, match="interface"):
        write(store, child)
    assert revision(store) == before


def test_nonempty_and_empty_call_dependencies_cannot_form_cycles(project):
    store, ids = project
    passthrough = write(store, document([], inputs={"rows": {"type": "rows"}},
                                       outputs={"rows": {"type": "rows", "from": "$input.rows"}}))
    doc = document([{"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}},
                    call(passthrough, "first", after=["second"]), call(passthrough, "second", after=["first"])])
    checked = store.workflows.validate(doc)
    assert not checked["ok"] and checked["issues"][0]["code"] == "cycle"
    doc["steps"][1]["after"] = ["absent"]
    doc["steps"][2]["after"] = []
    checked = store.workflows.validate(doc)
    assert not checked["ok"] and checked["issues"][0]["code"] == "missing_step"


def test_nested_rows_keep_template_table_restrictions(project):
    store, ids = project
    child = child_document()
    child["steps"][0]["ref"] = {"template": "muferro/1"}
    child["steps"][0]["parameters"] = {}
    child["interface"]["parameters"] = []
    identity = write(store, child)
    parent = parent_document(ids, identity)
    parent["steps"][1]["parameters"] = {}
    assert store.workflows.validate(child)["ok"]  # Abstract rows are bound by the caller.
    checked = store.workflows.validate(parent)
    assert not checked["ok"] and "template_table" in {p["code"] for p in checked["issues"]}
    assert checked["execution"] == {"requires_runtime": True, "table_id": ids["cases"]}


def test_execution_metadata_resolves_a_table_inside_the_child(project):
    store, ids = project
    child = child_document()
    child["steps"].insert(0, {"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}})
    child["steps"][1]["inputs"]["rows"]["from"] = "cases.rows"
    child["interface"]["inputs"] = {}
    identity = write(store, child)
    parent = document([{"id": "nested", "kind": "workflow", "ref": {"workflow": identity}}])
    checked = store.workflows.validate(parent)
    assert checked["ok"], checked
    assert checked["execution"] == {"requires_runtime": False, "table_id": ids["cases"]}
    _, run = prepare(store, ids, parent)
    assert run["table_id"] == ids["cases"] and len(run["order"]) == 1


@pytest.mark.parametrize("limit", ["MAX_SOURCE_BYTES", "MAX_EXPANDED_BYTES"])
def test_composition_byte_limits_refuse_without_writing(project, monkeypatch, limit):
    store, ids = project
    child = write(store, child_document())
    parent = parent_document(ids, child)
    before = revision(store)
    monkeypatch.setattr(composition, limit, 1)
    checked = store.workflows.validate(parent)
    assert not checked["ok"] and checked["issues"][0]["code"] == "workflow_size"
    assert revision(store) == before
