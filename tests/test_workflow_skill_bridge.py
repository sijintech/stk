"""Workflow method copies use the same checked desktop and Python operations, without execution."""
from copy import deepcopy
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_analyses import document as analysis_document
from test_workflow_composition import child_document, document, parent_document, write
from test_workflow_runs import project, revision  # noqa: F401
from test_bridge_workflow_runs import settled


def source_project(directory):
    store = ProjectStore.create(directory, "Reusable workflows")
    analysis, child, root = (str(uuid4()) for _ in range(3))
    store.analyses.create("Saved analysis", analysis_document(), analysis_id=analysis, expected_revision=0)
    store.workflows.create("Nested method", document([
        {"id": "plot", "kind": "analysis", "ref": {"analysis": analysis}}],
        outputs={"result": {"type": "result", "from": "plot.view"}}),
        workflow_id=child, expected_revision=1)
    store.workflows.create("Whole method", document([
        {"id": "first", "kind": "workflow", "ref": {"workflow": child}},
        {"id": "second", "kind": "workflow", "ref": {"workflow": child}}]),
        workflow_id=root, expected_revision=2)
    return store, analysis, child, root


def test_bridge_and_script_freeze_shared_sources_and_copy_after_source_deletion(inproc, tmp_path, monkeypatch):
    from suan.agent.levels import level
    from suan.skills import catalog
    from suan.workflows import templates

    store, source_analysis, source_child, source_root = source_project(tmp_path / "methods")
    harness = inproc()
    hello = harness.call("hello", {"protocol": 1})
    assert "project.skills.publish_workflow" in hello["methods"]
    assert "project.skills.create_workflow" in hello["methods"]
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    project = Project(harness.call, handle)

    def unavailable(*args, **kwargs):
        raise AssertionError("Method publication and copying must not load a catalog or engine")

    monkeypatch.setattr(catalog, "load_catalog", unavailable)
    monkeypatch.setattr(templates, "workflow_templates", unavailable)
    identity = str(uuid4())
    receipt = project.skills.publish_workflow(source_root, project_skill_id=identity, create=True,
        name="Frozen workflow", description="Includes both calls and the complete analysis", expected_revision=3)
    assert receipt["revision"] == 4 and receipt["record_id"] == identity
    saved = project.skills.get(identity)["skill"]
    version = saved["document"]["versions"][0]
    assert version["definition"]["entry"] == {"kind": "workflow.document"}
    assert set(version["template"]["workflows"]) == {source_root, source_child}
    assert set(version["template"]["analyses"]) == {source_analysis}
    assert version["template"]["analyses"][source_analysis]["document"] == analysis_document()
    project.apply([
        {"op": "delete_record", "id": source_root},
        {"op": "delete_record", "id": source_child},
        {"op": "delete_record", "id": source_analysis},
    ], expected_revision=4)
    before = store.snapshot()
    target = str(uuid4())
    result = project.skills.create_workflow(identity, saved["active"]["content_sha256"],
        workflow_id=target, name="Independent method", bindings={"tables": {}, "fields": {}, "snapshots": {}},
        expected_revision=5)
    assert result["revision"] == 6 and result["record_id"] == target
    root = store.workflows.get(target)["workflow"]["document"]
    children = {step["ref"]["workflow"] for step in root["steps"]}
    assert len(children) == 1 and source_child not in children
    child = store.workflows.get(next(iter(children)))["workflow"]["document"]
    copied_analysis = child["steps"][0]["ref"]["analysis"]
    assert copied_analysis != source_analysis
    copy = store.analyses.get(copied_analysis)["analysis"]["document"]
    assert copy["parameters"] == analysis_document()["parameters"]
    assert copy["outputs"] == analysis_document()["outputs"]
    assert store.workflows.list()["total"] == 2 and store.analyses.list()["total"] == 1
    project.undo(expected_revision=6)
    assert store.snapshot()["tables"] == before["tables"]
    project.redo(expected_revision=7)
    assert store.workflows.get(target)["workflow"]["document"] == root
    assert project.skills.get(identity)["skill"] == saved
    assert harness.bridge.graphs.worker._child is None
    assert level("project.skills.publish_workflow") == "project_edit"
    assert level("project.skills.create_workflow") == "project_edit"
    harness.assert_clean()


@pytest.mark.parametrize("damage", ["missing_bindings", "extra_category", "invalid_uuid", "stale_revision"])
def test_invalid_or_stale_copy_is_rejected_before_any_project_edit(inproc, tmp_path, damage):
    store, _, _, root = source_project(tmp_path / "invalid")
    harness = inproc()
    harness.call("hello", {"protocol": 1})
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    project = Project(harness.call, handle)
    identity = str(uuid4())
    project.skills.publish_workflow(root, project_skill_id=identity, create=True,
        name="Method", description="Frozen definition", expected_revision=3)
    digest = project.skills.get(identity)["skill"]["active"]["content_sha256"]
    params = {"handle": handle, "project_skill_id": identity, "content_sha256": digest,
              "workflow_id": str(uuid4()), "name": "Copy", "expected_revision": 4,
              "bindings": {"tables": {}, "fields": {}, "snapshots": {}}}
    if damage == "missing_bindings":
        del params["bindings"]
    elif damage == "extra_category":
        params["bindings"]["automatic"] = True
    elif damage == "invalid_uuid":
        params["bindings"]["tables"]["by-name"] = "Cases"
    else:
        params["expected_revision"] = 3
    before, history = deepcopy(store.snapshot()), store.history()
    error = harness.error("project.skills.create_workflow", params)
    assert error["code"] == ("conflict" if damage == "stale_revision" else "invalid_params")
    assert store.snapshot() == before and store.history() == history
    assert harness.bridge.graphs.worker._child is None
    harness.assert_clean()


def test_copied_workflow_runs_real_graph_worker_after_originals_are_deleted(project, inproc):
    pytest.importorskip("vtkmodules")
    store, ids = project
    child = child_document()
    child["steps"].append({"id": "temperature", "kind": "analysis", "ref": {"analysis": ids["analysis"]},
                           "inputs": {"data": {"from": "simulate.files"}}})
    child["interface"]["outputs"]["view"] = {"type": "result", "from": "temperature.view"}
    child_id = write(store, child)
    root_doc = parent_document(ids, child_id)
    root_doc["steps"].pop()
    root_id = write(store, root_doc)
    harness = inproc()
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    client = Project(harness.call, handle)
    skill_id = str(uuid4())
    client.skills.publish_workflow(root_id, project_skill_id=skill_id, create=True,
        name="Portable method", description="Real nested simulation and analysis", expected_revision=revision(store))
    skill = client.skills.get(skill_id)["skill"]
    dependencies = skill["document"]["versions"][0]["template"]["dependencies"]
    client.apply([{"op": "delete_record", "id": identity} for identity in (root_id, child_id, ids["analysis"])],
                 expected_revision=revision(store))
    copied = str(uuid4())
    client.skills.create_workflow(skill_id, skill["active"]["content_sha256"], workflow_id=copied,
        name="Recovered method", bindings={category: {key: key for key in values} for category, values in dependencies.items()},
        expected_revision=revision(store))
    assert harness.bridge.graphs.worker._child is None
    run = harness.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": copied,
        "rows": ids["rows"][:1], "run_id": str(uuid4()), "expected_revision": revision(store)})["run"]
    harness.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(harness, handle, run["id"], timeout=120)
    assert done["complete"] and done["counts"] == {"succeeded": 2}, done["tasks"]
    task = next(task for task in done["tasks"] if "analysis_run_id" in (task["produced"] or {}))
    result = store.analysis_runs.get(task["produced"]["analysis_run_id"])
    assert result["status"] == "succeeded" and result["result"]["has_payload"]
    harness.assert_clean()
