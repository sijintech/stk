"""Local method publication uses reviewed immutable versions across projects, without execution."""
from copy import deepcopy
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.scripting import Project
from suan.scripting.skills import Skills
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_workflow_skill_bridge import source_project


def saved_method(harness, directory, kind):
    store, analysis, child, root = source_project(directory)
    handle = harness.call("project.open", {"directory": str(directory)})["project"]["handle"]
    project = Project(harness.call, handle)
    identity = str(uuid4())
    publish = project.skills.publish_workflow if kind == "workflow.document" else project.skills.publish_analysis
    publish(root if kind == "workflow.document" else analysis, project_skill_id=identity, create=True,
            name="Shared method", description="Complete immutable method", expected_revision=3)
    saved = project.skills.get(identity)["skill"]
    return store, project, identity, saved, (root, child, analysis)


@pytest.mark.parametrize("kind", ["graph.document", "workflow.document"])
def test_publish_pin_and_instantiate_in_another_project_without_plugins(inproc, tmp_path, monkeypatch, kind):
    from suan.graph import catalog as graph_catalog
    from suan.agent.levels import level

    harness = inproc("shared-library")
    hello = harness.call("hello", {"protocol": 1})
    assert {"project.skills.publish_global", "skills.publication.get"} <= set(hello["methods"])
    assert "skills.changed" in hello["events"]
    store, source, identity, saved, source_ids = saved_method(harness, tmp_path / "source", kind)

    def forbidden(*args, **kwargs):
        raise AssertionError("Browsing and copying a method must not load executable plugins")

    monkeypatch.setattr(graph_catalog, "load_entry_points", forbidden)
    monkeypatch.setattr(harness.bridge.graphs, "registry", forbidden)
    before, history = deepcopy(store.snapshot()), store.history()
    event_mark = harness.mark()
    publication_id = str(uuid4())
    receipt = source.skills.publish_global(identity, saved["active"]["content_sha256"],
        publication_id=publication_id, mode="exact", expected_revision=4)
    assert receipt["publication_id"] == publication_id and receipt["mode"] == "exact"
    assert receipt["source"] == {"project_id": before["project"]["id"], "project_skill_id": identity,
                                  "revision": 4, "content_sha256": saved["active"]["content_sha256"]}
    assert receipt["skill"] == {key: saved["active"][key] for key in ("version", "ref", "content_sha256")} | {
        "id": saved["active"]["skill_id"], "source": "user"}
    assert store.snapshot() == before and store.history() == history
    harness.wait_event(lambda event: event["event"] == "skills.changed", start=event_mark)
    assert not any(event["event"] == "project.changed" for event in harness.events[event_mark:])

    catalog = Skills(harness.call)
    listed = catalog.list(query=receipt["skill"]["id"])
    assert listed["total"] == 1 and listed["skills"][0]["entry"]["kind"] == kind
    detail = catalog.get(receipt["skill"]["id"], version=1)
    assert detail["source"] == "user" and detail["availability"]["status"] == "unchecked"
    assert detail["content_sha256"] == saved["active"]["content_sha256"]
    if kind == "workflow.document":
        assert detail["method"] == {"workflow_count": 2, "analysis_count": 1,
                                     "data_dependencies": {"tables": 0, "fields": 0, "snapshots": 0}}

    source.apply([{"op": "delete_record", "id": item} for item in source_ids], expected_revision=4)
    # A committed publication remains the same request even after source revision/content changes.
    assert source.skills.publish_global(identity, saved["active"]["content_sha256"],
        publication_id=publication_id, mode="exact", expected_revision=4) == receipt
    harness.call("project.close", {"handle": source.handle})
    assert catalog.publication(publication_id) == receipt

    destination = ProjectStore.create(tmp_path / "destination", "Consumer")
    handle = harness.call("project.open", {"directory": str(destination.directory)})["project"]["handle"]
    target = Project(harness.call, handle)
    pinned_id = str(uuid4())
    target.skills.pin(receipt["skill"]["id"], 1, receipt["skill"]["content_sha256"],
                      project_skill_id=pinned_id, expected_revision=0)
    pinned = target.skills.get(pinned_id)["skill"]
    assert pinned["document"] == saved["document"]
    created_id = str(uuid4())
    if kind == "workflow.document":
        target.skills.create_workflow(pinned_id, receipt["skill"]["content_sha256"], workflow_id=created_id,
            name="Independent method", bindings={"tables": {}, "fields": {}, "snapshots": {}}, expected_revision=1)
        copied = destination.workflows.get(created_id)["workflow"]["document"]
        children = {step["ref"]["workflow"] for step in copied["steps"]}
        assert len(children) == 1 and not children.intersection(source_ids)
        assert destination.workflows.list()["total"] == 2 and destination.analyses.list()["total"] == 1
    else:
        target.skills.create_analysis(pinned_id, receipt["skill"]["content_sha256"], analysis_id=created_id,
                                      name="Independent analysis", expected_revision=1)
        copied = destination.analyses.get(created_id)["analysis"]["document"]
        assert copied["parameters"] == saved["document"]["versions"][0]["template"]["parameters"]
    target.undo(expected_revision=2)
    assert target.skills.get(pinned_id)["skill"]["document"] == saved["document"]

    isolated = inproc("different-library")
    assert isolated.call("skills.list", {"query": receipt["skill"]["id"]})["total"] == 0
    assert isolated.error("skills.publication.get", {"publication_id": publication_id})["code"] == "not_found"
    assert harness.bridge.graphs.worker._child is None
    assert level("project.skills.publish_global") == "project_edit"
    harness.assert_clean()


def test_explicit_new_global_version_preserves_project_history_and_old_version(inproc, tmp_path):
    harness = inproc()
    store, project, identity, saved, _ = saved_method(harness, tmp_path / "versions", "workflow.document")
    digest = saved["active"]["content_sha256"]
    first_id = str(uuid4())
    first = project.skills.publish_global(identity, digest, publication_id=first_id, mode="exact", expected_revision=4)
    original, history = deepcopy(store.snapshot()), store.history()
    newer = project.skills.publish_global(identity, digest, publication_id=str(uuid4()), mode="new_version", expected_revision=4)
    assert newer["skill"]["version"] == 2 and newer["skill"]["id"] == first["skill"]["id"]
    assert newer["skill"]["content_sha256"] != first["skill"]["content_sha256"]
    assert store.snapshot() == original and store.history() == history
    rows = harness.call("skills.list", {"query": first["skill"]["id"]})["skills"]
    assert [row["version"] for row in rows] == [1, 2]
    error = harness.error("project.skills.publish_global", {"handle": project.handle,
        "project_skill_id": identity, "content_sha256": digest, "publication_id": first_id,
        "mode": "new_version", "expected_revision": 4})
    assert error["code"] == "conflict"
    stale_id = str(uuid4())
    error = harness.error("project.skills.publish_global", {"handle": project.handle,
        "project_skill_id": identity, "content_sha256": digest, "publication_id": stale_id,
        "mode": "exact", "expected_revision": 3})
    assert error["code"] == "conflict"
    assert harness.error("skills.publication.get", {"publication_id": stale_id})["code"] == "not_found"
    harness.assert_clean()


def test_highest_project_version_can_be_published_exactly_but_not_incremented(inproc, tmp_path):
    import hashlib
    from suan.graph.schema import canonical_json
    from suan.project.skills import FIELD_IDS, TABLE_ID
    from suan.skills.catalog import MAX_VERSION

    harness = inproc()
    store, project, identity, saved, _ = saved_method(harness, tmp_path / "maximum", "graph.document")
    snapshot = deepcopy(saved["document"]["versions"][0])
    snapshot["definition"]["version"] = MAX_VERSION
    snapshot["content_sha256"] = hashlib.sha256(canonical_json({key: snapshot[key] for key in
                                                               ("definition", "template")})).hexdigest()
    project.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                    "field_id": FIELD_IDS[key], "value": value} for key, value in
                   (("active", snapshot["content_sha256"]), ("versions", [snapshot]))], expected_revision=4)
    receipt = project.skills.publish_global(identity, snapshot["content_sha256"], publication_id=str(uuid4()),
                                            mode="exact", expected_revision=5)
    assert receipt["skill"]["version"] == MAX_VERSION
    publication_id = str(uuid4())
    error = harness.error("project.skills.publish_global", {"handle": project.handle,
        "project_skill_id": identity, "content_sha256": snapshot["content_sha256"], "publication_id": publication_id,
        "mode": "new_version", "expected_revision": 5})
    assert error["code"] == "conflict"
    assert harness.error("skills.publication.get", {"publication_id": publication_id})["code"] == "not_found"
    assert store.info()["revision"] == 5
    harness.assert_clean()


@pytest.mark.parametrize("record", ["payload", "receipt"])
def test_corrupt_user_library_content_reports_reviewable_conflict(inproc, tmp_path, record):
    import sqlite3

    harness = inproc()
    _, project, identity, saved, _ = saved_method(harness, tmp_path / "damaged", "graph.document")
    receipt = project.skills.publish_global(identity, saved["active"]["content_sha256"],
        publication_id=str(uuid4()), mode="exact", expected_revision=4)
    with sqlite3.connect(harness.bridge.skill_library.path) as db:
        if record == "payload":
            db.execute("UPDATE versions SET payload='{}'")
        else:
            db.execute("UPDATE publications SET receipt='{}'")
    method = "skills.get" if record == "payload" else "skills.publication.get"
    params = ({"id": receipt["skill"]["id"], "version": 1} if record == "payload" else
              {"publication_id": receipt["publication_id"]})
    error = harness.error(method, params)
    assert error["code"] == "conflict" and error["data"]["catalog_code"] == "invalid_definition"
    assert error["retryable"] is False
    # Unrelated built-in methods remain visible; listing does not expand the damaged payload.
    assert harness.call("skills.list", {"query": "stk.muferro"})["total"] > 0
    harness.assert_clean()


def test_accepted_long_method_name_survives_catalog_response_and_pin(inproc, tmp_path):
    import hashlib
    from suan.graph.schema import canonical_json
    from suan.project.skills import FIELD_IDS, TABLE_ID

    harness = inproc()
    _, project, identity, saved, _ = saved_method(harness, tmp_path / "long-name", "graph.document")
    snapshot = deepcopy(saved["document"]["versions"][0])
    snapshot["template"]["name"] = "方" * 4096
    snapshot["content_sha256"] = hashlib.sha256(canonical_json({key: snapshot[key] for key in
                                                               ("definition", "template")})).hexdigest()
    project.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                    "field_id": FIELD_IDS[key], "value": value} for key, value in
                   (("active", snapshot["content_sha256"]), ("versions", [snapshot]))], expected_revision=4)
    assert project.skills.get(identity)["skill"]["state"] == "readable"
    receipt = project.skills.publish_global(identity, snapshot["content_sha256"], publication_id=str(uuid4()),
                                            mode="exact", expected_revision=5)
    skill = Skills(harness.call).get(receipt["skill"]["id"], version=1)
    assert skill["entry"]["name"] == snapshot["template"]["name"]
    copy_id = str(uuid4())
    project.skills.pin(skill["id"], 1, skill["content_sha256"], project_skill_id=copy_id, expected_revision=5)
    assert project.skills.get(copy_id)["skill"]["document"]["versions"][0] == snapshot
    harness.assert_clean()
