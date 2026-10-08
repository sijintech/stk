"""Archiving project objects (format 11): an append-only record outside the editable revision."""
import sqlite3
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.store import DATABASE_NAME, UnsupportedProjectFormat
from test_bridge_workflow_runs import analysis_document, setup  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def finished_run(store, ids, rows):
    """A stopped workflow run (its tasks are not run: nothing here needs results)."""
    run = store.workflow_runs.prepare(ids["workflow"], rows, run_id=str(uuid4()), expected_revision=store.info()["revision"])
    executor = str(uuid4())
    store.workflow_runs.start(run["id"], executor_id=executor)
    store.workflow_runs.stop(run["id"], executor_id=executor)
    return run["id"]


def test_archiving_hides_without_changing_the_project_and_restoring_brings_back(setup):
    h, store, ids, handle, worker = setup
    context = store.contexts.capture(table_id=ids["cases"], record_ids=ids["rows"][:1], field_ids=[ids["temperature"]],
                                     expected_revision=store.info()["revision"], title="Scope", context_id=str(uuid4()))
    draft = store.drafts.save([{"op": "set_cell", "table_id": ids["cases"], "record_id": ids["rows"][0],
                                "field_id": ids["temperature"], "value": 301}],
                              expected_revision=store.info()["revision"], title="Warmer", draft_id=str(uuid4()))
    run = finished_run(store, ids, ids["rows"][:1])
    items = [{"kind": "workflow", "id": ids["workflow"]}, {"kind": "analysis", "id": ids["analysis"]},
             {"kind": "draft", "id": draft["id"]}, {"kind": "context", "id": context["id"]}, {"kind": "workflow_run", "id": run}]
    before, history = store.snapshot(), store.history()
    mark = h.mark()
    changed = h.call("project.archive.set", {"handle": handle, "items": items, "archived": True, "note": "Old scan"})
    assert changed["changed"] == 5 and changed["items"] == items
    assert store.snapshot() == before and store.history() == history  # not an edit: no revision, no undo
    event = h.wait_event(lambda e: e["event"] == "project.archive.changed", start=mark)
    assert event["data"] == {"handle": handle, "kinds": ["analysis", "context", "draft", "workflow", "workflow_run"]}
    listed = h.call("project.archive.list", {"handle": handle})
    assert [(item["kind"], item["id"], item["note"]) for item in listed["items"]] == [
        (item["kind"], item["id"], "Old scan") for item in items]
    assert listed["counts"]["workflow"] == 1 and listed["counts"]["simulation_run"] == 0
    assert h.call("project.archive.list", {"handle": handle, "kind": "draft"})["items"][0]["id"] == draft["id"]
    # Archiving again changes nothing (and announces nothing); restoring brings each back.
    assert h.call("project.archive.set", {"handle": handle, "items": items, "archived": True})["changed"] == 0
    assert store.archive.is_archived("workflow", ids["workflow"])
    restored = h.call("project.archive.set", {"handle": handle, "items": items[:2], "archived": False})
    assert restored["changed"] == 2 and not store.archive.is_archived("workflow", ids["workflow"])
    assert {item["kind"] for item in h.call("project.archive.list", {"handle": handle})["items"]} == {"draft", "context", "workflow_run"}
    assert not h.violations


def test_unknown_or_running_objects_are_refused_and_nothing_is_written(setup):
    h, store, ids, handle, worker = setup
    running = store.workflow_runs.prepare(ids["workflow"], ids["rows"][:1], run_id=str(uuid4()), expected_revision=store.info()["revision"])
    store.workflow_runs.start(running["id"], executor_id=str(uuid4()))
    for items, message in (([{"kind": "workflow_run", "id": running["id"]}], "still running"),
                           ([{"kind": "workflow", "id": ids["workflow"]}, {"kind": "draft", "id": str(uuid4())}], "No draft"),
                           ([{"kind": "analysis", "id": ids["workflow"]}], "No analysis")):  # a workflow is not an analysis
        error = h.error("project.archive.set", {"handle": handle, "items": items, "archived": True})
        assert message in error["message"]
    assert h.call("project.archive.list", {"handle": handle})["items"] == []
    with pytest.raises(Exception):
        h.call("project.archive.set", {"handle": handle, "items": [{"kind": "file", "id": ids["workflow"]}], "archived": True})


def test_a_workflow_can_take_its_stopped_runs_with_it(setup):
    h, store, ids, handle, worker = setup
    first, second = finished_run(store, ids, ids["rows"][:1]), finished_run(store, ids, ids["rows"][1:2])
    running = store.workflow_runs.prepare(ids["workflow"], ids["rows"][2:], run_id=str(uuid4()), expected_revision=store.info()["revision"])
    store.workflow_runs.start(running["id"], executor_id=str(uuid4()))
    changed = h.call("project.archive.set", {"handle": handle, "items": [{"kind": "workflow", "id": ids["workflow"]}],
                                             "archived": True, "include_runs": True})
    assert changed["changed"] == 3 and {item["id"] for item in changed["items"]} == {ids["workflow"], first, second}
    assert not store.archive.is_archived("workflow_run", running["id"])  # still running: left alone
    back = h.call("project.archive.set", {"handle": handle, "items": [{"kind": "workflow", "id": ids["workflow"]}],
                                          "archived": False, "include_runs": True})
    assert back["changed"] == 3


def test_older_projects_have_nothing_archived_until_upgraded(tmp_path):
    store = ProjectStore.create(tmp_path / "old", "Old")
    with sqlite3.connect(store.directory / DATABASE_NAME) as db:
        db.execute("DROP TABLE project_archive")
        db.execute("PRAGMA user_version=10")
    assert store.archive.list() == {"items": [], "counts": {kind: 0 for kind in store.archive.list()["counts"]}}
    assert not store.archive.is_archived("workflow", str(uuid4())) and store.archive.ids("draft") == set()
    with pytest.raises(UnsupportedProjectFormat):
        store.archive.set([{"kind": "workflow", "id": str(uuid4())}], archived=True)
    upgraded = store.upgrade(expected_revision=0)
    assert upgraded["format_version"] == 11 and upgraded["backup"]
    with pytest.raises(ProjectError, match="No workflow"):
        store.archive.set([{"kind": "workflow", "id": str(uuid4())}], archived=True)
