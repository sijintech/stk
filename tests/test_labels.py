"""Data labels (format 12): data is private unless a person labels it public; labelling is not an edit."""
import sqlite3
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.store import _DDL_V12, DATABASE_NAME, UnsupportedProjectFormat
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
    with pytest.raises(ProjectError, match="public, structure or private"):
        store.labels.set([{"kind": "table", "id": ids["cases"]}], label="shared")
    with pytest.raises(ProjectError, match="known kind"):
        store.labels.set([{"kind": "context", "id": ids["cases"]}], label="public")


def test_older_projects_label_nothing_until_upgraded(tmp_path):
    store = ProjectStore.create(tmp_path / "old", "Old")
    table = str(uuid4())
    store.apply([{"op": "create_table", "id": table, "name": "Cases"}], expected_revision=0)
    with sqlite3.connect(store.directory / DATABASE_NAME) as db:
        db.execute("DROP TABLE IF EXISTS project_agent_objects")
        db.execute("DROP TABLE IF EXISTS project_agent_events")
        db.execute("DROP TABLE IF EXISTS project_agent_sessions")
        db.execute("DROP TABLE project_labels")
        db.execute("PRAGMA user_version=11")
    assert store.labels.list() == {"items": []} and not store.labels.is_public("table", table)
    with pytest.raises(UnsupportedProjectFormat):
        store.labels.set([{"kind": "table", "id": table}], label="public")
    assert store.upgrade(expected_revision=1)["format_version"] == 13
    assert store.labels.set([{"kind": "table", "id": table}], label="public")["changed"] == 1


def test_scripts_label_data_through_the_service(setup):
    from suan.scripting import Project
    h, store, ids, handle, worker = setup
    project = Project(h.call, handle)
    assert project.mark_public("table", [ids["cases"]], note="Shared")["changed"] == 1
    assert [(item["id"], item["note"]) for item in project.labels()["items"]] == [(ids["cases"], "Shared")]
    assert project.labels("file") == {"items": []}
    assert project.mark_private("table", [ids["cases"]])["changed"] == 1 and project.labels() == {"items": []}
    assert project.mark_structure_public([ids["cases"]])["changed"] == 1 and project.labels() == {"items": []}
    assert [item["label"] for item in project.labels(include_structure=True)["items"]] == ["structure"]
    assert not h.violations


def test_a_tables_structure_can_be_public_while_its_values_stay_private(setup):
    """Format 13 (docs/design/agent-harness.md, owner decision 8): "structure" makes a table's names, fields, units and
    row count public; its values stay private, so nothing about the data boundary for values changes."""
    h, store, ids, handle, worker = setup
    table = {"kind": "table", "id": ids["cases"]}
    h.call("project.labels.set", {"handle": handle, "items": [table], "label": "structure"})
    assert store.labels.label("table", ids["cases"]) == "structure"
    assert store.labels.structure_public("table", ids["cases"]) and not store.labels.is_public("table", ids["cases"])
    assert h.call("project.labels.list", {"handle": handle})["items"] == []  # the default list is public data only
    listed = h.call("project.labels.list", {"handle": handle, "include_structure": True})["items"]
    assert [(item["id"], item["label"]) for item in listed] == [(ids["cases"], "structure")]
    h.call("project.labels.set", {"handle": handle, "items": [table], "label": "public"})
    assert store.labels.structure_public("table", ids["cases"]) and store.labels.is_public("table", ids["cases"])
    assert [item["label"] for item in h.call("project.labels.list", {"handle": handle})["items"]] == ["public"]
    with pytest.raises(ProjectError, match="Only a table's structure"):
        store.labels.set([{"kind": "file", "id": ids["cases"]}], label="structure")
    assert not store.labels.structure_public("table", str(uuid4()))  # unknown: private


def test_upgrading_to_format_13_keeps_every_label(setup):
    h, store, ids, handle, worker = setup
    store.labels.set([{"kind": "table", "id": ids["cases"]}], label="public", note="kept")
    store.labels.set([{"kind": "table", "id": ids["cases"]}], label="private")
    store.labels.set([{"kind": "table", "id": ids["cases"]}], label="public", note="kept again")
    before = store.labels.list()
    with sqlite3.connect(store.path) as db:  # a format-12 database: no agent tables, labels without "structure"
        for table in ("project_agent_objects", "project_agent_events", "project_agent_sessions"):
            db.execute(f"DROP TABLE {table}")
        rows = db.execute("SELECT id, kind, object_id, label, at, note FROM project_labels ORDER BY id").fetchall()
        sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='project_labels'").fetchone()[0]
        db.execute("DROP TABLE project_labels")
        for statement in _DDL_V12:
            db.execute(statement)
        db.executemany("INSERT INTO project_labels VALUES (?,?,?,?,?,?)", rows)
        db.execute("PRAGMA user_version=12")
    with pytest.raises(UnsupportedProjectFormat, match="format 13"):
        store.labels.set([{"kind": "table", "id": ids["cases"]}], label="structure")
    upgraded = store.upgrade(expected_revision=store.info()["revision"])
    assert upgraded["format_version"] == 13 and upgraded["backup"]
    assert store.labels.list() == before and store.labels.is_public("table", ids["cases"])
    with sqlite3.connect(store.path) as db:  # the whole history, ids kept, and the new CHECK in place
        assert db.execute("SELECT id, kind, object_id, label, at, note FROM project_labels ORDER BY id").fetchall() == rows
        assert db.execute("SELECT seq FROM sqlite_sequence WHERE name='project_labels'").fetchone()[0] == sequence
        assert "'structure'" in db.execute("SELECT sql FROM sqlite_master WHERE name='project_labels'").fetchone()[0]
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.labels.set([{"kind": "table", "id": ids["cases"]}], label="structure")
    assert store.labels.label("table", ids["cases"]) == "structure"
