"""Portable workspace RPCs preserve projects and never adopt UI or execute tasks themselves."""
from pathlib import Path
import hashlib
import shutil

import pytest

from suan.project import ProjectStore
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def test_project_bundle_rpc_preserves_history_assets_and_shared_identity(inproc, tmp_path):
    bridge = inproc()
    project = bridge.call("project.create", {"directory": str(tmp_path / "source"), "name": "Portable"})["project"]
    source = tmp_path / "external.dat"
    source.write_bytes(b"public scientific data\n")
    indexed = bridge.call("project.files.index", {"handle": project["handle"], "expected_revision": 0,
                                                  "paths": [str(source)]})
    snapshot = bridge.call("project.snapshot", {"handle": project["handle"]})["snapshot"]
    state = {"format": "stk.desktop.workspace-state", "version": 1, "windows": [],
             "app": {"selected_source": str(source), "value": 9223372036854775807}}
    archive = tmp_path / "research.stkworkspace"
    result = bridge.call("workspace.export", {"handle": project["handle"], "expected_revision": indexed["revision"],
                                                "path": str(archive), "state": state})
    assert result["complete"] is True and result["diagnostics"] == []
    assert result["project"]["id"] == project["id"]
    assert result["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert bridge.call("project.snapshot", {"handle": project["handle"]})["snapshot"] == snapshot
    preview = bridge.call("workspace.preview", {"path": str(archive)})
    assert preview["sha256"] == result["sha256"] and preview["state"]["app"]["selected_source"].startswith("stk-resource://")
    changed_before = len(bridge.events_of("project.changed"))
    restored = bridge.call("workspace.import", {"path": str(archive), "destination": str(tmp_path / "restored"),
                                                "expected_sha256": preview["sha256"]})
    assert restored["complete"] is True
    assert Path(restored["state"]["app"]["selected_source"]).read_bytes() == source.read_bytes()
    imported = ProjectStore(restored["project_directory"])
    assert imported.snapshot() == snapshot
    assert imported.history() == ProjectStore(project["directory"]).history()
    assert len(bridge.events_of("project.changed")) == changed_before
    reopened = bridge.call("workspace.open", {"directory": restored["workspace_path"]})
    assert reopened["state"] == restored["state"] and reopened["path_map"] == restored["path_map"]
    # No native project has been selected or run by any of these local package operations.
    assert bridge.call("project.list")["projects"] == [bridge.call("project.open", {"directory": project["directory"]})["project"]]
    assert not bridge.violations


def test_workspace_without_project_and_reopen_after_second_move(inproc, tmp_path):
    bridge = inproc()
    resource = tmp_path / "payload.bin"
    resource.write_bytes(b"public payload")
    state = {"windows": [{"draft": "print('explicit run')"}], "payload": str(resource)}
    archive = tmp_path / "viewer.stkworkspace"
    exported = bridge.call("workspace.export", {"path": str(archive), "state": state,
                                                "resources": [{"id": "payload", "path": str(resource)}]})
    assert exported["project"] is None and exported["complete"]
    target = tmp_path / "one"
    restored = bridge.call("workspace.import", {"path": str(archive), "destination": str(target),
                                                "expected_sha256": exported["sha256"]})
    assert restored["project_directory"] is None and bridge.call("project.list")["projects"] == []
    moved = tmp_path / "two"
    target.rename(moved)
    reopened = bridge.call("workspace.open", {"directory": str(moved)})
    assert Path(reopened["state"]["payload"]).is_relative_to(moved)
    assert Path(reopened["state"]["payload"]).read_bytes() == resource.read_bytes()
    assert reopened["state"]["windows"] == state["windows"]
    assert not bridge.violations


def test_reexport_relocated_workspace_keeps_original_external_file_identity(inproc, tmp_path):
    bridge = inproc()
    original = bridge.call("project.create", {"directory": str(tmp_path / "source-project"),
                                                "name": "Repeated migration"})["project"]
    external = tmp_path / "original-external.dat"
    content = b"public immutable scientific input\n"
    external.write_bytes(content)
    indexed = bridge.call("project.files.index", {"handle": original["handle"], "expected_revision": 0,
                                                  "paths": [str(external)]})
    source_store = ProjectStore(original["directory"])
    file_id = source_store.files.list()["records"][0]["id"]
    snapshot, history = source_store.snapshot(), source_store.history()
    archive = tmp_path / "first.stkworkspace"
    first = bridge.call("workspace.export", {"handle": original["handle"], "expected_revision": indexed["revision"],
                                               "path": str(archive), "state": {"selected_file": str(external)}})
    one = bridge.call("workspace.import", {"path": str(archive), "destination": str(tmp_path / "first-machine"),
                                             "expected_sha256": first["sha256"]})
    external.unlink()
    moved_project = bridge.call("project.open", {"directory": one["project_directory"]})["project"]
    resolved = bridge.call("project.files.resolve", {"handle": moved_project["handle"],
                                                      "expected_revision": indexed["revision"], "record_id": file_id})
    assert Path(resolved["path"]).read_bytes() == content
    second_archive = tmp_path / "second.stkworkspace"
    second = bridge.call("workspace.export", {"handle": moved_project["handle"],
                                                "expected_revision": indexed["revision"],
                                                "path": str(second_archive), "state": one["state"]})
    assert second["complete"], second["diagnostics"]
    two = bridge.call("workspace.import", {"path": str(second_archive), "destination": str(tmp_path / "second-machine"),
                                             "expected_sha256": second["sha256"]})
    # The new package must work after the entire previous machine disappears.
    bridge.call("project.close", {"handle": moved_project["handle"]})
    shutil.rmtree(tmp_path / "first-machine")
    final = bridge.call("project.open", {"directory": two["project_directory"]})["project"]
    final_file = bridge.call("project.files.resolve", {"handle": final["handle"],
                                                        "expected_revision": indexed["revision"], "record_id": file_id})
    assert Path(final_file["path"]).is_relative_to(tmp_path / "second-machine")
    assert Path(final_file["path"]).read_bytes() == content
    assert Path(two["state"]["selected_file"]).read_bytes() == content
    final_store = ProjectStore(two["project_directory"])
    assert final_store.snapshot() == snapshot
    assert final_store.history() == history
    assert source_store.snapshot() == snapshot and source_store.history() == history
    assert not bridge.violations


def test_archive_change_rejected_before_target_creation_and_existing_paths_preserved(inproc, tmp_path):
    bridge = inproc()
    archive = tmp_path / "work.stkworkspace"
    bridge.call("workspace.export", {"path": str(archive), "state": {"value": 1}})
    preview = bridge.call("workspace.preview", {"path": str(archive)})
    raw = archive.read_bytes()
    archive.write_bytes(raw + b"changed")
    target = tmp_path / "new"
    assert bridge.error("workspace.import", {"path": str(archive), "destination": str(target),
                                                "expected_sha256": preview["sha256"]})["code"] in {"conflict", "invalid_params"}
    assert not target.exists()
    archive.write_bytes(raw)
    existing = tmp_path / "existing"
    existing.mkdir()
    assert bridge.error("workspace.import", {"path": str(archive), "destination": str(existing)})["code"] == "invalid_params"
    assert existing.is_dir() and list(existing.iterdir()) == []
    assert bridge.error("workspace.export", {"path": str(archive), "state": {}})["code"] == "invalid_params"
    assert archive.read_bytes() == raw
    assert not bridge.violations


def test_workspace_revision_and_credentials_boundaries_are_enforced(inproc, tmp_path):
    bridge = inproc()
    project = bridge.call("project.create", {"directory": str(tmp_path / "project"), "name": "Boundaries"})["project"]
    archive = str(tmp_path / "work.stkworkspace")
    base = {"path": archive, "state": {}, "handle": project["handle"]}
    assert bridge.error("workspace.export", base)["code"] == "invalid_params"
    assert bridge.error("workspace.export", {**base, "expected_revision": 1})["code"] == "conflict"
    for key in ("api_key", "password", "credentials", "private_key", "model_endpoint", "network_policy"):
        assert bridge.error("workspace.export", {"path": archive, "state": {key: "abcdefghijklmnopqrstu"}})["code"] == "invalid_params"
    assert not Path(archive).exists()
    assert bridge.call("project.snapshot", {"handle": project["handle"]})["snapshot"]["project"]["revision"] == 0
    assert not bridge.violations


@pytest.mark.parametrize("method,params", [
    ("workspace.export", {"path": "/tmp/export.stkworkspace", "state": {}, "unrecognized": True}),
    ("workspace.preview", {"path": "/tmp/export.stkworkspace", "run": True}),
    ("workspace.import", {"path": "/tmp/export.stkworkspace", "destination": "/tmp/import", "execute": True}),
    ("workspace.open", {"directory": "/tmp/import", "network_policy": {}}),
])
def test_workspace_rpc_rejects_unsupported_execution_or_policy_fields(inproc, method, params):
    bridge = inproc()
    assert bridge.error(method, params)["code"] == "invalid_params"
    assert not bridge.violations
