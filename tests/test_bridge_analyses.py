"""Saved graph documents use revisioned project edits, never graph execution or source access."""
from copy import deepcopy
from uuid import uuid4

import pytest

from suan.contracts import load_schema
from suan.desktop_bridge.schema import method_contract, validate_params
from suan.project import ProjectStore
from suan.project.analyses import TABLE_ID, FIELD_IDS
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def document():
    return {"format": "stk.analysis-document/1", "graph": {"schema": "stk.graph/1",
        "parameters": [{"name": "step", "type": "step", "default": "latest"}],
        "nodes": [{"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}}],
        "outputs": {"frames": "run.frames"}}, "parameters": {"step": "latest"}, "outputs": ["frames"]}


def opened(harness, tmp_path):
    info = harness.call("project.create", {"directory": str(tmp_path / "project"), "name": "Analyses"})["project"]
    return Project(lambda method, params: harness.call(method, params), info["handle"]), ProjectStore(tmp_path / "project")


def test_bridge_document_schema_reuses_the_published_structural_graph_contract():
    schema = load_schema("graph-1")

    def inline(value):
        if isinstance(value, list):
            return [inline(v) for v in value]
        if isinstance(value, dict):
            if "$ref" in value:
                return inline(schema["$defs"][value["$ref"].split("/")[-1]])
            return {k: inline(v) for k, v in value.items() if k not in ("$id", "$schema", "$defs", "title", "description")}
        return value

    embedded = method_contract("project.analyses.create")["params"]["properties"]["document"]["properties"]["graph"]
    # Drop descriptive annotations at every level, but retain all structural constraints.
    assert inline(embedded) == inline(schema)


def test_create_update_reads_reopen_undo_and_redo_use_one_shared_history(inproc, tmp_path, monkeypatch):
    h = inproc()
    p, store = opened(h, tmp_path)
    initial = store.snapshot()
    assert p.analyses.list() == {"revision": 0, "table_id": TABLE_ID, "compatible": True, "error": "",
                                 "offset": 0, "total": 0, "analyses": []}
    assert store.snapshot() == initial and h.events_of("project.changed") == []
    methods = {"project.analyses." + action for action in ("create", "update", "get", "list")}
    assert methods <= set(h.call("hello", {"protocol": 1})["methods"])
    assert methods <= h.call("script.catalog")["operations"].keys()

    def forbidden(*args, **kwargs):
        raise AssertionError("Analysis persistence must not validate, execute or submit anything")

    monkeypatch.setattr(h.bridge.graphs, "evaluate", forbidden)
    monkeypatch.setattr(h.bridge.graphs, "validate", forbidden)
    monkeypatch.setattr(h.bridge.project_runs, "call", forbidden)
    monkeypatch.setattr(h.bridge.projects._executor, "start", forbidden)
    identity = str(uuid4())
    first = p.analyses.create("结果分析", document(), analysis_id=identity, expected_revision=0)
    assert first["revision"] == 1 and first["record_id"] == identity and first["table_id"] == TABLE_ID
    h.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 1)
    assert h.events_of("project.changed") == [{"handle": p.handle, "revision": 1}]
    saved = p.analyses.get(identity)
    assert saved == {"revision": 1, "table_id": TABLE_ID, "compatible": True, "error": "", "analysis": {
        "id": identity, "name": "结果分析", "format": "stk.analysis-document/1", "state": "readable", "error": "", "document": document()}}
    replacement = document(); replacement["parameters"]["step"] = 4; replacement["outputs"] = []
    assert p.analyses.update(identity, "Revised", replacement, expected_revision=1)["revision"] == 2
    h.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 2)
    assert h.events_of("project.changed") == [{"handle": p.handle, "revision": 1}, {"handle": p.handle, "revision": 2}]
    assert p.analyses.get(identity)["analysis"]["document"] == replacement
    assert len(store.history()) == 2 and store.requests.list()["requests"] == []
    assert p.undo(expected_revision=2)["revision"] == 3
    assert p.analyses.get(identity)["analysis"] == saved["analysis"]
    assert p.redo(expected_revision=3)["revision"] == 4
    assert p.analyses.get(identity)["analysis"]["document"] == replacement
    assert p.close()
    assert h.error("project.analyses.get", {"handle": p.handle, "analysis_id": identity})["code"] == "not_found"
    reopened = h.call("project.open", {"directory": str(store.directory)})["project"]
    assert reopened["handle"] != p.handle
    assert h.call("project.analyses.get", {"handle": reopened["handle"], "analysis_id": identity})["analysis"]["document"] == replacement
    assert not h.violations


def test_conflicts_missing_rows_and_invalid_writes_leave_history_and_events_unchanged(inproc, tmp_path):
    h = inproc(); p, store = opened(h, tmp_path); identity = str(uuid4())
    p.analyses.create("Saved", document(), analysis_id=identity, expected_revision=0)
    h.wait_event(lambda e: e["event"] == "project.changed")
    before, history, events = store.snapshot(), store.history(), h.events_of("project.changed")
    params = {"handle": p.handle, "analysis_id": identity, "name": "Replaced", "document": document(), "expected_revision": 1}
    assert h.error("project.analyses.create", params)["code"] == "conflict"
    assert h.error("project.analyses.update", {**params, "expected_revision": 0})["code"] == "conflict"
    assert h.error("project.analyses.update", {**params, "analysis_id": str(uuid4())})["code"] == "not_found"
    assert h.error("project.analyses.get", {"handle": p.handle, "analysis_id": str(uuid4())})["code"] == "not_found"
    for invalid in ({**document(), "outputs": ["absent"]}, {**document(), "source": {"path": "unsaved"}},
                    {**document(), "outputs": ["frames", "frames"]}):
        assert h.error("project.analyses.update", {**params, "document": invalid})["code"] == "invalid_params"
    assert store.snapshot() == before and store.history() == history
    assert h.events_of("project.changed") == events and not h.violations


@pytest.mark.parametrize("change,state", [("malformed", "invalid"), ("future", "unsupported"), ("schema", "invalid")])
def test_manually_edited_rows_remain_inspectable_without_evaluation(inproc, tmp_path, monkeypatch, change, state):
    h = inproc(); p, store = opened(h, tmp_path); identity = str(uuid4())
    p.analyses.create("Saved", document(), analysis_id=identity, expected_revision=0)
    if change == "schema":
        command = {"op": "delete_field", "id": FIELD_IDS["graph"]}
    else:
        command = {"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                   "field_id": FIELD_IDS["format" if change == "future" else "graph"],
                   "value": "stk.analysis-document/2" if change == "future" else {"broken": True}}
    store.apply([command], expected_revision=1)
    h.wait_event(lambda e: e["event"] == "project.changed")
    events = h.events_of("project.changed")

    def forbidden(*args, **kwargs):
        raise AssertionError("Analysis reads must not obtain an evaluated project snapshot")

    with monkeypatch.context() as m:
        m.setattr(ProjectStore, "snapshot", forbidden)
        m.setattr(ProjectStore, "_snapshot", forbidden)
        read = p.analyses.get(identity); listed = p.analyses.list()
    assert read["revision"] == 2 and read["analysis"]["state"] == state and read["analysis"]["document"] is None
    assert read["analysis"]["error"] and len(read["analysis"]["error"].encode()) <= 512
    assert listed["analyses"] == [{k: v for k, v in read["analysis"].items() if k != "document"}]
    assert read["compatible"] is (change != "schema")
    if change == "future":
        assert h.error("project.analyses.update", {"handle": p.handle, "analysis_id": identity, "name": "Downgrade",
                      "document": document(), "expected_revision": 2})["code"] == "unsupported"
    assert h.events_of("project.changed") == events and not h.violations


def test_readable_draft_keeps_unknown_type_duplicate_ids_cycles_and_empty_output_selection(inproc, tmp_path):
    h = inproc(); p, _ = opened(h, tmp_path); draft = document()
    draft["graph"]["nodes"] = [{"id": "run", "type": "fixture.unknown.node@1",
        "inputs": {"in": {"from": "run.frames"}}}, {"id": "run", "type": "fixture.other.node@1"}]
    draft["outputs"] = []
    identity = str(uuid4()); p.analyses.create("Needs validation", draft, analysis_id=identity, expected_revision=0)
    assert p.analyses.get(identity)["analysis"]["document"] == draft
    assert p.analyses.list()["analyses"][0]["state"] == "readable"
    assert not h.violations


@pytest.mark.parametrize("action", ["create", "update", "get", "list"])
def test_exact_request_shapes_reject_unknown_fields_and_boolean_revisions(action):
    params = {"handle": "a" * 32}
    if action != "list": params["analysis_id"] = str(uuid4())
    if action in ("create", "update"):
        params.update(name="Saved", document=document(), expected_revision=0)
    assert validate_params("project.analyses." + action, params) == []
    assert validate_params("project.analyses." + action, {**params, "evaluate": True})
    if action in ("create", "update"):
        assert validate_params("project.analyses." + action, {**params, "expected_revision": True})
    if action == "list":
        for extra in ({"limit": 0}, {"limit": 101}, {"offset": True}, {"offset": -1}):
            assert validate_params("project.analyses.list", {**params, **extra})


def test_pagination_and_summary_contract_do_not_include_full_graphs(inproc, tmp_path):
    h = inproc(); p, _ = opened(h, tmp_path); identities = [str(uuid4()), str(uuid4())]
    for revision, identity in enumerate(identities):
        p.analyses.create(str(revision), document(), analysis_id=identity, expected_revision=revision)
    first = p.analyses.list(limit=1); second = p.analyses.list(offset=1, limit=1)
    assert first["total"] == second["total"] == 2
    assert first["analyses"][0]["id"] == identities[0] and second["analyses"][0]["id"] == identities[1]
    assert set(first["analyses"][0]) == {"id", "name", "format", "state", "error"}
    assert p.analyses.list(offset=2)["analyses"] == []
    assert not h.violations
