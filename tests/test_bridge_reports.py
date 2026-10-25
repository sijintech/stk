"""Frozen reports cross the real, schema-checked bridge without rerunning their sources."""
import base64
import hashlib
import json
import posixpath
from uuid import UUID, uuid4
import zipfile

import pytest

from suan.desktop_bridge.schema import validate_params
from suan.project import ProjectStore
from suan.project import reports as report_storage
from suan.project.reports import EXPORT_MANIFEST, TABLE_ID
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5WQAAAAASUVORK5CYII=")
METHODS = {"project.reports." + action for action in
           ("create", "get", "list", "asset", "preview", "export_file")}


@pytest.mark.parametrize("damage", ["diagnostics", "limits", "content"])
def test_invalid_context_provenance_is_isolated_before_strict_bridge_serialization(inproc, tmp_path, monkeypatch, damage):
    harness = inproc()
    project, store, snapshot, assets, _ = prepared(harness, tmp_path)
    context = store.contexts.capture(str(uuid4()), [str(uuid4())], [str(uuid4())], expected_revision=2,
                                     title="Missing selection", context_id=str(uuid4()))
    identity, healthy = str(uuid4()), str(uuid4())
    project.reports.create("Context", snapshot["id"], assets[0]["record_id"], assets,
                           report_id=identity, expected_revision=2, sources=[{"kind": "context", "id": context["id"]}])
    saved = project.reports.get(identity)["report"]
    assert saved["state"] == "readable" and saved["manifest"]["sources"][0]["context"] == context
    project.reports.create("Healthy", snapshot["id"], assets[0]["record_id"], assets,
                           report_id=healthy, expected_revision=3)
    manifest = saved["manifest"]
    source = manifest["sources"][0]
    if damage == "content":
        source["context"]["content"]["value"] = []
        source["context"]["content"].update(sha256=report_storage._hash([]), size_bytes=2)
    else:
        source["context"][damage] = []
    source["context_sha256"] = report_storage._hash(source["context"])
    store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                  "field_id": report_storage.FIELD_IDS["manifest"], "value": manifest}], expected_revision=4)
    before = harness.events_of("project.changed")
    monkeypatch.setattr(report_storage, "_read_asset", lambda *args: pytest.fail("metadata opened a report asset"))
    invalid = project.reports.get(identity)["report"]
    assert invalid["state"] == "invalid" and invalid["error"]
    assert invalid["manifest"] is None and invalid["source_sha256"] is None
    listed = project.reports.list()
    assert listed["revision"] == 5
    assert {item["id"]: item["state"] for item in listed["reports"]} == {identity: "invalid", healthy: "readable"}
    assert project.reports.get(healthy)["report"]["state"] == "readable"
    assert harness.events_of("project.changed") == before
    harness.assert_clean()


def prepared(harness, tmp_path, *, entry_name="report.md"):
    """Use real bridge file/snapshot selection, leaving only explicit report creation undone."""
    directory = tmp_path / "project"
    info = harness.call("project.create", {"directory": str(directory), "name": "Reports"})["project"]
    project = Project(harness.call, info["handle"])
    source = {
        "report.md": "# 冻结报告\n\n| 温度 | 结果 |\n| --- | --- |\n| 300 | 通过 |\n\n"
                     "![结果](../images/plot%20%23100%25.png)\n\n<script>drop-script</script>\n",
        "report.html": '<h1>冻结报告</h1><img src="../images/plot%20%23100%25.png">'
                       '<script>drop-script</script>',
        "paper.pdf": "%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n",
    }[entry_name].encode("utf-8")
    originals = {entry_name: source, "plot #100%.png": PNG}
    for name, data in originals.items():
        (directory / name).write_bytes(data)
    records = project.files.index(list(originals), expected_revision=0)["record_ids"]
    snapshot = project.snapshots.capture(records, expected_revision=1)["snapshot"]
    assets = [{"record_id": records[0], "path": "reports/" + entry_name},
              {"record_id": records[1], "path": "images/plot #100%.png"}]
    harness.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 2)
    return project, ProjectStore(directory), snapshot, assets, originals


def create_report(harness, prepared_project, *, report_id=None):
    project, _, snapshot, assets, _ = prepared_project
    identity = report_id or str(uuid4())
    result = project.reports.create("冻结报告", snapshot["id"], assets[0]["record_id"], assets,
                                    report_id=identity, expected_revision=2, sources=[])
    harness.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 3)
    return identity, result, project.reports.get(identity)["report"]


def assert_no_runs(store):
    assert store.requests.list()["requests"] == []
    assert store.runs.list()["runs"] == []
    assert store.analysis_runs.list()["runs"] == []
    assert store.workflow_runs.list()["runs"] == []


@pytest.mark.parametrize("entry_name", ["report.md", "report.html"])
def test_bridge_report_create_read_preview_export_reopen_uses_frozen_sources(
    inproc, tmp_path, monkeypatch, entry_name,
):
    harness = inproc()
    fixture = prepared(harness, tmp_path, entry_name=entry_name)
    project, store, snapshot, assets, originals = fixture
    assert METHODS <= set(harness.call("hello", {"protocol": 1})["methods"])
    assert METHODS <= harness.call("script.catalog")["operations"].keys()
    before_events = harness.events_of("project.changed")

    def forbidden(*args, **kwargs):
        pytest.fail("Report operations must not evaluate, execute, or submit a source")

    monkeypatch.setattr(harness.bridge.graphs, "evaluate", forbidden)
    monkeypatch.setattr(harness.bridge.graphs, "validate", forbidden)
    monkeypatch.setattr(harness.bridge.project_runs, "call", forbidden)
    monkeypatch.setattr(harness.bridge.projects._executor, "start", forbidden)
    assert project.reports.list()["reports"] == []
    identity, created, saved = create_report(harness, fixture)
    assert created["revision"] == 3 and created["record_id"] == identity
    assert created["table_id"] == TABLE_ID
    assert saved["manifest"]["snapshot_id"] == snapshot["id"]
    assert saved["manifest"]["source_revision"] == 2
    assert saved["manifest"]["sources"] == []
    digest = saved["source_sha256"]
    selection = {"expected_revision": 3, "expected_source_sha256": digest}
    for name in originals:
        (store.directory / name).unlink()

    # Navigation is metadata-only even when all original files are gone.
    with monkeypatch.context() as patch:
        patch.setattr(report_storage, "_read_asset", forbidden)
        patch.setattr(ProjectStore, "snapshot", forbidden)
        assert project.reports.get(identity)["report"] == saved
        listed = project.reports.list(offset=0, limit=1)
        assert listed["total"] == 1 and listed["reports"] == [
            {key: value for key, value in saved.items() if key != "manifest"}
        ]
        assert project.reports.list(offset=1, limit=1)["reports"] == []

    asset = project.reports.asset(identity, assets[0]["path"], **selection)
    assert base64.b64decode(asset["data"], validate=True) == originals[entry_name]
    assert asset["content_sha256"] == hashlib.sha256(originals[entry_name]).hexdigest()
    assert asset["source_sha256"] == digest and asset["source_sha256"] != asset["content_sha256"]
    preview = project.reports.preview(identity, **selection)
    rendered = base64.b64decode(preview["data"], validate=True)
    assert preview["project_id"] == store.info()["id"] and preview["report_id"] == identity
    assert preview["revision"] == 3 and preview["source_sha256"] == digest
    assert preview["renderer"] == "stk.report-renderer/1"
    assert preview["source_content_sha256"] == asset["content_sha256"]
    assert preview["source_size"] == asset["size"] == len(originals[entry_name])
    assert preview["source_mime"] == asset["mime"]
    assert preview["content_sha256"] == hashlib.sha256(rendered).hexdigest()
    assert preview["content_sha256"] not in {digest, asset["content_sha256"]}
    assert preview["size"] == len(rendered) and preview["mime"] == "text/html; charset=utf-8"
    assert preview["path"] == assets[0]["path"]
    assert str(UUID(preview["session_id"])) == preview["session_id"]
    assert "冻结报告" in rendered.decode() and b"drop-script" not in rendered
    assert b'../images/plot%20%23100%25.png' in rendered
    expected_prefix = "/".join((preview["session_id"], store.info()["id"], identity, digest, "assets")) + "/"
    assert ("https://stk-preview.invalid/" + expected_prefix).encode() in rendered
    again = project.reports.preview(identity, **selection)
    assert again["session_id"] != preview["session_id"]
    assert again["source_content_sha256"] == preview["source_content_sha256"]

    destination = tmp_path / "export.zip"
    exported = project.reports.export_file(identity, destination, **selection)
    archive_bytes = destination.read_bytes()
    assert exported["sha256"] == hashlib.sha256(archive_bytes).hexdigest()
    assert exported["size"] == len(archive_bytes) and exported["source_sha256"] == digest
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {EXPORT_MANIFEST, *(asset["path"] for asset in assets)}
        assert archive.read(assets[0]["path"]) == originals[entry_name]
        assert archive.read(assets[1]["path"]) == PNG
        envelope = json.loads(archive.read(EXPORT_MANIFEST))
        assert envelope["manifest"] == saved["manifest"] and envelope["source_sha256"] == digest

    assert harness.error("project.reports.export_file", {
        "handle": project.handle, "report_id": identity, "destination": str(destination), **selection,
    })["code"] == "invalid_params"
    assert destination.read_bytes() == archive_bytes
    assert harness.events_of("project.changed") == before_events + [{"handle": project.handle, "revision": 3}]
    assert project.close()
    assert harness.error("project.reports.get", {"handle": project.handle, "report_id": identity})["code"] == "not_found"
    reopened_info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    reopened = Project(harness.call, reopened_info["handle"])
    assert reopened.handle != project.handle
    assert reopened.reports.get(identity)["report"] == saved
    assert reopened.reports.asset(identity, assets[0]["path"], **selection) == asset
    assert reopened.reports.preview(identity, **selection)["session_id"] != preview["session_id"]
    assert len(store.history()) == 3 and store.info()["revision"] == 3
    assert_no_runs(store)
    assert harness.events_of("ui.request") == []
    assert harness.events_of("project.changed") == before_events + [{"handle": project.handle, "revision": 3}]
    harness.assert_clean()


def test_pdf_preview_is_identity_bytes_with_fresh_session(inproc, tmp_path):
    harness = inproc()
    fixture = prepared(harness, tmp_path, entry_name="paper.pdf")
    project, _, _, assets, originals = fixture
    identity, _, saved = create_report(harness, fixture)
    selection = {"expected_revision": 3, "expected_source_sha256": saved["source_sha256"]}
    asset = project.reports.asset(identity, assets[0]["path"], **selection)
    preview = project.reports.preview(identity, **selection)
    assert preview["renderer"] == "identity" and preview["mime"] == "application/pdf"
    assert preview["source_mime"] == "application/pdf"
    assert preview["content_sha256"] == preview["source_content_sha256"] == asset["content_sha256"]
    assert base64.b64decode(preview["data"]) == originals["paper.pdf"]
    assert preview["size"] == preview["source_size"] == asset["size"]
    assert project.reports.preview(identity, **selection)["session_id"] != preview["session_id"]
    harness.assert_clean()


def test_preview_accepts_long_relative_url_between_legal_manifest_paths(inproc, tmp_path):
    harness = inproc()
    directory = tmp_path / "nested-project"
    info = harness.call("project.create", {"directory": str(directory), "name": "Nested report"})["project"]
    project = Project(harness.call, info["handle"])
    entry = "d/" * 63 + "report.md"
    image = ("b" * 15 + "/") * 60 + "image.png"
    relative = posixpath.relpath(image, posixpath.dirname(entry))
    assert len(entry.encode()) == 135 and len(image.encode()) == 969 and len(relative.encode()) == 1158
    (directory / "report.md").write_text(f"# Nested report\n\n![Result]({relative})", encoding="utf-8")
    (directory / "image.png").write_bytes(PNG)
    records = project.files.index(["report.md", "image.png"], expected_revision=0)["record_ids"]
    snapshot = project.snapshots.capture(records, expected_revision=1)["snapshot"]
    identity = str(uuid4())
    project.reports.create("Nested report", snapshot["id"], records[0],
        [{"record_id": records[0], "path": entry}, {"record_id": records[1], "path": image}],
        report_id=identity, expected_revision=2)
    saved = project.reports.get(identity)["report"]
    preview = project.reports.preview(identity, expected_revision=3,
        expected_source_sha256=saved["source_sha256"])
    data = base64.b64decode(preview["data"], validate=True)
    assert preview["path"] == entry and preview["renderer"] == "stk.report-renderer/1"
    assert f'src="{relative}"'.encode() in data
    assert preview["content_sha256"] == hashlib.sha256(data).hexdigest()
    harness.assert_clean()


def test_conflicts_unlisted_assets_foreign_projects_and_failed_create_do_not_write(inproc, tmp_path):
    harness = inproc()
    fixture = prepared(harness, tmp_path)
    project, store, snapshot, assets, _ = fixture
    identity, _, saved = create_report(harness, fixture)
    events, history = harness.events_of("project.changed"), store.history()
    base = {"handle": project.handle, "report_id": identity, "expected_revision": 3,
            "expected_source_sha256": saved["source_sha256"]}
    for action, extra in (("asset", {"path": assets[0]["path"]}), ("preview", {}),
                          ("export_file", {"destination": str(tmp_path / "must-not-exist.zip")})):
        method = "project.reports." + action
        assert harness.error(method, {**base, **extra, "expected_revision": 2})["code"] == "conflict"
        assert harness.error(method, {**base, **extra, "expected_source_sha256": "0" * 64})["code"] == "conflict"
        assert harness.error(method, {**base, **extra, "expected_source_sha256": "bad"})["code"] == "invalid_params"
    assert harness.error("project.reports.asset", {**base, "path": "unlisted.png"})["code"] == "not_found"
    assert harness.error("project.reports.asset", {**base, "path": "../outside.png"})["code"] == "invalid_params"
    creation = {"handle": project.handle, "report_id": str(uuid4()), "name": "Bad", "snapshot_id": snapshot["id"],
                "entry_record_id": assets[0]["record_id"], "assets": assets, "expected_revision": 3}
    assert harness.error("project.reports.create", {**creation, "report_id": identity})["code"] == "conflict"
    assert harness.error("project.reports.create", {**creation, "expected_revision": 2})["code"] == "conflict"
    assert harness.error("project.reports.create", {**creation, "assets": [
        {**assets[0], "path": "../escape.md"}, assets[1],
    ]})["code"] == "invalid_params"

    foreign_info = harness.call("project.create", {"directory": str(tmp_path / "other"), "name": "Independent"})["project"]
    foreign = foreign_info["handle"]
    assert harness.error("project.reports.get", {"handle": foreign, "report_id": identity})["code"] == "not_found"
    assert harness.error("project.reports.preview", {**base, "handle": foreign, "expected_revision": 0})["code"] == "not_found"
    assert harness.error("project.reports.asset", {**base, "handle": foreign,
        "expected_revision": 0, "path": assets[0]["path"]})["code"] == "not_found"
    assert harness.error("project.reports.create", {**creation, "handle": foreign,
        "expected_revision": 0})["code"] == "invalid_params"
    assert harness.call("project.reports.list", {"handle": foreign})["reports"] == []
    assert not (tmp_path / "must-not-exist.zip").exists()
    assert store.history() == history and store.info()["revision"] == 3
    assert harness.events_of("project.changed") == events
    harness.assert_clean()


def test_corrupt_frozen_bytes_remain_metadata_readable_but_never_preview_or_export(inproc, tmp_path):
    harness = inproc()
    fixture = prepared(harness, tmp_path)
    project, store, _, assets, _ = fixture
    identity, _, saved = create_report(harness, fixture)
    first = saved["manifest"]["assets"][0]
    store.snapshots._object(first["sha256"]).write_bytes(b"x" * first["size"])
    before_events, history = harness.events_of("project.changed"), store.history()
    assert project.reports.get(identity)["report"] == saved
    assert project.reports.list()["reports"][0]["state"] == "readable"
    base = {"handle": project.handle, "report_id": identity, "expected_revision": 3,
            "expected_source_sha256": saved["source_sha256"]}
    for action, extra in (("asset", {"path": assets[0]["path"]}), ("preview", {}),
                          ("export_file", {"destination": str(tmp_path / "corrupt.zip")})):
        error = harness.error("project.reports." + action, {**base, **extra})
        assert error["code"] == "invalid_params" and "checksum" in error["message"]
    assert not (tmp_path / "corrupt.zip").exists()
    assert store.history() == history and harness.events_of("project.changed") == before_events
    harness.assert_clean()


@pytest.mark.parametrize("action", ["create", "get", "list", "asset", "preview", "export_file"])
def test_report_request_contracts_keep_explicit_selection_and_reject_extra_fields(action):
    params = {"handle": "a" * 32}
    if action != "list":
        params["report_id"] = str(uuid4())
    if action == "create":
        record = str(uuid4())
        params.update(name="Report", snapshot_id=str(uuid4()), entry_record_id=record,
                      assets=[{"record_id": record, "path": "report.md"}], expected_revision=0)
    if action in {"asset", "preview", "export_file"}:
        params.update(expected_revision=0, expected_source_sha256="a" * 64)
    if action == "asset":
        params["path"] = "report.md"
    if action == "export_file":
        params["destination"] = "/tmp/report.zip"
    method = "project.reports." + action
    assert validate_params(method, params) == []
    assert validate_params(method, {**params, "run": True})
    if "expected_revision" in params:
        assert validate_params(method, {**params, "expected_revision": True})
        assert validate_params(method, {key: value for key, value in params.items() if key != "expected_revision"})
    if "expected_source_sha256" in params:
        assert validate_params(method, {**params, "expected_source_sha256": "not-a-digest"})
        assert validate_params(method, {key: value for key, value in params.items() if key != "expected_source_sha256"})
    if action == "list":
        for extra in ({"offset": True}, {"offset": -1}, {"limit": 0}, {"limit": 101}):
            assert validate_params(method, {**params, **extra})
