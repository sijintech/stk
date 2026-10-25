"""Local catalog publication, immutable identity and project independence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import sqlite3
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.skills import catalog, user_catalog
from suan.skills.catalog import SkillCatalogError
from suan.skills.user_catalog import UserSkillLibrary
from test_project_skills import user_analysis, publish, saved
from test_workflow_composition import child_document, document, parent_document, write
from test_workflow_runs import project  # noqa: F401


@pytest.fixture
def library(tmp_path):
    return UserSkillLibrary(root=tmp_path / "state" / "skills")


@pytest.fixture
def source(tmp_path):
    store = ProjectStore.create(tmp_path / "source", "Source")
    analysis_id, _ = user_analysis(store, outputs=[])
    identity = publish(store, analysis_id)
    return store, identity, analysis_id


def capture(source):
    store, identity, _ = source
    active = saved(store, identity)["active"]
    revision = store.info()["revision"]
    exported = store.skills.export_snapshot(identity, active["content_sha256"], expected_revision=revision)
    return exported["snapshot"], {"project_id": exported["project_id"], "project_skill_id": identity,
                                  "revision": revision, "content_sha256": active["content_sha256"]}, exported["max_version"]


def send(library, source, *, mode="exact", publication_id=None, minimum_version=None):
    snapshot, provenance, maximum = capture(source)
    return library.publish(snapshot, publication_id=publication_id or str(uuid4()), source=provenance,
                           mode=mode, minimum_version=minimum_version or maximum + 1)


def forbidden(*args, **kwargs):
    raise AssertionError("Read-only catalog must not load node plugins or snapshot payloads")


def test_empty_library_read_never_creates_state_and_builtin_read_does_not_load_plugins(library, monkeypatch):
    from suan.graph import catalog as graph_catalog
    monkeypatch.setattr(graph_catalog, "load_entry_points", forbidden)
    assert catalog.load_catalog(user_library=library).page()["total"] == 6
    with pytest.raises(SkillCatalogError) as error:
        library.publication(str(uuid4()))
    assert error.value.code == "not_found"
    assert not library.root.exists()


def test_publish_read_freeze_and_replay_do_not_modify_source(library, source, monkeypatch):
    store, identity, _ = source
    before, history = store.snapshot(), store.history()
    publication_id = str(uuid4())
    receipt = send(library, source, publication_id=publication_id)
    assert receipt["created"] and receipt["mode"] == "exact"
    assert send(library, source, publication_id=publication_id) == receipt
    assert not send(library, source)["created"]
    assert library.publication(publication_id) == receipt
    assert store.snapshot() == before and store.history() == history
    merged = catalog.load_catalog(user_library=UserSkillLibrary(root=library.root))
    detail = merged.get(receipt["skill"]["id"], 1)
    assert detail["entry"]["operation"] == "project.skills.create_analysis"
    assert detail["availability"]["status"] == "unchecked" and detail["outputs"] == []
    assert detail["inputs"][0]["name"] == "chosen"
    assert next(item for item in detail["parameters"] if item["name"] == "level")["default"] == 9007199254740993
    snapshot, _, _ = capture(source)
    assert merged.freeze(detail["id"], 1, detail["content_sha256"]) == {key: snapshot[key] for key in ("definition", "template")}
    monkeypatch.setattr(UserSkillLibrary, "_read_version", forbidden)
    assert catalog.load_catalog(user_library=library, directories=[]).page(query="reusable")["total"] == 1


def test_export_checks_active_and_revision_within_read_snapshot(source):
    store, identity, aid = source
    snapshot, _, _ = capture(source)
    publish(store, aid, identity=identity, create=False)
    before = store.snapshot()
    with pytest.raises(RevisionConflict):
        store.skills.export_snapshot(identity, snapshot["content_sha256"], expected_revision=2)
    with pytest.raises(RevisionConflict, match="active"):
        store.skills.export_snapshot(identity, snapshot["content_sha256"], expected_revision=3)
    assert store.snapshot() == before
    store.skills.restore(identity, snapshot["content_sha256"], expected_revision=3)
    exported = store.skills.export_snapshot(identity, snapshot["content_sha256"], expected_revision=4)
    assert exported["max_version"] == 2 and exported["snapshot"] == snapshot


def test_undo_republish_identity_conflict_and_explicit_new_version(library, source):
    store, identity, aid = source
    first = send(library, source)
    store.undo(expected_revision=2)
    publish(store, aid, identity=identity)
    before = store.snapshot()
    with pytest.raises(SkillCatalogError) as error:
        send(library, source)
    assert error.value.code == "conflict"
    newer = send(library, source, mode="new_version", minimum_version=7)
    assert newer["skill"]["version"] == 7
    assert send(library, source, mode="new_version")["skill"]["version"] == 8
    assert store.snapshot() == before
    assert library.snapshot(first["skill"]["id"], 1)["content_sha256"] == first["skill"]["content_sha256"]


@pytest.mark.parametrize("changed", ["source", "mode", "minimum_version", "content"])
def test_publication_id_binds_the_whole_request(library, source, changed):
    snapshot, provenance, maximum = capture(source)
    args = dict(publication_id=str(uuid4()), source=provenance, mode="exact", minimum_version=maximum + 1)
    receipt = library.publish(snapshot, **args)
    if changed == "source":
        args["source"] = {**provenance, "revision": provenance["revision"] + 1}
    elif changed == "mode":
        args["mode"] = "new_version"
    elif changed == "minimum_version":
        args["minimum_version"] += 1
    else:
        snapshot = deepcopy(snapshot)
        snapshot["definition"]["summary"]["en"] = "Changed"
        snapshot["content_sha256"] = hashlib.sha256(catalog._canonical({key: snapshot[key] for key in ("definition", "template")}).encode()).hexdigest()
        args["source"] = {**provenance, "content_sha256": snapshot["content_sha256"]}
    with pytest.raises(SkillCatalogError) as error:
        library.publish(snapshot, **args)
    assert error.value.code == "conflict" and library.publication(receipt["publication_id"]) == receipt


def test_concurrent_allocations_and_replays_are_atomic(library, source):
    snapshot, provenance, _ = capture(source)
    def publish_one(identity):
        return UserSkillLibrary(root=library.root).publish(snapshot, publication_id=identity, source=provenance,
                                                         mode="new_version", minimum_version=5)
    identities = [str(uuid4()) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(publish_one, identities * 2))
    assert {receipt["skill"]["version"] for receipt in receipts} == {5, 6, 7, 8}
    assert receipts[:4] == receipts[4:]
    assert len(library.summaries()[0]) == 4


def test_pin_into_other_project_append_preserves_identity_and_library_independence(library, source, tmp_path, monkeypatch):
    receipt = send(library, source)
    target = ProjectStore.create(tmp_path / "target", "Target")
    identity = str(uuid4())
    item = receipt["skill"]
    resolver = lambda: catalog.load_catalog(user_library=library)
    target.skills.pin(item["id"], item["version"], item["content_sha256"], project_skill_id=identity,
                      expected_revision=0, catalog=resolver)
    aid = str(uuid4())
    target.skills.create_analysis(identity, item["content_sha256"], analysis_id=aid, name="Copy", expected_revision=1)
    publish(target, aid, identity=identity, create=False)
    updated = saved(target, identity)
    assert updated["active"]["skill_id"] == item["id"] and updated["active"]["version"] == 2
    assert updated["document"]["versions"][0]["template"]["id"] == updated["document"]["versions"][1]["template"]["id"]
    newer = send(library, source, mode="new_version", minimum_version=3)["skill"]
    target.skills.upgrade(identity, newer["version"], newer["content_sha256"], expected_revision=3, catalog=resolver)
    monkeypatch.setattr(catalog, "load_catalog", forbidden)
    library.path.unlink()
    target.skills.restore(identity, item["content_sha256"], expected_revision=4)
    assert saved(ProjectStore(target.directory), identity)["active"]["version"] == 1
    target.undo(expected_revision=5)
    assert saved(target, identity)["active"]["version"] == 3


def test_workflow_directory_boundary_and_imported_append(library, tmp_path):
    store = ProjectStore.create(tmp_path / "workflow", "Workflow")
    wid = write(store, document([], parameters=[{"name": "n", "type": "integer", "default": 3}]))
    sid = str(uuid4())
    store.skills.publish_workflow(wid, project_skill_id=sid, create=True, name="Complete", description="Frozen",
                                 expected_revision=1)
    source = store, sid, wid
    item = send(library, source)["skill"]
    resolver = lambda: catalog.load_catalog(user_library=library)
    detail = resolver().get(item["id"], 1)
    assert detail["entry"]["operation"] == "project.skills.create_workflow"
    assert detail["parameters"] == [{"name": "n", "type": "integer", "default": 3}]
    assert detail["method"] == {"workflow_count": 1, "analysis_count": 0,
                                "data_dependencies": {"tables": 0, "fields": 0, "snapshots": 0}}
    imported = str(uuid4())
    store.skills.pin(item["id"], 1, item["content_sha256"], project_skill_id=imported, expected_revision=2, catalog=resolver)
    store.skills.publish_workflow(wid, project_skill_id=imported, create=False, name="Again", description="Imported",
                                 expected_revision=3)
    assert saved(store, imported)["active"]["skill_id"] == item["id"]


def test_corrupt_payload_does_not_force_list_to_read_it_but_get_and_freeze_reject(library, source):
    item = send(library, source)["skill"]
    with sqlite3.connect(library.path) as db:
        db.execute("UPDATE versions SET payload='{}'")
    merged = catalog.load_catalog(user_library=library)
    assert merged.page(query=item["id"])["total"] == 1
    for operation in (lambda: merged.get(item["id"], 1), lambda: merged.freeze(item["id"], 1, item["content_sha256"])):
        with pytest.raises(SkillCatalogError) as error:
            operation()
        assert error.value.code == "invalid_definition"


def test_corrupt_summary_isolated_and_size_limit_fails_atomically(library, source, monkeypatch):
    first = send(library, source)
    with sqlite3.connect(library.path) as db:
        db.execute("UPDATE versions SET summary='{}'")
    result = catalog.load_catalog(user_library=library).page()
    assert result["total"] == 6 and result["problem_count"] == 1
    monkeypatch.setattr(user_catalog, "MAX_COLLECTION_BYTES", 1)
    with pytest.raises(SkillCatalogError):
        send(library, source, mode="new_version")
    with sqlite3.connect(library.path) as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM publications").fetchone()[0] == 1
    assert library.publication(first["publication_id"]) == first


def test_receipt_survives_source_removal_and_maximum_bilingual_summary(library, source):
    snapshot, provenance, _ = capture(source)
    snapshot["definition"]["title"] = {"en": "T" * 120, "zh_CN": "题" * 120}
    snapshot["definition"]["summary"] = {"en": "S" * 1000, "zh_CN": "说" * 1000}
    snapshot["content_sha256"] = hashlib.sha256(catalog._canonical({key: snapshot[key] for key in ("definition", "template")}).encode()).hexdigest()
    provenance["content_sha256"] = snapshot["content_sha256"]
    receipt = library.publish(snapshot, publication_id=str(uuid4()), source=provenance, mode="exact", minimum_version=2)
    source[0].path.unlink()
    assert library.publication(receipt["publication_id"]) == receipt
    assert len(library.summaries()[0]) == 1


def test_version_exhaustion_allows_exact_but_never_reuses_global_version(library, source):
    snapshot, provenance, _ = capture(source)
    snapshot["definition"]["version"] = catalog.MAX_VERSION
    snapshot["content_sha256"] = hashlib.sha256(catalog._canonical({key: snapshot[key] for key in ("definition", "template")}).encode()).hexdigest()
    provenance["content_sha256"] = snapshot["content_sha256"]
    first = library.publish(snapshot, publication_id=str(uuid4()), source=provenance, mode="exact", minimum_version=1)
    for minimum in (1, catalog.MAX_VERSION + 1):
        with pytest.raises(SkillCatalogError) as error:
            library.publish(snapshot, publication_id=str(uuid4()), source=provenance,
                            mode="new_version", minimum_version=minimum)
        assert error.value.code == "conflict"
    assert library.publication(first["publication_id"]) == first
    assert len(library.summaries()[0]) == 1


def test_library_rejects_kind_changes_for_the_same_method(library, source):
    original = send(library, source)
    store = source[0]
    wid = write(store, document([]))
    sid = str(uuid4())
    store.skills.publish_workflow(wid, project_skill_id=sid, create=True, name="Other", description="Other kind",
                                 expected_revision=store.info()["revision"])
    snapshot, provenance, _ = capture((store, sid, wid))
    snapshot["definition"]["id"] = original["skill"]["id"]
    snapshot["template"]["id"] = original["skill"]["id"].removeprefix("user.s")
    snapshot["content_sha256"] = hashlib.sha256(catalog._canonical({key: snapshot[key] for key in ("definition", "template")}).encode()).hexdigest()
    provenance["content_sha256"] = snapshot["content_sha256"]
    with pytest.raises(SkillCatalogError, match="entry kind"):
        library.publish(snapshot, publication_id=str(uuid4()), source=provenance, mode="new_version", minimum_version=2)
    assert len(library.summaries()[0]) == 1


def test_receipt_budget_rolls_back_a_new_version(library, source, monkeypatch):
    first = send(library, source)
    monkeypatch.setattr(user_catalog, "MAX_PUBLICATIONS", 1)
    assert library.publication(first["publication_id"]) == first
    with pytest.raises(SkillCatalogError, match="receipts"):
        send(library, source, mode="new_version")
    assert len(library.summaries()[0]) == 1


def test_same_ref_different_static_content_is_unavailable_even_with_a_third_copy(tmp_path):
    from test_skill_catalog import builtin_definition, write as write_definition
    definition = builtin_definition("stk.muferro.energy_trace")
    roots = []
    for index in range(3):
        value = deepcopy(definition)
        if index == 1:
            value["summary"]["en"] = "Different method"
        root = tmp_path / str(index)
        write_definition(root, definition["id"] + ".json", value)
        roots.append((str(index), root))
    merged = catalog.load_catalog(directories=roots)
    assert merged.skills == [] and merged.problems[0]["code"] == "conflicting_skill"
    with pytest.raises(SkillCatalogError):
        merged.get(definition["id"], 1)


def test_nested_method_crosses_real_library_and_instantiates_after_source_removal(library, project, tmp_path):
    store, ids = project
    child = write(store, child_document())
    root = write(store, parent_document(ids, child))
    sid = str(uuid4())
    store.skills.publish_workflow(root, project_skill_id=sid, create=True, name="Nested method", description="Complete",
                                 expected_revision=store.info()["revision"])
    item = send(library, (store, sid, root))["skill"]
    frozen = library.snapshot(item["id"], 1)
    assert len(frozen["template"]["workflows"]) == 2 and len(frozen["template"]["analyses"]) == 1
    target = ProjectStore.create(tmp_path / "nested_target", "Target")
    mapping = {key: {identity: str(uuid4()) for identity in values}
               for key, values in frozen["template"]["dependencies"].items()}
    commands = [{"op": "create_table", "id": mapped, "name": "Target cases"}
                for mapped in mapping["tables"].values()]
    commands += [{"op": "add_field", "table_id": mapping["tables"][field["table_id"]], "id": mapping["fields"][identity],
                  "name": field["name"], "type": field["type"], "unit": field["unit"]}
                 for identity, field in frozen["template"]["dependencies"]["fields"].items()]
    target.apply(commands, expected_revision=0)
    imported = str(uuid4())
    target.skills.pin(item["id"], 1, item["content_sha256"], project_skill_id=imported, expected_revision=1,
                      catalog=lambda: catalog.load_catalog(user_library=library))
    store.path.unlink()
    library.path.unlink()
    before = target.snapshot()
    wid = str(uuid4())
    with pytest.raises(ProjectError):
        target.skills.create_workflow(imported, item["content_sha256"], workflow_id=wid, name="Copied", bindings={}, expected_revision=2)
    assert target.snapshot() == before
    target.skills.create_workflow(imported, item["content_sha256"], workflow_id=wid, name="Copied", bindings=mapping, expected_revision=2)
    assert target.workflows.list()["total"] == 2 and target.analyses.list()["total"] == 1
    target.undo(expected_revision=3)
    assert target.snapshot()["tables"] == before["tables"]


@pytest.mark.parametrize("version", [True, 1.0, "1", 0, catalog.MAX_VERSION + 1])
def test_lazy_freeze_keeps_strict_version_validation(library, source, version):
    item = send(library, source)["skill"]
    merged = catalog.load_catalog(user_library=library)
    with pytest.raises(SkillCatalogError) as error:
        merged.freeze(item["id"], version, item["content_sha256"])
    assert error.value.code == "invalid_params"
