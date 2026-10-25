"""Reports freeze explicit bytes/provenance and reopen without executing their sources."""
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
import zipfile

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import reports
from suan.project.reports import Reports, ReportNotFound, TABLE_ID, FIELD_IDS, DOCUMENT_FORMAT


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5WQAAAAASUVORK5CYII=")


@pytest.fixture
def project(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Reports")
    contents = {"index.html": b'<!doctype html><h1>Frozen report</h1><img src="plot%20%23100%25.png">',
                "plot #100%.png": PNG, "notes.md": "# 冻结报告\n\nSelected values only.\n".encode(),
                "paper.pdf": b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"}
    paths = []
    for path, data in contents.items():
        target = store.directory / path
        target.write_bytes(data)
        paths.append(str(target))
    ids = store.files.index(paths, expected_revision=0)["record_ids"]
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    assets = [{"record_id": identity, "path": path} for identity, path in zip(ids, contents)]
    return store, snapshot, assets, contents


def create(project, *, identity=None, assets=None, sources=None, revision=None):
    store, snapshot, selected, _ = project
    return Reports(store).create("报告", snapshot["id"], selected[0]["record_id"],
        selected if assets is None else assets, report_id=identity or str(uuid4()),
        expected_revision=store.info()["revision"] if revision is None else revision, sources=sources)


def saved(project):
    identity = create(project)["record_id"]
    value = Reports(project[0]).get(identity)
    return identity, value["revision"], value["report"]


def literal(store, identity, key, value):
    return store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                        "field_id": FIELD_IDS[key], "value": value}], expected_revision=store.info()["revision"])


def test_empty_read_create_single_undo_reopen_and_redo(project):
    store, snapshot, assets, _ = project
    before = store.history()
    assert Reports(store).list() == {"revision": 2, "table_id": TABLE_ID, "offset": 0, "total": 0, "reports": []}
    with pytest.raises(ReportNotFound):
        Reports(store).get(str(uuid4()))
    assert store.history() == before
    result = create(project)
    identity = result["record_id"]
    assert result["revision"] == 3 and result["table_id"] == TABLE_ID
    assert len(store.history()) == len(before) + 1
    value = Reports(store).get(identity)
    assert set(value) == {"revision", "table_id", "report"}
    report = value["report"]
    assert report["state"] == "readable" and report["name"] == "报告" and report["format"] == DOCUMENT_FORMAT
    assert report["manifest"]["snapshot_id"] == snapshot["id"] and report["manifest"]["source_revision"] == 2
    assert report["manifest"]["entry_path"] == assets[0]["path"]
    assert report["source_sha256"] == hashlib.sha256(reports._json(report["manifest"])).hexdigest()
    assert Reports(ProjectStore(store.directory)).get(identity) == value
    store.undo(expected_revision=3)
    assert Reports(store).list()["total"] == 0
    assert store.snapshots.verify(snapshot["id"])["files"]
    store.redo(expected_revision=4)
    assert Reports(store).get(identity)["report"] == report


def test_all_assets_are_exact_untruncated_bytes_and_live_changes_are_ignored(project):
    store, _, assets, contents = project
    identity, revision, report = saved(project)
    before = store.history()
    for path in contents:
        (store.directory / path).write_bytes(b"current content is different")
    for asset in assets:
        result = Reports(store).asset(identity, asset["path"], expected_revision=revision,
                                      expected_source_sha256=report["source_sha256"])
        data = contents[asset["path"]]
        assert base64.b64decode(result["data"]) == data
        assert result["size"] == len(data) and result["content_sha256"] == hashlib.sha256(data).hexdigest()
        assert result["project_id"] == store.info()["id"] and result["report_id"] == identity
        assert result["source_sha256"] == report["source_sha256"]
    assert store.history() == before


def test_large_markdown_is_not_attachment_preview_truncated(tmp_path):
    store = ProjectStore.create(tmp_path / "p", "Long text")
    text = b"# Heading\n" + b"x" * 100000
    path = store.directory / "report.md"
    path.write_bytes(text)
    record = store.files.index([str(path)], expected_revision=0)["record_ids"][0]
    snapshot = store.snapshots.capture([record], expected_revision=1)["snapshot"]
    result = Reports(store).create("Full", snapshot["id"], record, [{"record_id": record, "path": "report.md"}],
                                   report_id=str(uuid4()), expected_revision=2)
    report = Reports(store).get(result["record_id"])["report"]
    read = Reports(store).asset(result["record_id"], "report.md", expected_revision=3,
                               expected_source_sha256=report["source_sha256"])
    assert base64.b64decode(read["data"]) == text and read["mime"] == "text/markdown; charset=utf-8"


def test_metadata_is_content_free_and_damaged_cas_fails_explicit_read(project, monkeypatch):
    store, _, _, _ = project
    identity, revision, report = saved(project)
    first = report["manifest"]["assets"][0]
    object_path = store.snapshots._object(first["sha256"])
    object_path.write_bytes(b"x" * first["size"])
    with monkeypatch.context() as patch:
        patch.setattr(reports, "_read_asset", lambda *a: pytest.fail("metadata opened an asset"))
        patch.setattr(store, "snapshot", lambda: pytest.fail("metadata read the whole project"))
        assert Reports(store).get(identity)["report"] == report
        assert Reports(store).list()["reports"][0]["state"] == "readable"
    with pytest.raises(ProjectError, match="checksum"):
        Reports(store).asset(identity, first["path"], expected_revision=revision, expected_source_sha256=report["source_sha256"])


@pytest.mark.parametrize("path", ["../x.html", "/x.html", "a//x.html", "a/./x.html", "a\\x.html", "a:x.html",
    "a?x.html", "a*x.html", "a|x.html", "a<x.html", "NUL.html", "COM¹.html", "a. /x.html",
    "a./x.html", "a\x00.html", "a\u0085.html", "STK-REPORT.JSON", "stk-report.json/x.html", "\ud800.html"])
def test_nonportable_or_reserved_paths_never_save(project, path):
    store, _, assets, _ = project
    selected = deepcopy(assets)
    selected[0]["path"] = path
    before = store.history()
    with pytest.raises(ProjectError):
        create(project, assets=selected)
    assert store.history() == before and Reports(store).list()["total"] == 0


@pytest.mark.parametrize("paths", [["a.html", "A.html"], ["é.html", "e\u0301.html"],
                                    ["a.html", "a.html/x.html"], ["Dir/a.html", "dir/b.html"]])
def test_colliding_portable_files_or_directories_are_rejected(project, paths):
    store, snapshot, assets, _ = project
    # Select a second, real HTML record from the same new snapshot.
    other = store.directory / "other.html"
    other.write_bytes(b"<p>other</p>")
    identity = store.files.index([str(other)], expected_revision=2)["record_ids"][0]
    snapshot = store.snapshots.capture([assets[0]["record_id"], identity], expected_revision=3)["snapshot"]
    selected = [{"record_id": record, "path": path} for record, path in zip([assets[0]["record_id"], identity], paths)]
    with pytest.raises(ProjectError, match="collide"):
        Reports(store).create("Bad", snapshot["id"], assets[0]["record_id"], selected,
                              report_id=str(uuid4()), expected_revision=4)
    assert Reports(store).list()["total"] == 0


@pytest.mark.parametrize("change", ["empty", "duplicate", "foreign", "extra", "rename_type", "too_many"])
def test_invalid_asset_selection_is_atomic(project, change):
    store, _, assets, _ = project
    selected = deepcopy(assets)
    if change == "empty":
        selected = []
    elif change == "duplicate":
        selected.append(selected[0])
    elif change == "foreign":
        selected[0]["record_id"] = str(uuid4())
    elif change == "extra":
        selected[0]["arbitrary_path"] = "unselected.html"
    elif change == "rename_type":
        selected[0]["path"] = "hidden.png"
    else:
        selected *= 17
    with pytest.raises(ProjectError):
        create(project, assets=selected)
    assert store.info()["revision"] == 2 and Reports(store).list()["total"] == 0


def test_revision_manifest_project_and_uuid_gates(project, tmp_path):
    store = project[0]
    identity, revision, report = saved(project)
    with pytest.raises(RevisionConflict):
        create(project, identity=identity)
    for bad_revision, bad_hash in [(revision - 1, report["source_sha256"]), (revision, "0" * 64)]:
        with pytest.raises(RevisionConflict):
            Reports(store).asset(identity, "index.html", expected_revision=bad_revision, expected_source_sha256=bad_hash)
        with pytest.raises(RevisionConflict):
            Reports(store).export_file(identity, tmp_path / "absent.zip", expected_revision=bad_revision,
                                       expected_source_sha256=bad_hash)
        assert not (tmp_path / "absent.zip").exists()
    with pytest.raises(ReportNotFound):
        Reports(store).asset(identity, "unlisted.html", expected_revision=revision, expected_source_sha256=report["source_sha256"])
    other = ProjectStore.create(tmp_path / "other", "Other")
    with pytest.raises(ProjectError):
        Reports(other).create("Wrong", project[1]["id"], project[2][0]["record_id"], project[2],
                              report_id=str(uuid4()), expected_revision=0)


def test_cas_rechecks_after_asset_io_without_partial_record(project, monkeypatch):
    store = project[0]
    read = reports._read_asset
    changed = False
    def concurrent_edit(*args):
        nonlocal changed
        data = read(*args)
        if not changed:
            changed = True
            store.apply([{"op": "create_table", "id": str(uuid4()), "name": "Concurrent"}], expected_revision=2)
        return data
    monkeypatch.setattr(reports, "_read_asset", concurrent_edit)
    with pytest.raises(RevisionConflict):
        create(project, revision=2)
    assert store.info()["revision"] == 3 and Reports(store).list()["total"] == 0


@pytest.mark.parametrize("change", ["revision", "manifest"])
def test_asset_rechecks_revision_and_manifest_after_actual_read(project, monkeypatch, change):
    store = project[0]
    identity, revision, report = saved(project)
    read = reports._read_asset
    def changed(*args):
        data = read(*args)
        if change == "revision":
            literal(store, identity, "name", "Changed")
        else:
            manifest = deepcopy(report["manifest"])
            manifest["entry_path"] = "notes.md"
            with sqlite3.connect(store.path) as db:
                db.execute("UPDATE cells SET value=? WHERE record_id=? AND field_id=?",
                           (json.dumps(manifest), identity, FIELD_IDS["manifest"]))
        return data
    monkeypatch.setattr(reports, "_read_asset", changed)
    with pytest.raises(RevisionConflict):
        Reports(store).asset(identity, "index.html", expected_revision=revision,
                             expected_source_sha256=report["source_sha256"])


def test_same_descriptor_change_during_read_is_rejected(project, monkeypatch):
    store = project[0]
    identity, revision, report = saved(project)
    item = report["manifest"]["assets"][0]
    path = store.snapshots._object(item["sha256"])
    original = os.fdopen
    @contextmanager
    def mutate_while_reading(*args, **kwargs):
        with original(*args, **kwargs) as stream:
            class Reader:
                def fileno(self):
                    return stream.fileno()
                def read(self, size):
                    data = stream.read(size)
                    path.write_bytes(b"x" * item["size"])
                    return data
            yield Reader()
    monkeypatch.setattr(reports.os, "fdopen", mutate_while_reading)
    with pytest.raises(ProjectError, match="changed"):
        Reports(store).asset(identity, "index.html", expected_revision=revision,
                             expected_source_sha256=report["source_sha256"])


@pytest.mark.parametrize("key,value", [("name", ""), ("format", "stk.report/99"), ("manifest", []),
                                         ("manifest", {"format": DOCUMENT_FORMAT})])
def test_generic_damage_is_local_invalid_metadata(project, key, value):
    store = project[0]
    bad = create(project)["record_id"]
    good = create(project)["record_id"]
    literal(store, bad, key, value)
    assert Reports(store).get(bad)["report"]["state"] == "invalid"
    assert Reports(store).get(good)["report"]["state"] == "readable"
    assert [entry["state"] for entry in Reports(store).list()["reports"]] == ["invalid", "readable"]
    assert Reports(store).list(limit=1)["reports"][0]["id"] == bad
    assert Reports(store).list(offset=1, limit=1)["reports"][0]["id"] == good


def test_manifest_identity_and_snapshot_binding_corruption_is_rejected(project):
    store = project[0]
    identity, _, report = saved(project)
    for mutation in (lambda m: m.update(project_id=str(uuid4())),
                     lambda m: m.update(snapshot_sha256="1" * 64),
                     lambda m: m["assets"][0].update(sha256="2" * 64),
                     lambda m: m["assets"][0].update(size=True),
                     lambda m: m.update(source_revision=100000),
                     lambda m: m.update(entry_path="missing.html")):
        value = deepcopy(report["manifest"])
        mutation(value)
        literal(store, identity, "manifest", value)
        assert Reports(store).get(identity)["report"]["state"] == "invalid"


def test_ambiguous_raw_json_formula_and_damaged_schema_are_invalid(project):
    store = project[0]
    identity, _, _ = saved(project)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE cells SET value=? WHERE record_id=? AND field_id=?",
                   ('{"format":"stk.report/1","format":"stk.report/1"}', identity, FIELD_IDS["manifest"]))
    assert Reports(store).get(identity)["report"]["state"] == "invalid"
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE fields SET type='number' WHERE id=?", (FIELD_IDS["manifest"],))
    assert Reports(store).get(identity)["report"]["state"] == "invalid"


def test_asset_and_metadata_budgets_roll_back(project, monkeypatch):
    store = project[0]
    with monkeypatch.context() as patch:
        patch.setattr(reports, "MAX_ASSET_BYTES", 8)
        with pytest.raises(ProjectError, match="4 MiB"):
            create(project)
    with monkeypatch.context() as patch:
        patch.setattr(reports, "MAX_TOTAL_BYTES", 10)
        with pytest.raises(ProjectError, match="32 MiB"):
            create(project)
    with monkeypatch.context() as patch:
        patch.setattr(reports, "MAX_MANIFEST_BYTES", 128)
        with pytest.raises(ProjectError, match="byte"):
            create(project)
    with monkeypatch.context() as patch:
        patch.setattr(reports, "MAX_COLLECTION_BYTES", 128)
        with pytest.raises(ProjectError, match="collection"):
            create(project)
    assert store.info()["revision"] == 2 and Reports(store).list()["total"] == 0
    create(project)
    with monkeypatch.context() as patch:
        patch.setattr(reports, "MAX_REPORTS", 1)
        with pytest.raises(ProjectError, match="collection"):
            create(project)
    assert Reports(store).list()["total"] == 1


def test_create_verifies_bytes_before_publishing(project):
    store, snapshot, _, _ = project
    path = store.snapshots._object(snapshot["manifest"]["files"][0]["sha256"])
    path.write_bytes(b"damaged")
    with pytest.raises(ProjectError):
        create(project)
    assert store.info()["revision"] == 2 and Reports(store).list()["total"] == 0


def test_symlinked_asset_is_denied(project, tmp_path):
    store, snapshot, _, contents = project
    original = snapshot["manifest"]["files"][0]
    path = store.snapshots._object(original["sha256"])
    target = tmp_path / "target.html"
    target.write_bytes(contents["index.html"])
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ProjectError):
        create(project)
    assert Reports(store).list()["total"] == 0


def test_export_is_portable_complete_and_does_not_mutate_or_overwrite(project, tmp_path):
    store, _, _, contents = project
    identity, revision, report = saved(project)
    before = store.history()
    destination = tmp_path / "report.zip"
    result = Reports(store).export_file(identity, destination, expected_revision=revision,
                                       expected_source_sha256=report["source_sha256"])
    output = destination.read_bytes()
    assert result["size"] == len(output) and result["sha256"] == hashlib.sha256(output).hexdigest()
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {*contents, "stk-report.json"}
        envelope = json.loads(archive.read("stk-report.json"))
        assert envelope["manifest"] == report["manifest"] and envelope["report_id"] == identity
        assert envelope["source_sha256"] == report["source_sha256"]
        for path, data in contents.items():
            assert archive.read(path) == data
    with pytest.raises(ProjectError, match="already exists"):
        Reports(store).export_file(identity, destination, expected_revision=revision, expected_source_sha256=report["source_sha256"])
    assert destination.read_bytes() == output and store.history() == before
    assert not list(tmp_path.glob(".stk-report-*.part"))


def test_export_rejects_incomplete_bytes_and_changed_report_without_partial_file(project, tmp_path, monkeypatch):
    store = project[0]
    identity, revision, report = saved(project)
    destination = tmp_path / "missing.zip"
    original = reports._read_asset
    changed = False
    def edit_after_read(*args):
        nonlocal changed
        data = original(*args)
        if not changed:
            changed = True
            literal(store, identity, "name", "Changed")
        return data
    with monkeypatch.context() as patch:
        patch.setattr(reports, "_read_asset", edit_after_read)
        with pytest.raises(RevisionConflict):
            Reports(store).export_file(identity, destination, expected_revision=revision,
                                       expected_source_sha256=report["source_sha256"])
    assert not destination.exists() and not list(tmp_path.glob(".stk-report-*.part"))
    item = report["manifest"]["assets"][-1]
    store.snapshots._object(item["sha256"]).unlink()
    with pytest.raises(ProjectError):
        Reports(store).export_file(identity, destination, expected_revision=revision + 1,
                                   expected_source_sha256=report["source_sha256"])
    assert not destination.exists() and not list(tmp_path.glob(".stk-report-*.part"))


@pytest.mark.skipif(os.link not in os.supports_dir_fd, reason="requires POSIX directory descriptors")
def test_export_parent_renamed_at_publication_rolls_back_via_pinned_directory(project, tmp_path, monkeypatch):
    identity, revision, report = saved(project)
    parent, moved = tmp_path / "output", tmp_path / "renamed"
    parent.mkdir()
    destination = parent / "report.zip"
    link = os.link
    def rename_after_link(source, target, **kwargs):
        link(source, target, **kwargs)
        parent.rename(moved)
    monkeypatch.setattr(reports.os, "link", rename_after_link)
    with pytest.raises(ProjectError):
        Reports(project[0]).export_file(identity, destination, expected_revision=revision,
                                        expected_source_sha256=report["source_sha256"])
    assert not destination.exists() and list(moved.iterdir()) == []


def test_full_asset_and_total_byte_boundaries(tmp_path):
    store = ProjectStore.create(tmp_path / "p", "Byte limits")
    content = b"x" * reports.MAX_ASSET_BYTES
    paths = []
    for number in range(9):
        path = store.directory / f"{number}.txt"
        path.write_bytes(content)
        paths.append(str(path))
    oversized = store.directory / "too-big.txt"
    oversized.write_bytes(content + b"x")
    paths.append(str(oversized))
    ids = store.files.index(paths, expected_revision=0)["record_ids"]
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    selected = [{"record_id": identity, "path": Path(path).name} for identity, path in zip(ids, paths)]
    result = Reports(store).create("Exact total", snapshot["id"], ids[0], selected[:8],
                                   report_id=str(uuid4()), expected_revision=2)
    assert sum(a["size"] for a in Reports(store).get(result["record_id"])["report"]["manifest"]["assets"]) == reports.MAX_TOTAL_BYTES
    with pytest.raises(ProjectError, match="32 MiB"):
        Reports(store).create("Total overflow", snapshot["id"], ids[0], selected[:9], report_id=str(uuid4()), expected_revision=3)
    with pytest.raises(ProjectError, match="4 MiB"):
        Reports(store).create("Asset overflow", snapshot["id"], ids[-1], selected[-1:], report_id=str(uuid4()), expected_revision=3)
    assert Reports(store).list()["total"] == 1


def _parameter_table(store):
    table, field, row = (str(uuid4()) for _ in range(3))
    store.apply([{"op": "create_table", "id": table, "name": "Cases"},
                 {"op": "add_field", "id": field, "table_id": table, "name": "T", "type": "number", "unit": "K"},
                 {"op": "add_record", "id": row, "table_id": table},
                 {"op": "set_cell", "table_id": table, "record_id": row, "field_id": field, "value": 300}],
                expected_revision=store.info()["revision"])
    return table, field, row


def test_all_four_provenance_types_freeze_without_running_or_reading_entire_project(project, monkeypatch):
    from suan.desktop_bridge.schema import validate_outgoing
    store, snapshot, assets, _ = project
    table, field, row = _parameter_table(store)
    context_id = str(uuid4())
    context = store.contexts.capture(table, [row], [field], expected_revision=3, title="Frozen values", context_id=context_id)
    simulation = store.runs.prepare([{"table_id": table, "record_id": row,
        "spec": {"workspace_id": "a" * 32, "argv": ["{python}", "-c", "pass"]}}],
        connection="runtime:Test", connection_identity="a" * 16, expected_revision=3)["run_ids"][0]
    analysis_id, analysis_run_id, workflow_id, workflow_run_id = (str(uuid4()) for _ in range(4))
    store.analyses.create("Unknown source", {"format": "stk.analysis-document/1", "graph": {
        "schema": "stk.graph/1", "nodes": [{"id": "source", "type": "missing.source.node@1", "params": {"binding": "data"}}],
        "outputs": {"view": "source.payload"}}, "parameters": {}, "outputs": ["view"]},
        analysis_id=analysis_id, expected_revision=4)
    run = store.analysis_runs.prepare(analysis_id, snapshot["id"], {"data": {"index.html": assets[0]["record_id"]}},
                                      run_id=analysis_run_id, expected_revision=5)
    store.workflows.create("Synthetic", {"format": "stk.workflow/1", "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": table}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": field}}}], "ui": {}},
        workflow_id=workflow_id, expected_revision=5)
    workflow = store.workflow_runs.prepare(workflow_id, [row], run_id=workflow_run_id, expected_revision=6)
    selection = [{"kind": kind, "id": identity} for kind, identity in
                 [("context", context_id), ("simulation_run", simulation), ("analysis_run", analysis_run_id), ("workflow_run", workflow_run_id)]]
    monkeypatch.setattr(store, "snapshot", lambda: pytest.fail("whole-project read while freezing report provenance"))
    report_id = create(project, sources=selection)["record_id"]
    frozen = Reports(store).get(report_id)["report"]["manifest"]["sources"]
    assert frozen[0]["context"] == context and frozen[0]["context_sha256"] == reports._hash(context)
    assert frozen[1]["captured_status"]["status"] == {"submission": "prepared"}
    assert frozen[2]["plan_sha256"] == run["plan_sha256"] and frozen[2]["captured_status"]["status"] == "prepared"
    assert frozen[3]["plan_sha256"] == workflow["plan_sha256"] and frozen[3]["captured_status"] == {
        "status": "prepared", "complete": False, "counts": {"pending": 1}, "stop_error": None}
    assert validate_outgoing({"id": 1, "result": Reports(store).get(report_id)}, "project.reports.get") == []
    owner = str(uuid4())
    store.analysis_runs._claim(analysis_run_id, executor_id=owner)
    assert Reports(store).get(report_id)["report"]["manifest"]["sources"] == frozen
    assert store.info()["revision"] == 7


def test_context_omission_and_missing_selection_remain_visible(project):
    from suan.project import contexts
    store = project[0]
    table, _, row = _parameter_table(store)
    field = str(uuid4())
    store.apply([{"op": "add_field", "id": field, "table_id": table, "name": "Long text", "type": "text"},
                 {"op": "set_cell", "table_id": table, "record_id": row, "field_id": field,
                  "value": "x" * (contexts.MAX_VALUE_BYTES + 1)}], expected_revision=3)
    context = store.contexts.capture(table, [row, str(uuid4())], [field], expected_revision=4,
                                     title="Omitted values", context_id=str(uuid4()))
    report_id = create(project, sources=[{"kind": "context", "id": context["id"]}])["record_id"]
    frozen = Reports(store).get(report_id)["report"]["manifest"]["sources"][0]["context"]
    assert frozen == context and frozen["omitted_values"] == 1 and len(frozen["diagnostics"]["record_ids"]) == 1
    assert frozen["content"]["value"]["records"][0]["literals"][field]["state"] == "omitted"


@pytest.mark.parametrize("path,value", [
    (("diagnostics",), []),
    (("diagnostics", "table_missing"), "false"),
    (("diagnostics", "record_ids"), ["not-a-uuid"]),
    (("diagnostics", "extra"), True),
    (("limits", "max_value_bytes"), 1),
    (("limits",), {}),
    (("omitted_values",), -1),
    (("omitted_values",), True),
    (("title",), []),
    (("title",), ""),
    (("created_at",), []),
    (("created_at",), ""),
    (("content", "extra"), True),
    (("content", "value", "table", "name"), 42),
    (("content", "value", "fields", 0, "type"), "unsupported"),
    (("content", "value", "records", 0, "literals", "$field"), {"state": "included"}),
    (("content", "value", "records", 0, "literals", "$field"),
     {"state": "omitted", "reason": "unknown", "size_bytes": 0, "sha256": "0" * 64}),
    (("content", "value"), []),
])
def test_frozen_context_corruption_is_locally_invalid_even_with_recomputed_hashes(project, monkeypatch, path, value):
    from suan.desktop_bridge.schema import validate_outgoing
    store = project[0]
    table, field, row = _parameter_table(store)
    context = store.contexts.capture(table, [row], [field], expected_revision=3,
                                     title="Frozen", context_id=str(uuid4()))
    identity = create(project, sources=[{"kind": "context", "id": context["id"]}])["record_id"]
    healthy = create(project)["record_id"]
    manifest = Reports(store).get(identity)["report"]["manifest"]
    source = manifest["sources"][0]
    target = source["context"]
    for part in path[:-1]:
        target = target[field if part == "$field" else part]
    target[field if path[-1] == "$field" else path[-1]] = value
    content = source["context"]["content"]
    content.update(sha256=reports._hash(content["value"]), size_bytes=len(reports._json(content["value"])))
    source["context_sha256"] = reports._hash(source["context"])
    literal(store, identity, "manifest", manifest)

    monkeypatch.setattr(store, "snapshot", lambda: pytest.fail("whole-project read while checking context metadata"))
    monkeypatch.setattr(reports, "_read_asset", lambda *args: pytest.fail("context metadata opened an asset"))
    value = Reports(store).get(identity)
    assert value["report"]["state"] == "invalid"
    assert value["report"]["manifest"] is None and value["report"]["source_sha256"] is None
    assert validate_outgoing({"id": 1, "result": value}, "project.reports.get") == []
    listed = Reports(store).list()
    assert {item["id"]: item["state"] for item in listed["reports"]} == {identity: "invalid", healthy: "readable"}
    assert validate_outgoing({"id": 2, "result": listed}, "project.reports.list") == []


def test_invalid_context_capture_is_rejected_before_asset_reads_or_report_write(project, monkeypatch):
    from suan.project.contexts import Contexts
    store = project[0]
    table, field, row = _parameter_table(store)
    context = store.contexts.capture(table, [row], [field], expected_revision=3,
                                     title="Frozen", context_id=str(uuid4()))
    context["diagnostics"] = []
    monkeypatch.setattr(Contexts, "_get", lambda *args: deepcopy(context))
    monkeypatch.setattr(reports, "_read_asset", lambda *args: pytest.fail("invalid context opened an asset"))
    history = store.history()
    with pytest.raises(ProjectError, match="context descriptor"):
        create(project, sources=[{"kind": "context", "id": context["id"]}])
    assert store.history() == history and store.info()["revision"] == 3
    assert Reports(store).list()["total"] == 0


@pytest.mark.parametrize("sources", [[{"kind": "analysis", "id": str(uuid4())}],
    [{"kind": "context", "id": str(uuid4())}], [{"kind": "context", "id": str(uuid4()), "project_id": str(uuid4())}],
    [{"kind": "context", "id": str(uuid4())}] * 17, "context"])
def test_unavailable_or_invalid_provenance_never_saves(project, sources):
    with pytest.raises(ProjectError):
        create(project, sources=sources)
    assert project[0].info()["revision"] == 2 and Reports(project[0]).list()["total"] == 0


@pytest.mark.parametrize("offset,limit", [(True, 1), (-1, 50), (0, True), (0, 0), (0, 101)])
def test_strict_pagination(project, offset, limit):
    with pytest.raises(ProjectError):
        Reports(project[0]).list(offset=offset, limit=limit)
