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


def draft(store, ids, value, title):
    return store.drafts.save([{"op": "set_cell", "table_id": ids["cases"], "record_id": ids["rows"][0],
                               "field_id": ids["temperature"], "value": value}],
                             expected_revision=store.info()["revision"], title=title, draft_id=str(uuid4()))["id"]


def test_lists_filter_archived_objects_with_correct_paging(setup):
    h, store, ids, handle, worker = setup
    drafts = [draft(store, ids, 300 + i, f"Draft {i}") for i in range(5)]
    store.archive.set([{"kind": "draft", "id": drafts[1]}, {"kind": "draft", "id": drafts[3]}], archived=True)
    first = h.call("project.drafts.list", {"handle": handle, "limit": 2, "archived": False})
    assert [d["id"] for d in first["drafts"]] == [drafts[0], drafts[2]] and first["next_offset"] == 2
    second = h.call("project.drafts.list", {"handle": handle, "offset": 2, "limit": 2, "archived": False})
    assert [d["id"] for d in second["drafts"]] == [drafts[4]] and second["next_offset"] is None
    assert [d["id"] for d in h.call("project.drafts.list", {"handle": handle, "archived": True})["drafts"]] == [drafts[1], drafts[3]]
    assert len(h.call("project.drafts.list", {"handle": handle})["drafts"]) == 5  # unfiltered: everything, as before
    # Managed tables count with the filter too.
    other = str(uuid4())
    store.analyses.create("Other", analysis_document(), analysis_id=other, expected_revision=store.info()["revision"])
    store.archive.set([{"kind": "analysis", "id": other}], archived=True)
    live = h.call("project.analyses.list", {"handle": handle, "archived": False})
    assert live["total"] == 1 and [a["id"] for a in live["analyses"]] == [ids["analysis"]]
    assert h.call("project.analyses.list", {"handle": handle, "archived": True})["total"] == 1
    run = finished_run(store, ids, ids["rows"][:1])
    store.archive.set([{"kind": "workflow_run", "id": run}], archived=True)
    assert h.call("project.workflow_runs.list", {"handle": handle, "workflow_id": ids["workflow"], "archived": False})["runs"] == []
    assert [r["id"] for r in h.call("project.workflow_runs.list", {"handle": handle, "archived": True})["runs"]] == [run]
    assert not h.violations


def test_archived_objects_are_read_only_until_restored(setup):
    h, store, ids, handle, worker = setup
    saved = store.workflows.get(ids["workflow"])["workflow"]
    context = store.contexts.capture(table_id=ids["cases"], record_ids=ids["rows"][:1], field_ids=[ids["temperature"]],
                                     expected_revision=store.info()["revision"], title="Scope", context_id=str(uuid4()))
    message = store.discussion.add("Why?", message_id=str(uuid4()), context_id=context["id"])
    request = store.requests.create(message["id"], request_id=str(uuid4()), configuration={"adapter": "controlled/1", "model": "m"})
    pending = draft(store, ids, 305, "Pending")
    run = finished_run(store, ids, ids["rows"][:1])
    items = [{"kind": "workflow", "id": ids["workflow"]}, {"kind": "draft", "id": pending}, {"kind": "context", "id": context["id"]},
             {"kind": "request", "id": request["id"]}, {"kind": "workflow_run", "id": run}]
    store.archive.set(items, archived=True)
    revision = store.info()["revision"]
    refused = [
        lambda: h.call("project.workflows.update", {"handle": handle, "workflow_id": ids["workflow"], "name": "Renamed",
                                                     "document": saved["document"], "expected_revision": revision}),
        lambda: h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": ids["workflow"], "rows": ids["rows"][:1],
                                                          "run_id": str(uuid4()), "expected_revision": revision}),
        lambda: h.call("project.workflow_runs.start", {"handle": handle, "run_id": run}),
        lambda: h.call("project.drafts.apply", {"handle": handle, "draft_id": pending, "expected_revision": revision}),
        lambda: h.call("project.drafts.discard", {"handle": handle, "draft_id": pending}),
        lambda: h.call("project.discussion.add", {"handle": handle, "message_id": str(uuid4()), "context_id": context["id"],
                                                   "text": "More?"}),
        lambda: h.call("project.requests.create", {"handle": handle, "message_id": message["id"], "request_id": str(uuid4()),
                                                    "configuration": {"adapter": "controlled/1", "model": "m"}}),
        lambda: h.call("project.requests.start", {"handle": handle, "request_id": request["id"]}),
    ]
    for call in refused:
        with pytest.raises(Exception, match="archived; restore it"):
            call()
    assert store.info()["revision"] == revision and store.drafts.get(pending)["status"] == "pending"
    # Reading stays possible; restoring makes them usable again.
    assert h.call("project.workflows.get", {"handle": handle, "workflow_id": ids["workflow"]})["workflow"]["id"] == ids["workflow"]
    store.archive.set(items, archived=False)
    assert h.call("project.drafts.discard", {"handle": handle, "draft_id": pending})["draft"]["status"] == "discarded"
    h.call("project.discussion.add", {"handle": handle, "message_id": str(uuid4()), "context_id": context["id"], "text": "More?"})


def test_an_archived_analysis_cannot_be_run_directly_or_through_a_workflow(setup):
    h, store, ids, handle, worker = setup
    store.archive.set([{"kind": "analysis", "id": ids["analysis"]}], archived=True)
    with pytest.raises(Exception, match="uses an archived analysis"):
        store.workflow_runs.prepare(ids["workflow"], ids["rows"][:1], run_id=str(uuid4()), expected_revision=store.info()["revision"])
    with pytest.raises(Exception, match="archived; restore it to run it"):
        store.analysis_runs.prepare(ids["analysis"], str(uuid4()), {"data": {"field.vtk": str(uuid4())}}, run_id=str(uuid4()),
                                    expected_revision=store.info()["revision"])


def test_archived_objects_leave_attention_and_are_marked_in_search(setup):
    h, store, ids, handle, worker = setup
    executor = str(uuid4())
    failed = store.workflow_runs.prepare(ids["workflow"], ids["rows"][:1], run_id=str(uuid4()), expected_revision=store.info()["revision"])
    store.workflow_runs.start(failed["id"], executor_id=executor)
    attempt = store.workflow_runs.begin_attempt(failed["id"], "simulate", ids["rows"][0], executor_id=executor)
    store.workflow_runs.finish_attempt(failed["id"], "simulate", ids["rows"][0], attempt, "failed", executor_id=executor,
                                       error={"code": "x", "message": "No field"})
    store.workflow_runs.stop(failed["id"], executor_id=executor)
    assert [item["id"] for item in h.call("project.attention.list", {"handle": handle})["items"]] == [failed["id"]]
    store.archive.set([{"kind": "workflow_run", "id": failed["id"]}], archived=True)
    assert h.call("project.attention.list", {"handle": handle})["items"] == []
    second = str(uuid4())
    store.workflows.create("Scan B", store.workflows.get(ids["workflow"])["workflow"]["document"], workflow_id=second,
                           expected_revision=store.info()["revision"])
    store.archive.set([{"kind": "workflow", "id": ids["workflow"]}], archived=True)
    found = h.call("project.search", {"handle": handle, "query": "scan"})["results"]
    assert [(item["id"], item.get("archived", False)) for item in found] == [(second, False), (ids["workflow"], True)]
    assert not h.violations


def test_batches_check_the_archive_through_the_console():
    from suan.workflows.batches import _archived

    class Project:
        def __init__(self, items=None, error=None):
            self.items, self.error = items, error

        def archived(self, kind):
            if self.error:
                raise self.error
            return {"items": self.items, "counts": {}}
    batch = str(uuid4())
    assert _archived(Project([{"kind": "batch", "id": batch}]), batch)
    assert not _archived(Project([]), batch)
    assert not _archived(Project(error=RuntimeError("unknown method")), batch)  # an older service archives nothing
