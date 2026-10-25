"""Project-owned versions survive catalog replacement, recovery and portable workspace transfer."""
from copy import deepcopy
import hashlib
import json
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.skills import FIELD_IDS, TABLE_ID, ProjectSkillNotFound
from suan.skills import catalog
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.fixture
def store(tmp_path):
    return ProjectStore.create(tmp_path / "project", "Saved skills")


def pin(store, item=None, identity=None, revision=None):
    item = item or catalog.load_catalog().get("stk.muferro.energy_trace", 1)
    return store.skills.pin(item["id"], item["version"], item["content_sha256"],
        project_skill_id=identity or str(uuid4()),
        expected_revision=store.info()["revision"] if revision is None else revision)["record_id"]


def saved(store, identity):
    return store.skills.get(identity)["skill"]


def unavailable(*args, **kwargs):
    raise AssertionError("Stored versions must not access the catalog")


def replacement(tmp_path, monkeypatch, original, version=2):
    root = tmp_path / "replacement"
    root.mkdir(exist_ok=True)
    definition = deepcopy(original["definition"])
    definition["version"] = version
    definition["title"]["en"] = "Revised method"
    (root / (definition["id"] + ".json")).write_text(json.dumps(definition), encoding="utf-8")
    monkeypatch.setattr(catalog, "_builtin_root", lambda: root)
    return catalog.load_catalog().get(definition["id"], version)


def test_empty_read_has_no_table_or_revision_side_effects(store):
    before = store.snapshot()
    assert store.skills.list()["skills"] == []
    with pytest.raises(ProjectSkillNotFound):
        store.skills.get(str(uuid4()))
    assert store.snapshot() == before and store.history() == []


def test_saved_skills_cannot_be_used_as_workflow_parameter_tables(store):
    pin(store)
    before = store.snapshot()
    assert store.workflows.choices()["tables"] == []
    result = store.workflows.validate({"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "saved", "kind": "table", "ref": {"table": TABLE_ID}}]})
    assert not result["ok"]
    assert any(item["code"] == "missing_reference" for item in result["issues"])
    assert store.snapshot() == before


def test_damaged_long_format_still_has_a_schema_valid_error_reply(store):
    from suan.desktop_bridge.schema import validate_outgoing
    identity = pin(store)
    store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                  "field_id": FIELD_IDS["format"], "value": "x" * 129}], expected_revision=1)
    result = store.skills.get(identity)
    assert result["skill"]["state"] == "unsupported" and result["skill"]["format"] is None
    validate_outgoing({"id": 1, "result": result}, "project.skills.get")


def test_all_builtin_versions_are_complete_copies_in_one_edit_each(store):
    source = catalog.load_catalog()
    for index, item in enumerate(source.skills):
        identity = pin(store, item)
        version = saved(store, identity)["document"]["versions"][0]
        assert {key: version[key] for key in ("definition", "template")} == source.freeze(
            item["id"], item["version"], item["content_sha256"])
        assert store.info()["revision"] == index + 1
    page = store.skills.list(offset=1, limit=2)
    assert page["total"] == 6 and len(page["skills"]) == 2
    assert all("document" not in item for item in page["skills"])


def test_pin_undo_redo_and_reopen_without_catalog(store, monkeypatch):
    identity = pin(store)
    before = saved(store, identity)
    monkeypatch.setattr(catalog, "load_catalog", unavailable)
    assert saved(ProjectStore(store.directory), identity) == before
    store.undo(expected_revision=1)
    assert store.skills.list()["total"] == 0
    store.redo(expected_revision=2)
    assert saved(store, identity) == before


def test_upgrade_retains_old_content_and_restore_never_reads_catalog(store, tmp_path, monkeypatch):
    identity = pin(store)
    original = saved(store, identity)
    item = replacement(tmp_path, monkeypatch, original["document"]["versions"][0])
    # Merely changing the installed catalog does not change this project's selected method.
    assert saved(store, identity) == original
    store.skills.upgrade(identity, item["version"], item["content_sha256"], expected_revision=1)
    upgraded = saved(store, identity)
    assert upgraded["active"]["version"] == 2 and len(upgraded["versions"]) == 2
    assert upgraded["document"]["versions"][0] == original["document"]["versions"][0]
    with pytest.raises(ProjectError, match="newer version"):
        store.skills.upgrade(identity, item["version"], item["content_sha256"], expected_revision=2)
    monkeypatch.setattr(catalog, "load_catalog", unavailable)
    store.skills.restore(identity, original["active"]["content_sha256"], expected_revision=2)
    restored = saved(store, identity)
    assert restored["active"] == original["active"] and restored["versions"] == upgraded["versions"]
    store.undo(expected_revision=3)
    assert saved(store, identity) == upgraded


def test_catalog_drift_and_stale_writes_leave_project_unchanged(store, tmp_path, monkeypatch):
    item = catalog.load_catalog().get("stk.muferro.energy_trace", 1)
    identity = pin(store, item)
    before = store.snapshot()
    replacement(tmp_path, monkeypatch, saved(store, identity)["document"]["versions"][0], version=1)
    with pytest.raises(RevisionConflict, match="content changed"):
        pin(store, item)
    with pytest.raises(RevisionConflict):
        store.skills.restore(identity, item["content_sha256"], expected_revision=0)
    with pytest.raises(ProjectError, match="not saved"):
        store.skills.restore(identity, "0" * 64, expected_revision=1)
    assert store.snapshot() == before


def test_freeze_uses_the_pair_from_catalog_read_and_detaches_it(monkeypatch):
    source = catalog.load_catalog()
    item = source.get("stk.muferro.energy_trace", 1)
    from suan.graph import catalog as graphs
    monkeypatch.setattr(graphs, "preset_document", unavailable)
    content = source.freeze(item["id"], 1, item["content_sha256"])
    content["template"]["graph"]["name"] = "Changed copy"
    assert source.freeze(item["id"], 1, item["content_sha256"])["template"]["graph"]["name"] != "Changed copy"


def test_analysis_uses_saved_graph_and_provenance_without_installed_skill(store, monkeypatch):
    identity = pin(store)
    original = saved(store, identity)
    monkeypatch.setattr(catalog, "load_catalog", unavailable)
    analysis_id = str(uuid4())
    result = store.skills.create_analysis(identity, original["active"]["content_sha256"],
        analysis_id=analysis_id, name="My analysis", expected_revision=1)
    assert result["revision"] == 2 and result["record_id"] == analysis_id
    document = store.analyses.get(analysis_id)["analysis"]["document"]
    graph = deepcopy(document["graph"])
    provenance = graph.pop("ui")["project_skill"]
    assert provenance == {"id": identity, "ref": original["active"]["ref"],
                          "content_sha256": original["active"]["content_sha256"]}
    assert graph == original["document"]["versions"][0]["template"]["graph"]
    assert document["outputs"] == list(graph["outputs"])
    assert store.analysis_runs.list()["runs"] == []
    assert saved(store, identity) == original
    before = store.snapshot()
    with pytest.raises(RevisionConflict):
        store.skills.create_analysis(identity, "0" * 64, analysis_id=str(uuid4()), name="Bad", expected_revision=2)
    assert store.snapshot() == before
    store.undo(expected_revision=2)
    assert store.analyses.list()["total"] == 0 and saved(store, identity) == original


def test_workspace_roundtrip_and_creation_after_source_catalog_removed(store, tmp_path, monkeypatch):
    from suan.project import workspace_bundle as bundle
    identity = pin(store)
    original = saved(store, identity)
    state = {"format": "stk.desktop.workspace-state", "version": 1, "windows": [], "app": {}}
    exported = bundle.export_workspace(store.directory, tmp_path / "skills.stkworkspace", state=state)
    monkeypatch.setattr(catalog, "load_catalog", unavailable)
    imported = bundle.import_workspace(exported["path"], tmp_path / "new-machine", expected_sha256=exported["sha256"])
    moved = ProjectStore(imported["project_directory"])
    assert saved(moved, identity) == original
    moved.skills.create_analysis(identity, original["active"]["content_sha256"], analysis_id=str(uuid4()),
                                 name="Recovered analysis", expected_revision=moved.info()["revision"])
    assert moved.analyses.list()["total"] == 1


@pytest.mark.parametrize("damage", ["digest", "missing", "duplicate", "wrong_skill", "active", "format", "indirect"])
def test_invalid_versions_are_visible_and_cannot_create_or_restore(store, damage):
    identity = pin(store)
    original = saved(store, identity)
    document = original["document"]
    key, value = "versions", deepcopy(document["versions"])
    if damage == "digest":
        value[0]["template"]["graph"]["name"] = "Changed without a digest"
    elif damage == "missing":
        del value[0]["template"]["graph"]
    elif damage == "duplicate":
        value.append(deepcopy(value[0]))
    elif damage == "wrong_skill":
        other = deepcopy(value[0])
        other["definition"]["id"] = "stk.other.skill"
        other["definition"]["version"] = 2
        other["content_sha256"] = hashlib.sha256(catalog._canonical(
            {key: other[key] for key in ("definition", "template")}).encode()).hexdigest()
        value.append(other)
    elif damage == "active":
        key, value = "active", "0" * 64
    elif damage == "format":
        key, value = "format", "stk.project-skill/99"
    command = {"op": "set_cell", "table_id": TABLE_ID, "record_id": identity, "field_id": FIELD_IDS[key], "value": value}
    if damage == "indirect":
        command = {"op": "set_expression", "table_id": TABLE_ID, "record_id": identity,
                   "field_id": FIELD_IDS["name"], "expression": "1", "bindings": {}}
    store.apply([command], expected_revision=1)
    assert saved(store, identity)["state"] in {"invalid", "unsupported"}
    assert store.skills.list()["skills"][0]["error"]
    before = store.snapshot()
    with pytest.raises(ProjectError):
        store.skills.restore(identity, original["active"]["content_sha256"], expected_revision=2)
    with pytest.raises(ProjectError):
        store.skills.create_analysis(identity, original["active"]["content_sha256"], analysis_id=str(uuid4()),
                                     name="Bad", expected_revision=2)
    assert store.snapshot() == before


def test_bridge_and_script_share_contract_without_running(inproc, tmp_path):
    harness = inproc()
    harness.call("hello", {"protocol": 1})
    opened = harness.call("project.create", {"directory": str(tmp_path / "bridge-project"), "name": "Skills"})
    handle = opened["project"]["handle"]
    # The scripting facade uses the same checked operations as the desktop.
    from suan.scripting import Project
    project = Project(harness.call, handle)
    item = harness.call("skills.get", {"id": "stk.muferro.energy_trace", "version": 1})["skill"]
    identity = str(uuid4())
    result = project.skills.pin(item["id"], 1, item["content_sha256"], project_skill_id=identity, expected_revision=0)
    assert result["revision"] == 1
    assert project.skills.get(identity)["skill"]["active"]["ref"] == item["ref"]
    assert project.skills.list()["total"] == 1
    project.skills.create_analysis(identity, item["content_sha256"], analysis_id=str(uuid4()), name="Copied", expected_revision=1)
    assert harness.bridge.graphs.worker._child is None
    assert harness.error("project.skills.restore", {"handle": handle, "project_skill_id": identity,
        "content_sha256": item["content_sha256"], "expected_revision": 1})["code"] == "conflict"
    assert harness.error("project.skills.get", {"handle": handle, "project_skill_id": str(uuid4())})["code"] == "not_found"
