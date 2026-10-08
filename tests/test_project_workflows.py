"""Project workflows: shape-checked drafts in a managed table, and read-only reference validation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from suan.graph.schema import canonical_json
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import analyses, files, workflows
from suan.project.store import UnsupportedProjectFormat
from suan.project.workflows import DOCUMENT_FORMAT, TABLE_ID, WorkflowNotFound
from suan.scripting import Project
from suan.workflows import muferro
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

VOLUME = json.loads((Path(__file__).resolve().parents[1] / "suan" / "graph" / "presets" / "volume.json").read_text())


def document(*steps, ui=None):
    return {"format": DOCUMENT_FORMAT, "steps": list(steps), "ui": {} if ui is None else ui}


def analysis_document(graph):
    return {"format": analyses.DOCUMENT_FORMAT, "graph": graph, "parameters": {}, "outputs": []}


@pytest.fixture
def store(tmp_path):
    return ProjectStore.create(tmp_path / "project", "Workflows")


@pytest.fixture
def project(store):
    """A cases table (number in K, text, number in eV), one snapshot, the volume preset and a thresholded analysis."""
    ids = {key: str(uuid4()) for key in ("cases", "temperature", "label", "energy", "other", "other_field")}
    revision = store.apply([
        {"op": "create_table", "id": ids["cases"], "name": "Cases"},
        {"op": "add_field", "id": ids["temperature"], "table_id": ids["cases"], "name": "T", "type": "number", "unit": "K"},
        {"op": "add_field", "id": ids["label"], "table_id": ids["cases"], "name": "Colormap", "type": "text"},
        {"op": "add_field", "id": ids["energy"], "table_id": ids["cases"], "name": "E", "type": "number", "unit": "eV"},
        {"op": "create_table", "id": ids["other"], "name": "Other"},
        {"op": "add_field", "id": ids["other_field"], "table_id": ids["other"], "name": "X", "type": "text"},
    ], expected_revision=0)["revision"]
    path = store.path.parent / "field.vtk"
    path.write_text("not read by validation\n")
    indexed = store.files.index([str(path)], expected_revision=revision)
    captured = store.snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    ids["snapshot"] = captured["snapshot"]["id"]
    ids["volume"], ids["threshold"], ids["dynamic"] = str(uuid4()), str(uuid4()), str(uuid4())
    revision = store.analyses.create("Volume", analysis_document(VOLUME["graph"]), analysis_id=ids["volume"],
                                     expected_revision=captured["revision"])["revision"]
    threshold = {"schema": "stk.graph/1", "parameters": [
        {"name": "level", "type": "number", "default": 300, "unit": "K", "label": "Level"}],
        "nodes": [{"id": "src", "type": "stk.source.file@1", "params": {"binding": "data", "path": "a.vtk"}},
                  {"id": "tab", "type": "stk.source.table@1", "params": {"binding": "table", "path": "t.csv"}},
                  {"id": "cut", "type": "stk.filter.threshold@1", "params": {"field": "f", "lower": {"$param": "level"}},
                   "inputs": {"in": {"from": "src.out"}}}],
        "outputs": {"kept": "cut.out", "rows": "tab.out"}}
    revision = store.analyses.create("Threshold", analysis_document(threshold), analysis_id=ids["threshold"],
                                     expected_revision=revision)["revision"]
    dynamic = {"schema": "stk.graph/1", "parameters": [{"name": "which", "type": "string", "default": "data"}],
               "nodes": [{"id": "src", "type": "stk.source.file@1", "params": {"binding": {"$param": "which"}, "path": "a"}}],
               "outputs": {"out": "src.out"}}
    store.analyses.create("Dynamic", analysis_document(dynamic), analysis_id=ids["dynamic"], expected_revision=revision)
    return ids


def flow(ids):
    return document(
        {"id": "cases", "kind": "table", "ref": {"table": ids["cases"]}, "x-note": {"kept": [1, 2.5, None]}},
        {"id": "fields", "kind": "files", "ref": {"snapshot": ids["snapshot"]}, "after": ["cases"]},
        {"id": "view", "kind": "analysis", "ref": {"analysis": ids["volume"]}, "label": "温度场",
         "inputs": {"data": {"from": "fields.files"}},
         "parameters": {"colormap": {"$field": ids["label"]}, "path": "field.vtk"}},
        ui={"positions": {"cases": [0, 0], "fields": [260, 0.5]}, "zoom": 1.25})


def create(store, value, identity=None, name="流程"):
    identity = identity or str(uuid4())
    return identity, store.workflows.create(name, value, workflow_id=identity, expected_revision=store.info()["revision"])


def test_round_trip_keeps_exact_json_and_shares_project_undo(store, project):
    value = flow(project)
    identity, written = create(store, value)
    assert written["table_id"] == TABLE_ID and written["record_id"] == identity
    got = store.workflows.get(identity)
    table = next(step["ref"]["table"] for step in value["steps"] if step["kind"] == "table")  # the rows a run takes
    assert got["workflow"] == {"id": identity, "name": "流程", "format": DOCUMENT_FORMAT, "state": "readable",
                               "error": "", "document": value, "table_id": table}
    assert canonical_json(got["workflow"]["document"]) == canonical_json(value)
    listed = store.workflows.list()
    assert listed["total"] == 1 and listed["workflows"] == [{"id": identity, "name": "流程", "format": DOCUMENT_FORMAT,
                                                             "state": "readable", "error": "", "table_id": table}]
    changed = deepcopy(value)
    changed["steps"].pop(0)
    revision = store.workflows.update(identity, "Renamed", changed, expected_revision=written["revision"])["revision"]
    assert store.workflows.get(identity)["workflow"]["document"] == changed
    store.undo(expected_revision=revision)
    assert store.workflows.get(identity)["workflow"]["document"] == value
    with pytest.raises(RevisionConflict):
        store.workflows.update(identity, "Stale", value, expected_revision=revision)
    with pytest.raises(RevisionConflict, match="already exists"):
        create(store, value, identity)
    with pytest.raises(WorkflowNotFound):
        store.workflows.get(str(uuid4()))
    # Saved analyses and workflows are separate managed tables.
    assert store.analyses.list()["total"] == 3 and store.workflows.list()["total"] == 1


@pytest.mark.parametrize("mutate, error", [
    (lambda d: d.update(format="stk.workflow/2"), UnsupportedProjectFormat),
    (lambda d: d.update(extra=1), ProjectError),
    (lambda d: d.pop("ui"), ProjectError),
    (lambda d: d["steps"][0].update(id="Cases"), ProjectError),
    (lambda d: d["steps"][0].update(unknown=1), ProjectError),
    (lambda d: d["steps"][0].update(ref={}), ProjectError),
    (lambda d: d["steps"][2].update(inputs={"data": {"from": "fields"}}), ProjectError),
    (lambda d: d["steps"][2].update(inputs={"data": {"from": "fields.files", "alias": "x"}}), ProjectError),
    (lambda d: d["steps"][1].update(after=["cases", "cases"]), ProjectError),
    (lambda d: d["ui"].update(positions={"cases": [0, 2e6]}), ProjectError),
    (lambda d: d["ui"].update(positions={"cases": [0, float("nan")]}), ProjectError),
    (lambda d: d["steps"][2].update(parameters={"path": "x" * (64 * 1024)}), ProjectError),
    (lambda d: d.update(steps=[{"id": f"s{i}", "kind": "table", "ref": {"table": "t"}} for i in range(201)]), ProjectError),
])
def test_writes_reject_bad_shapes_without_changing_the_project(store, project, mutate, error):
    value = flow(project)
    mutate(value)
    before = store.info()["revision"]
    with pytest.raises(error):
        create(store, value)
    assert store.info()["revision"] == before and store.workflows.list()["total"] == 0


def test_valid_flow_resolves_names_ports_and_content_hash(store, project):
    before, history = store.snapshot(), store.history()
    answer = store.workflows.validate(flow(project))
    assert answer["ok"], answer["issues"]
    assert answer["revision"] == store.info()["revision"] and answer["omitted_issues"] == 0
    cases, fields, view = answer["steps"]
    assert cases == {"id": "cases", "kind": "table", "name": "Cases", "content_sha256": None, "file_count": None,
                     "inputs": [], "outputs": [{"name": "rows", "type": "rows"}], "parameters": []}
    assert fields["file_count"] == 1 and fields["outputs"] == [{"name": "files", "type": "files"}]
    saved = store.analyses.get(project["volume"])["analysis"]["document"]
    assert view["name"] == "Volume"
    assert view["content_sha256"] == hashlib.sha256(canonical_json(saved)).hexdigest()
    assert view["inputs"] == [{"name": "data", "type": "files", "required": True}]
    # Ports follow the stored graph (object keys are stored canonically sorted).
    assert view["outputs"] == [{"name": name, "type": "result"} for name in saved["graph"]["outputs"]]
    assert sorted(p["name"] for p in view["outputs"]) == ["image", "view"]
    assert [p["name"] for p in view["parameters"]] == [p["name"] for p in VOLUME["graph"]["parameters"]]
    assert store.snapshot() == before and store.history() == history


def codes(answer):
    return sorted((issue["code"], issue["step"], issue["path"]) for issue in answer["issues"])


def test_issues_are_located_by_step_and_path(store, project):
    other = str(uuid4())
    value = document(
        {"id": "cases", "kind": "table", "ref": {"table": project["cases"]}},
        {"id": "twice", "kind": "table", "ref": {"table": project["cases"]}},
        {"id": "twice", "kind": "files", "ref": {"snapshot": project["snapshot"]}},
        {"id": "odd", "kind": "report", "ref": {"page": "x"}},
        {"id": "badref", "kind": "table", "ref": {"tabel": project["cases"]}},
        {"id": "notuuid", "kind": "files", "ref": {"snapshot": "latest"}},
        {"id": "gone", "kind": "analysis", "ref": {"analysis": other}},
        {"id": "internal", "kind": "table", "ref": {"table": analyses.TABLE_ID}},
        {"id": "sim", "kind": "simulation", "ref": {"template": "muferro/9"}},
        {"id": "sim1", "kind": "simulation", "ref": {"template": "muferro/1"}, "inputs": {"rows": {"from": "cases.rows"}}},
        {"id": "files", "kind": "files", "ref": {"snapshot": project["snapshot"]}},
        {"id": "cut", "kind": "analysis", "ref": {"analysis": project["threshold"]},
         "inputs": {"data": {"from": "cases.rows"}, "table": {"from": "files.nothing"}, "extra": {"from": "files.files"}},
         "parameters": {"level": {"$field": project["energy"]}, "nope": 1}},
        {"id": "cut2", "kind": "analysis", "ref": {"analysis": project["threshold"]},
         "inputs": {"data": {"from": "missing.files"}, "table": {"from": "twice.files"}},
         "parameters": {"level": {"$field": project["label"]}}},
        {"id": "cut3", "kind": "analysis", "ref": {"analysis": project["threshold"]},
         "inputs": {"data": {"from": "files.files"}, "table": {"from": "files.files"}},
         "parameters": {"level": {"$field": project["other_field"]}}},
        {"id": "dyn", "kind": "analysis", "ref": {"analysis": project["dynamic"]}},
        {"id": "loop_a", "kind": "files", "ref": {"snapshot": project["snapshot"]}, "after": ["loop_b"], "parameters": {"x": 1}},
        {"id": "loop_b", "kind": "table", "ref": {"table": project["cases"]}, "after": ["loop_a", "nowhere"]},
    )
    answer = store.workflows.validate(value)
    assert not answer["ok"]
    assert codes(answer) == sorted([
        ("duplicate_step", "twice", "steps/1/id"), ("duplicate_step", "twice", "steps/2/id"),
        ("unknown_kind", "odd", "steps/3/ref"),
        ("invalid_reference", "badref", "steps/4/ref"), ("invalid_reference", "notuuid", "steps/5/ref"),
        ("missing_reference", "gone", "steps/6/ref"), ("missing_reference", "internal", "steps/7/ref"),
        ("unknown_template", "sim", "steps/8/ref"),
        ("template_table", "sim1", "steps/9/inputs/rows"),
        ("type_mismatch", "cut", "steps/11/inputs/data"), ("missing_port", "cut", "steps/11/inputs/table"),
        ("unknown_port", "cut", "steps/11/inputs/extra"),
        ("unit_mismatch", "cut", "steps/11/parameters/level"), ("unknown_parameter", "cut", "steps/11/parameters/nope"),
        ("missing_step", "cut2", "steps/12/inputs/data"), ("ambiguous_step", "cut2", "steps/12/inputs/table"),
        ("parameter_type", "cut2", "steps/12/parameters/level"),
        ("field_not_in_workflow", "cut3", "steps/13/parameters/level"),
        ("dynamic_binding", "dyn", "steps/14/ref"),
        ("unknown_parameter", "loop_a", "steps/15/parameters/x"),
        ("missing_step", "loop_b", "steps/16/after/1"),
        ("cycle", "loop_a", "steps/15"), ("cycle", "loop_b", "steps/16"),
    ])
    assert all(issue["message"] for issue in answer["issues"])
    by_id = {summary["id"]: summary for summary in answer["steps"] if summary["id"] != "twice"}
    assert by_id["sim1"]["name"] == "MuFerro" and by_id["gone"]["inputs"] == by_id["gone"]["outputs"] == []
    assert by_id["cut"]["parameters"] == [{"name": "level", "type": "number", "label": "Level", "unit": "K", "default": 300}]
    assert [p["name"] for p in by_id["cut"]["inputs"]] == ["data", "table"]


def test_required_inputs_matching_units_and_template_tables(store, project):
    value = document(
        {"id": "cases", "kind": "table", "ref": {"table": project["cases"]}},
        {"id": "muferro", "kind": "table", "ref": {"table": muferro.TABLE_ID}},
        {"id": "sim", "kind": "simulation", "ref": {"template": "muferro/1"}},
        {"id": "cut", "kind": "analysis", "ref": {"analysis": project["threshold"]},
         "inputs": {"data": {"from": "sim.files"}}, "parameters": {"level": {"$field": project["temperature"]}}})
    answer = store.workflows.validate(value)
    # The MuFerro case table does not exist in this project; the run inputs are still required.
    assert codes(answer) == sorted([("missing_reference", "muferro", "steps/1/ref"),
                                    ("missing_input", "sim", "steps/2/inputs/rows"),
                                    ("missing_input", "cut", "steps/3/inputs/table")])
    self_link = document({"id": "a", "kind": "analysis", "ref": {"analysis": project["volume"]},
                          "inputs": {"data": {"from": "a.view"}}})
    assert codes(store.workflows.validate(self_link)) == [("cycle", "a", "steps/0"), ("type_mismatch", "a", "steps/0/inputs/data")]


def test_managed_tables_are_not_parameter_tables_and_analyses_decode_once(store, project, monkeypatch):
    decoded, original = [], analyses._record
    monkeypatch.setattr(analyses, "_record", lambda db, identity, *rest: decoded.append(identity) or original(db, identity, *rest))
    value = document({"id": "index", "kind": "table", "ref": {"table": files.TABLE_ID}},
                     {"id": "own", "kind": "table", "ref": {"table": TABLE_ID}},
                     {"id": "a", "kind": "analysis", "ref": {"analysis": project["volume"]}},
                     {"id": "b", "kind": "analysis", "ref": {"analysis": project["volume"]}})
    answer = store.workflows.validate(value)
    assert codes(answer) == [("missing_input", "a", "steps/2/inputs/data"), ("missing_input", "b", "steps/3/inputs/data"),
                             ("missing_reference", "index", "steps/0/ref"), ("missing_reference", "own", "steps/1/ref")]
    assert decoded == [project["volume"]]
    assert answer["steps"][2]["content_sha256"] == answer["steps"][3]["content_sha256"] is not None


def test_validation_reports_unreadable_analyses_and_bounds_issues(store, project, monkeypatch):
    store.apply([{"op": "set_cell", "table_id": analyses.TABLE_ID, "record_id": project["volume"],
                  "field_id": analyses.FIELD_IDS["graph"], "value": {"broken": True}}],
                expected_revision=store.info()["revision"])
    answer = store.workflows.validate(flow(project))
    assert codes(answer) == [("unreadable_reference", "view", "steps/2/ref")]
    assert answer["steps"][2]["name"] == "Volume" and answer["steps"][2]["content_sha256"] is None
    monkeypatch.setattr(workflows, "MAX_ISSUES", 2)
    many = document(*({"id": f"s{i}", "kind": "odd", "ref": {"x": "y"}} for i in range(5)))
    answer = store.workflows.validate(many)
    assert len(answer["issues"]) == 2 and answer["omitted_issues"] == 3 and not answer["ok"]


def test_choices_list_referencable_objects_only(store, project):
    create(store, flow(project))
    before, history = store.snapshot(), store.history()
    answer = store.workflows.choices()
    assert answer["revision"] == store.info()["revision"] and answer["omitted_tables"] == 0
    # Parameter tables only: never the managed analysis, workflow or file-index tables.
    assert answer["tables"] == [{"id": project["cases"], "name": "Cases"}, {"id": project["other"], "name": "Other"}]
    assert [(s["id"], s["file_count"]) for s in answer["snapshots"]] == [(project["snapshot"], 1)]
    assert answer["analyses"] == [{"id": project["volume"], "name": "Volume"}, {"id": project["threshold"], "name": "Threshold"},
                                  {"id": project["dynamic"], "name": "Dynamic"}]
    assert answer["templates"] == [{"id": "muferro/1", "name": "MuFerro", "table_id": muferro.TABLE_ID},
                                   {"id": "demo-synthetic/1", "name": "Synthetic demo solver", "table_id": None}]
    assert store.snapshot() == before and store.history() == history  # read-only
    store.apply([{"op": "set_cell", "table_id": analyses.TABLE_ID, "record_id": project["dynamic"],
                  "field_id": analyses.FIELD_IDS["graph"], "value": {"broken": True}}], expected_revision=store.info()["revision"])
    assert [a["id"] for a in store.workflows.choices()["analyses"]] == [project["volume"], project["threshold"]]


def test_bridge_methods_scripting_api_and_events(inproc, tmp_path):
    h = inproc()
    info = h.call("project.create", {"directory": str(tmp_path / "project"), "name": "Bridge"})["project"]
    p = Project(lambda method, params: h.call(method, params), info["handle"])
    methods = {"project.workflows." + action for action in ("create", "update", "get", "list", "validate", "choices")}
    assert methods <= set(h.call("hello", {"protocol": 1})["methods"])
    assert methods <= h.call("script.catalog")["operations"].keys()
    empty = document()
    assert p.workflows.validate(empty) == {"revision": 0, "ok": True, "issues": [], "omitted_issues": 0, "steps": []}
    assert h.events_of("project.changed") == []
    identity = str(uuid4())
    written = p.workflows.create("Empty", empty, workflow_id=identity, expected_revision=0)
    assert h.events_of("project.changed")[-1]["revision"] == written["revision"]
    step = {"id": "t", "kind": "table", "ref": {"table": str(uuid4())}}
    p.workflows.update(identity, "One step", document(step), expected_revision=written["revision"])
    assert p.workflows.get(identity)["workflow"]["document"] == document(step)
    assert p.workflows.list()["workflows"][0]["name"] == "One step"
    assert p.workflows.validate(document(step))["issues"][0]["code"] == "missing_reference"
    assert p.workflows.choices() == {"revision": p.snapshot()["project"]["revision"], "tables": [], "omitted_tables": 0,
                                     "snapshots": [], "analyses": [],
                                     "templates": [{"id": "muferro/1", "name": "MuFerro", "table_id": muferro.TABLE_ID},
                                                   {"id": "demo-synthetic/1", "name": "Synthetic demo solver", "table_id": None}]}
    error = h.error("project.workflows.get", {"handle": info["handle"], "workflow_id": str(uuid4())})
    assert error["code"] == "not_found"
    error = h.error("project.workflows.create", {"handle": info["handle"], "workflow_id": identity, "name": "Again",
                                                 "document": empty, "expected_revision": p.snapshot()["project"]["revision"]})
    assert error["code"] == "conflict"
    assert not h.violations
    h.close()
