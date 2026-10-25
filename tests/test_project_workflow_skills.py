"""Frozen workflow skills copy their method closure and explicitly rebind project data."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import analyses, managed, skills, workflow_skills, workflows
from suan.skills import catalog
from test_workflow_runs import project, revision  # noqa: F401
from test_workflow_composition import call, child_document, document, parent_document, write
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_bridge_workflow_runs import setup, settled  # noqa: F401


def publish(store, identity, *, skill_id=None, create=True):
    skill_id = skill_id or str(uuid4())
    result = store.skills.publish_workflow(identity, project_skill_id=skill_id, create=create,
        name="Reusable workflow", description="A complete saved method", expected_revision=revision(store))
    return result, store.skills.get(skill_id)["skill"]


def active(skill):
    return next(item for item in skill["document"]["versions"] if item["content_sha256"] == skill["active"]["content_sha256"])


def bindings(skill):
    return {key: {identity: identity for identity in values}
            for key, values in active(skill)["template"]["dependencies"].items()}


def instantiate(store, skill, *, mapping=None, identity=None):
    return store.skills.create_workflow(skill["id"], skill["active"]["content_sha256"],
        workflow_id=identity or str(uuid4()), name="Copied workflow", bindings=bindings(skill) if mapping is None else mapping,
        expected_revision=revision(store))


def no_read(*args, **kwargs):
    raise AssertionError("A workflow skill must not load plugins, its source catalog, or file bytes")


def test_nested_closure_survives_deleted_sources_and_instances_undo_together(project, monkeypatch):
    store, ids = project
    child = write(store, child_document())
    root_doc = parent_document(ids, child)
    root_doc["steps"].insert(2, call(child, "again"))
    root = write(store, root_doc)
    from suan.workflows import templates
    monkeypatch.setattr(templates, "workflow_templates", no_read)
    monkeypatch.setattr(catalog, "load_catalog", no_read)
    before = revision(store)
    receipt, skill = publish(store, root)
    assert receipt["revision"] == before + 1
    frozen = active(skill)["template"]
    assert set(frozen["workflows"]) == {root, child}
    assert set(frozen["analyses"]) == {ids["analysis"]}
    assert frozen["source"] == {"project_id": store.info()["id"], "workflow_id": root, "revision": before,
                               "content_sha256": workflow_skills._digest(root_doc)}
    store.apply([{"op": "delete_record", "id": identity} for identity in (root, child, ids["analysis"])],
                expected_revision=revision(store))
    before_snapshot = store.snapshot()
    before = revision(store)
    receipt = instantiate(store, skill)
    assert receipt["revision"] == before + 1
    copied = store.workflows.get(receipt["record_id"])["workflow"]["document"]
    first, second = copied["steps"][1:3]
    assert first["ref"] == second["ref"] and first["ref"]["workflow"] != child
    copied_child = store.workflows.get(first["ref"]["workflow"])["workflow"]["document"]
    assert copied_child["interface"] == child_document()["interface"]
    copied_analysis = store.analyses.get(copied["steps"][-1]["ref"]["analysis"])["analysis"]
    assert copied_analysis["document"]["graph"]["ui"]["project_skill"]["content_sha256"] == skill["active"]["content_sha256"]
    after_snapshot = store.snapshot()
    assert store.skills.get(skill["id"])["skill"] == skill
    store.undo(expected_revision=revision(store))
    assert store.snapshot()["tables"] == before_snapshot["tables"]
    store.redo(expected_revision=revision(store))
    assert store.snapshot()["tables"] == after_snapshot["tables"]
    assert ProjectStore(store.directory).skills.get(skill["id"])["skill"] == skill


def test_append_restore_and_explicit_wrong_kind_errors(project):
    store, ids = project
    _, first = publish(store, ids["workflow"])
    original = active(first)
    source = store.workflows.get(ids["workflow"])["workflow"]["document"]
    source["steps"][1]["parameters"]["temperature"] = 430
    store.workflows.update(ids["workflow"], "Changed", source, expected_revision=revision(store))
    _, second = publish(store, ids["workflow"], skill_id=first["id"], create=False)
    assert second["document"]["versions"][0] == original
    store.skills.restore(first["id"], first["active"]["content_sha256"], expected_revision=revision(store))
    _, third = publish(store, ids["workflow"], skill_id=first["id"], create=False)
    assert third["active"]["version"] == 3
    before = store.snapshot()
    with pytest.raises(ProjectError, match="workflow"):
        store.skills.create_analysis(first["id"], third["active"]["content_sha256"], analysis_id=str(uuid4()),
                                     name="Wrong kind", expected_revision=revision(store))
    with pytest.raises(ProjectError, match="new user skill"):
        store.skills.publish_analysis(ids["analysis"], project_skill_id=first["id"], create=False, name="Wrong kind",
                                      description="Must not change entry kind", expected_revision=revision(store))
    with pytest.raises(RevisionConflict):
        instantiate(store, first)
    assert store.snapshot() == before
    store.skills.publish_analysis(ids["analysis"], project_skill_id=(other := str(uuid4())), create=True, name="Analysis",
                                  description="Different kind", expected_revision=revision(store))
    analysis_skill = store.skills.get(other)["skill"]
    with pytest.raises(ProjectError, match="analysis"):
        store.skills.create_workflow(other, analysis_skill["active"]["content_sha256"], workflow_id=str(uuid4()),
                                     name="Wrong kind", bindings={}, expected_revision=revision(store))
    with pytest.raises(ProjectError, match="another skill kind"):
        publish(store, ids["workflow"], skill_id=other, create=False)


@pytest.mark.parametrize("damage", ["missing", "extra", "digest", "cycle", "dependency", "interface"])
def test_stored_closure_rejects_incomplete_or_tampered_content(project, damage):
    store, ids = project
    child = write(store, child_document())
    root = write(store, parent_document(ids, child))
    _, skill = publish(store, root)
    item = deepcopy(active(skill))
    template = item["template"]
    if damage == "missing":
        del template["analyses"][ids["analysis"]]
    elif damage == "extra":
        template["workflows"][str(uuid4())] = deepcopy(template["workflows"][child])
    elif damage == "digest":
        template["workflows"][child]["document"]["interface"]["parameters"][0]["default"] = 470
    elif damage == "cycle":
        doc = template["workflows"][child]["document"]
        doc["steps"].append({"id": "self", "kind": "workflow", "ref": {"workflow": child},
                             "inputs": {"rows": {"from": "$input.rows"}}})
        template["workflows"][child]["content_sha256"] = workflow_skills._digest(doc)
    elif damage == "dependency":
        template["dependencies"]["fields"].clear()
    elif damage == "interface":
        doc = template["workflows"][child]["document"]
        doc["interface"]["outputs"]["files"]["from"] = "simulate.absent"
        template["workflows"][child]["content_sha256"] = workflow_skills._digest(doc)
    item["content_sha256"] = workflow_skills._digest({key: item[key] for key in ("definition", "template")})
    with pytest.raises(ProjectError):
        skills._document({"format": skills.DOCUMENT_FORMAT, "active": item["content_sha256"], "versions": [item]})


def test_cross_project_mapping_is_explicit_typed_and_does_not_rewrite_literals(project, tmp_path, monkeypatch):
    source, ids = project
    marker = {"$field": ids["temperature"]}
    doc = document(source.workflows.get(ids["workflow"])["workflow"]["document"]["steps"],
                   parameters=[{"name": "payload", "type": "json", "default": marker}])
    doc["steps"][-1]["parameters"]["opaque"] = {"$literal": marker}
    doc["ui"]["original_id"] = ids["temperature"]
    root = write(source, doc)
    _, original = publish(source, root)
    frozen = active(original)
    target = ProjectStore.create(tmp_path / "destination", "Different project")
    table, temperature, label, wrong = [str(uuid4()) for _ in range(4)]
    target.apply([{"op": "create_table", "id": table, "name": "Same names do not identify a table"},
                  {"op": "add_field", "table_id": table, "id": temperature, "name": "T", "type": "number", "unit": "K"},
                  {"op": "add_field", "table_id": table, "id": label, "name": "Label", "type": "text"},
                  {"op": "add_field", "table_id": table, "id": wrong, "name": "T", "type": "number", "unit": "eV"}], expected_revision=0)
    monkeypatch.setattr(skills.ProjectSkills, "_capture", staticmethod(lambda *args: deepcopy(frozen)))
    skill_id = str(uuid4())
    target.skills.pin(frozen["definition"]["id"], 1, frozen["content_sha256"], project_skill_id=skill_id, expected_revision=1)
    imported = target.skills.get(skill_id)["skill"]
    before = target.snapshot()
    with pytest.raises(ProjectError, match="table binding"):
        instantiate(target, imported)
    mapping = {"tables": {ids["cases"]: table}, "fields": {ids["temperature"]: wrong, ids["label"]: label}, "snapshots": {}}
    with pytest.raises(ProjectError, match="type or unit"):
        instantiate(target, imported, mapping=mapping)
    assert target.snapshot() == before
    mapping["fields"][ids["temperature"]] = temperature
    copied = target.workflows.get(instantiate(target, imported, mapping=mapping)["record_id"])["workflow"]["document"]
    assert copied["steps"][0]["ref"]["table"] == table
    assert copied["steps"][1]["parameters"]["temperature"] == {"$field": temperature}
    assert copied["interface"]["parameters"][0]["default"] == marker
    assert copied["steps"][-1]["parameters"]["opaque"] == {"$literal": marker}
    assert copied["ui"]["original_id"] == ids["temperature"]
    assert active(imported) == frozen


def test_snapshot_bindings_use_only_metadata_and_require_the_declared_filenames(project, monkeypatch):
    store, ids = project
    paths = [store.directory / name for name in ("input.dat", "other.dat")]
    for path in paths:
        path.write_text("offline fixture", encoding="utf-8")
    indexed = store.files.index([str(path) for path in paths], expected_revision=revision(store))["record_ids"]
    first = store.snapshots.capture(indexed[:1], expected_revision=revision(store))["snapshot"]
    other = store.snapshots.capture(indexed[1:], expected_revision=revision(store))["snapshot"]
    root = write(store, document([{"id": "files", "kind": "files", "ref": {"snapshot": first["id"]}}],
                                 outputs={"files": {"type": "files", "from": "files.files"}}))
    from suan.project.snapshots import Snapshots
    monkeypatch.setattr(Snapshots, "resolve", no_read)
    _, skill = publish(store, root)
    dependency = active(skill)["template"]["dependencies"]["snapshots"][first["id"]]
    assert set(dependency) == {"sha256", "files"}
    assert dependency["files"][0]["name"] == "input.dat"
    mapping = bindings(skill)
    mapping["snapshots"][first["id"]] = other["id"]
    before = store.snapshot()
    with pytest.raises(ProjectError, match="file names"):
        instantiate(store, skill, mapping=mapping)
    assert store.snapshot() == before
    for path in paths:
        path.unlink()
    instantiate(store, skill)


@pytest.mark.parametrize("limit", ["versions", "collection", "snapshot", "commands"])
def test_limits_fail_without_any_partial_edit_or_undo_entry(project, monkeypatch, limit):
    store, ids = project
    _, skill = publish(store, ids["workflow"])
    before, history = store.snapshot(), store.history()
    if limit == "versions":
        monkeypatch.setattr(skills, "MAX_VERSIONS", 1)
        action = lambda: publish(store, ids["workflow"], skill_id=skill["id"], create=False)
    else:
        action = lambda: instantiate(store, skill)
        if limit == "collection":
            monkeypatch.setattr(analyses, "MAX_ANALYSES", 1)
        elif limit == "snapshot":
            size = len(json.dumps(before, ensure_ascii=False, separators=(",", ":")).encode())
            original = managed.snapshot_limit
            monkeypatch.setattr(workflow_skills, "snapshot_limit", lambda service, db, subject: original(service, db, subject, size + 1))
        else:
            original = ProjectStore._prepare_commands
            monkeypatch.setattr(ProjectStore, "_prepare_commands", staticmethod(lambda commands, rev: original(commands * 100, rev)))
    with pytest.raises(ProjectError):
        action()
    assert store.snapshot() == before and store.history() == history


def test_complete_snapshot_over_384_kib_can_be_read_and_instantiated(project):
    store, ids = project
    child_doc = child_document()
    child_doc["ui"]["notes"] = "a" * (205 * 1024)
    child = write(store, child_doc)
    root_doc = parent_document(ids, child)
    root_doc["ui"]["notes"] = "b" * (205 * 1024)
    root = write(store, root_doc)
    _, skill = publish(store, root)
    assert len(catalog._canonical(skill["document"]).encode()) > 384 * 1024
    assert ProjectStore(store.directory).skills.get(skill["id"])["skill"] == skill
    instantiate(store, skill)


@pytest.mark.parametrize("damage", ["field_type", "title"])
def test_damaged_dependency_metadata_is_an_invalid_record_not_a_failed_list(project, damage):
    store, ids = project
    _, skill = publish(store, ids["workflow"])
    item = deepcopy(active(skill))
    if damage == "field_type":
        item["template"]["dependencies"]["fields"][ids["temperature"]]["type"] = {}
    else:
        item["template"]["name"] = "x" * 121
    item["content_sha256"] = workflow_skills._digest({key: item[key] for key in ("definition", "template")})
    store.apply([{"op": "set_cell", "table_id": skills.TABLE_ID, "record_id": skill["id"],
                  "field_id": skills.FIELD_IDS[key], "value": value}
                 for key, value in (("versions", [item]), ("active", item["content_sha256"]))], expected_revision=revision(store))
    assert store.skills.get(skill["id"])["skill"]["state"] == "invalid"
    assert store.skills.list()["skills"][0]["state"] == "invalid"


def test_a_closure_that_cannot_fit_any_atomic_edit_is_refused_at_publication(project):
    store, ids = project
    root, commands, steps = str(uuid4()), [], []
    original_analysis = store.analyses.get(ids["analysis"])["analysis"]["document"]
    for category, count, module, doc in (("nested", 90, workflows, document([])),
                                        ("analysis", 80, analyses, original_analysis)):
        for number in range(count):
            identity = str(uuid4())
            commands.append({"op": "add_record", "table_id": module.TABLE_ID, "id": identity})
            values = {"name": "Frozen child", **doc}
            commands.extend({"op": "set_cell", "table_id": module.TABLE_ID, "record_id": identity,
                             "field_id": module.FIELD_IDS[key], "value": value} for key, value in values.items())
            kind = "workflow" if category == "nested" else "analysis"
            steps.append({"id": f"{category}_{number}", "kind": kind, "ref": {kind: identity}})
    for offset in range(0, len(commands), 500):
        store.apply(commands[offset:offset + 500], expected_revision=revision(store))
    write(store, document(steps), root)
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError, match="1000-command"):
        publish(store, root)
    assert store.snapshot() == before and store.history() == history


def test_published_method_executes_after_all_source_definitions_are_deleted(setup):
    harness, store, ids, handle, worker = setup
    child = write(store, child_document())
    root_doc = parent_document(ids, child)
    root_doc["steps"][-1]["parameters"] = {"level": {"$field": ids["temperature"]}}
    root = write(store, root_doc)
    _, skill = publish(store, root)
    store.apply([{"op": "delete_record", "id": identity} for identity in (root, child, ids["analysis"])],
                expected_revision=revision(store))
    copied = instantiate(store, skill)["record_id"]
    run = harness.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": copied,
        "rows": ids["rows"], "run_id": str(uuid4()), "expected_revision": revision(store)})["run"]
    assert worker.levels == []
    harness.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    result = settled(harness, handle, run["id"])
    assert result["complete"] and result["counts"] == {"succeeded": 6}
    assert worker.levels == [300, 325, 350]
    assert not harness.violations
