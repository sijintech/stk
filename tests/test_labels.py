"""Data labels (format 12): data is private unless a person labels it public; labelling is not an edit."""
import sqlite3
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.store import DATABASE_NAME, UnsupportedProjectFormat
from test_bridge_workflow_runs import analysis_document, setup  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def test_data_is_private_until_labelled_public_and_labelling_is_not_an_edit(setup, tmp_path):
    h, store, ids, handle, worker = setup
    assert not store.labels.is_public("table", ids["cases"]) and store.labels.public_ids("table") == set()
    path = tmp_path / "field.vtk"
    path.write_text("not read\n")
    record = store.files.index([str(path)], expected_revision=store.info()["revision"])["record_ids"][0]
    before, history = store.snapshot(), store.history()
    mark = h.mark()
    items = [{"kind": "table", "id": ids["cases"]}, {"kind": "file", "id": record}]
    changed = h.call("project.labels.set", {"handle": handle, "items": items, "label": "public", "note": "Published dataset"})
    assert changed == {"changed": 2, "items": items}
    assert store.snapshot() == before and store.history() == history  # no revision, no undo
    event = h.wait_event(lambda e: e["event"] == "project.labels.changed", start=mark)
    assert event["data"] == {"handle": handle, "kinds": ["file", "table"]}
    listed = h.call("project.labels.list", {"handle": handle})["items"]
    assert [(item["kind"], item["id"], item["note"]) for item in listed] == [
        ("table", ids["cases"], "Published dataset"), ("file", record, "Published dataset")]
    assert h.call("project.labels.list", {"handle": handle, "kind": "file"})["items"][0]["id"] == record
    # Labelling again changes nothing; private again takes it back.
    assert h.call("project.labels.set", {"handle": handle, "items": items, "label": "public"})["changed"] == 0
    assert h.call("project.labels.set", {"handle": handle, "items": items[:1], "label": "private"})["changed"] == 1
    assert not store.labels.is_public("table", ids["cases"]) and store.labels.is_public("file", record)
    assert not h.violations


def test_unknown_objects_and_bad_labels_are_refused_without_writing(setup):
    h, store, ids, handle, worker = setup
    with pytest.raises(ProjectError, match="No table"):
        store.labels.set([{"kind": "table", "id": ids["cases"]}, {"kind": "table", "id": str(uuid4())}], label="public")
    assert not store.labels.is_public("table", ids["cases"])  # the whole call was refused
    with pytest.raises(ProjectError, match="No file"):
        store.labels.set([{"kind": "file", "id": ids["rows"][0]}], label="public")  # a parameter row is not a file
    with pytest.raises(ProjectError, match="public or private"):
        store.labels.set([{"kind": "table", "id": ids["cases"]}], label="shared")
    with pytest.raises(ProjectError, match="known kind"):
        store.labels.set([{"kind": "context", "id": ids["cases"]}], label="public")


def test_older_projects_label_nothing_until_upgraded(tmp_path):
    store = ProjectStore.create(tmp_path / "old", "Old")
    table = str(uuid4())
    store.apply([{"op": "create_table", "id": table, "name": "Cases"}], expected_revision=0)
    with sqlite3.connect(store.directory / DATABASE_NAME) as db:
        db.execute("DROP TABLE project_labels")
        db.execute("PRAGMA user_version=11")
    assert store.labels.list() == {"items": []} and not store.labels.is_public("table", table)
    with pytest.raises(UnsupportedProjectFormat):
        store.labels.set([{"kind": "table", "id": table}], label="public")
    assert store.upgrade(expected_revision=1)["format_version"] == 12
    assert store.labels.set([{"kind": "table", "id": table}], label="public")["changed"] == 1


def test_scripts_label_data_through_the_service(setup):
    from suan.scripting import Project
    h, store, ids, handle, worker = setup
    project = Project(h.call, handle)
    assert project.mark_public("table", [ids["cases"]], note="Shared")["changed"] == 1
    assert [(item["id"], item["note"]) for item in project.labels()["items"]] == [(ids["cases"], "Shared")]
    assert project.labels("file") == {"items": []}
    assert project.mark_private("table", [ids["cases"]])["changed"] == 1 and project.labels() == {"items": []}
    assert not h.violations
