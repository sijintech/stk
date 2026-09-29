"""Frozen input bytes survive source edits, undo and relocation; corrupt objects are not repaired."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project import snapshots as module
from suan.project.cli import project
from suan.project.store import FORMAT_VERSION
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401


@pytest.fixture
def indexed(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Frozen inputs")
    inside, outside = store.directory / "输入.json", tmp_path / "external.dat"
    inside.write_bytes(b'{"temperature":300}')
    outside.write_bytes(b"external inputs")
    ids = store.files.index([str(inside), str(outside)], expected_revision=0)["record_ids"]
    return store, ids, inside, outside


def test_capture_frozen_bytes_survive_source_changes_index_undo_and_reopen(indexed):
    store, ids, inside, outside = indexed
    old = inside.read_bytes()
    captured = store.snapshots.capture(ids, expected_revision=1)
    snapshot = captured["snapshot"]
    assert captured["revision"] == 2 and snapshot["manifest"]["source_revision"] == 1
    assert snapshot["manifest"]["files"][0]["sha256"] == hashlib.sha256(old).hexdigest()
    assert store.snapshot()["edit_history"]["undo_revision"] == 1  # Capture is an append-only historical fact.
    inside.write_bytes(b"new inputs")
    outside.unlink()
    store.undo(expected_revision=2)
    assert store.snapshot()["tables"] == []
    reopened = ProjectStore(store.directory)
    assert reopened.snapshots.get(snapshot["id"]) == snapshot
    assert reopened.snapshots.verify(snapshot["id"])["ok"]
    assert Path(reopened.snapshots.resolve(snapshot["id"], ids[0])["path"]).read_bytes() == old
    assert inside.read_bytes() == b"new inputs" and not outside.exists()
    assert store.history()[1]["commands"][0]["op"] == "capture_files"


def test_identical_contents_share_one_object_but_captures_preserve_source_revision(indexed):
    store, ids, inside, outside = indexed
    outside.write_bytes(inside.read_bytes())
    first = store.snapshots.capture([*ids, ids[0]], expected_revision=1)["snapshot"]
    second = store.snapshots.capture(ids, expected_revision=2)["snapshot"]
    assert first["id"] != second["id"]
    assert len(first["manifest"]["files"]) == 2
    assert len(list((store.directory / ".stk/objects/sha256").glob("*/*"))) == 1
    assert [s["manifest"]["source_revision"] for s in store.snapshots.list()["snapshots"]] == [1, 2]
    assert not list((store.directory / ".stk/tmp").iterdir())


def test_empty_input_is_a_valid_snapshot_object(indexed):
    store, ids, inside, _ = indexed
    inside.write_bytes(b"")
    snapshot = store.snapshots.capture([ids[0]], expected_revision=1, max_bytes=1)["snapshot"]
    file = snapshot["manifest"]["files"][0]
    assert file["size"] == 0 and file["sha256"] == hashlib.sha256(b"").hexdigest()
    assert store.snapshots.verify(snapshot["id"])["ok"]


def test_fd_and_path_ctime_may_have_different_meanings(indexed, monkeypatch):
    store, ids, inside, _ = indexed
    original = module.os.fstat
    def fd_stat(fd):
        info = original(fd)
        values = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        values["st_ctime_ns"] += 1000000000  # Windows 3.12: fd change time vs path creation time.
        return SimpleNamespace(**values)
    monkeypatch.setattr(module.os, "fstat", fd_stat)
    snapshot = store.snapshots.capture([ids[0]], expected_revision=1)["snapshot"]
    assert store.snapshots.verify(snapshot["id"])["ok"]
    assert Path(store.snapshots.resolve(snapshot["id"], ids[0])["path"]).read_bytes() == inside.read_bytes()


@pytest.mark.skipif(os.name == "nt", reason="symlink/FIFO creation needs special Windows privileges")
def test_snapshot_storage_rejects_links_and_nonregular_object_replacements(indexed, tmp_path):
    store, ids, _, _ = indexed
    outside = tmp_path / "other"
    outside.mkdir()
    (store.directory / ".stk").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectError, match="symbolic"):
        store.snapshots.capture([ids[0]], expected_revision=1)
    assert list(outside.iterdir()) == []
    (store.directory / ".stk").unlink()
    snapshot = store.snapshots.capture([ids[0]], expected_revision=1)["snapshot"]
    path = Path(store.snapshots.resolve(snapshot["id"], ids[0])["path"])
    path.unlink()
    os.mkfifo(path)
    # A replaced FIFO must fail immediately rather than block waiting for a writer.
    assert not store.snapshots.verify(snapshot["id"])["ok"]
    path.unlink()
    target = outside / "content"
    target.write_bytes(b"untrusted object")
    path.symlink_to(target)
    with pytest.raises(ProjectError, match="symbolic"):
        store.snapshots.resolve(snapshot["id"], ids[0])


def test_relocate_entire_project_keeps_frozen_external_inputs(indexed, tmp_path):
    store, ids, inside, outside = indexed
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    outside.unlink()
    target = tmp_path / "移走的项目"
    shutil.move(store.directory, target)
    moved = ProjectStore(target)
    assert moved.snapshots.verify(snapshot["id"])["ok"]
    assert Path(moved.snapshots.resolve(snapshot["id"], ids[1])["path"]).is_relative_to(target)


def test_missing_and_corrupt_objects_are_reported_and_never_overwritten(indexed):
    store, ids, inside, _ = indexed
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    first = Path(store.snapshots.resolve(snapshot["id"], ids[0])["path"])
    second = Path(store.snapshots.resolve(snapshot["id"], ids[1])["path"])
    first.write_bytes(b"x" * first.stat().st_size)
    second.unlink()
    checked = store.snapshots.verify(snapshot["id"])
    assert not checked["ok"] and [f["state"] for f in checked["files"]] == ["invalid", "missing"]
    with pytest.raises(ProjectError, match="checksum"):
        store.snapshots.resolve(snapshot["id"], ids[0])
    with pytest.raises(ProjectError, match="checksum"):
        store.snapshots.capture([ids[0]], expected_revision=2)
    assert first.read_bytes() != inside.read_bytes()
    assert store.info()["revision"] == 2 and len(store.snapshots.list()["snapshots"]) == 1


def test_capture_budget_and_missing_file_are_atomic(indexed):
    store, ids, inside, outside = indexed
    with pytest.raises(ProjectError, match="max_bytes"):
        store.snapshots.capture(ids, expected_revision=1, max_bytes=inside.stat().st_size)
    assert store.info()["revision"] == 1 and store.snapshots.list()["snapshots"] == []
    outside.unlink()
    with pytest.raises(ProjectError, match="missing"):
        store.snapshots.capture(ids, expected_revision=1)
    assert store.info()["revision"] == 1
    with pytest.raises(RevisionConflict):
        store.snapshots.capture([ids[0]], expected_revision=0)
    assert not list((store.directory / ".stk/tmp").iterdir())


def test_source_mutation_during_read_cannot_publish_a_manifest(indexed, monkeypatch):
    store, ids, inside, _ = indexed
    original = module._reader
    @contextmanager
    def reader(path):
        with original(path) as stream:
            class Mutating:
                def fileno(self):
                    return stream.fileno()
                def read(self, size):
                    value = stream.read(size)
                    if value:
                        with inside.open("ab") as writer:
                            writer.write(b"changed")
                    return value
            yield Mutating()
    # Small budget bounds a growing source as well as the final metadata check.
    monkeypatch.setattr(module, "_reader", reader)
    with pytest.raises(ProjectError, match="max_bytes|changed"):
        store.snapshots.capture([ids[0]], expected_revision=1, max_bytes=100)
    assert store.snapshots.list()["snapshots"] == [] and store.info()["revision"] == 1
    assert not list((store.directory / ".stk/tmp").iterdir())


def test_revision_changed_during_copy_keeps_only_reusable_unreferenced_bytes(indexed, monkeypatch):
    store, ids, _, _ = indexed
    original = module.Snapshots._copy
    def copy(self, source, remaining):
        result = original(self, source, remaining)
        store.apply([{"op": "create_table", "name": "Concurrent edit"}], expected_revision=1)
        return result
    monkeypatch.setattr(module.Snapshots, "_copy", copy)
    with pytest.raises(RevisionConflict):
        store.snapshots.capture([ids[0]], expected_revision=1)
    assert store.snapshots.list()["snapshots"] == [] and store.info()["revision"] == 2
    assert len(list((store.directory / ".stk/objects/sha256").glob("*/*"))) == 1
    assert not list((store.directory / ".stk/tmp").iterdir())


def test_concurrent_capture_has_one_manifest_and_no_partial_objects(indexed, monkeypatch):
    store, ids, _, _ = indexed
    original, barrier = module.Snapshots._copy, threading.Barrier(2)
    def copy(self, source, remaining):
        result = original(self, source, remaining)
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(module.Snapshots, "_copy", copy)
    def capture(_):
        try:
            return store.snapshots.capture([ids[0]], expected_revision=1)
        except RevisionConflict:
            return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(capture, range(2)))
    assert sum(r is not None for r in results) == 1
    saved = store.snapshots.list()["snapshots"]
    assert len(saved) == 1 and store.snapshots.verify(saved[0]["id"])["ok"]


def test_corrupt_manifest_fails_before_using_paths(indexed):
    store, ids, _, _ = indexed
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    with sqlite3.connect(store.path) as db:
        data = json.loads(db.execute("SELECT manifest FROM project_snapshots").fetchone()[0])
        data["files"][0]["sha256"] = "../outside"
        db.execute("UPDATE project_snapshots SET manifest=?", (json.dumps(data),))
    with pytest.raises(ProjectError, match="manifest"):
        store.snapshots.get(snapshot["id"])
    with pytest.raises(ProjectError, match="manifest"):
        store.snapshots.verify(snapshot["id"])


def test_format_three_requires_explicit_backup_upgrade_and_retains_undo(indexed):
    store, ids, _, _ = indexed
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS project_requests")
        db.execute("DROP TABLE IF EXISTS project_proposals")
        db.execute("DROP TABLE IF EXISTS project_messages")
        db.execute("DROP TABLE IF EXISTS project_contexts")
        db.execute("DROP TABLE IF EXISTS project_drafts")
        db.execute("DROP TABLE run_observations")
        db.execute("DROP TABLE run_plans")
        db.execute("DROP TABLE project_snapshots")
        db.execute("PRAGMA user_version=3")
    store = ProjectStore(store.directory)
    before = store.snapshot()
    with pytest.raises(ProjectError, match="format 4"):
        store.snapshots.capture(ids, expected_revision=1)
    assert store.snapshot() == before and not (store.directory / ".stk").exists()
    result = store.upgrade(expected_revision=1)
    assert result["backup"]["format_version"] == 3 and result["format_version"] == FORMAT_VERSION
    assert store.snapshot()["edit_history"]["undo_revision"] == 1
    assert store.snapshots.capture(ids, expected_revision=2)["revision"] == 3


def test_database_backup_is_not_a_resource_backup(indexed, tmp_path):
    store, ids, _, _ = indexed
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    backup = store.backup()
    restored = tmp_path / "only-database"
    restored.mkdir()
    shutil.copyfile(backup["path"], restored / "project.sqlite3")
    recovered = ProjectStore(restored)
    assert recovered.snapshots.get(snapshot["id"]) == snapshot
    assert not recovered.snapshots.verify(snapshot["id"])["ok"]


def test_cli_capture_verify_and_resolve(indexed):
    store, ids, inside, _ = indexed
    runner = CliRunner()
    result = runner.invoke(project, ["snapshots", "capture", str(store.directory), ids[0], "--expected-revision", "1"])
    assert result.exit_code == 0, result.output
    snapshot = json.loads(result.output)["snapshot"]
    checked = runner.invoke(project, ["snapshots", "verify", str(store.directory), snapshot["id"]])
    assert checked.exit_code == 0 and json.loads(checked.output)["ok"]
    resolved = runner.invoke(project, ["snapshots", "resolve", str(store.directory), snapshot["id"], ids[0]])
    assert resolved.exit_code == 0
    assert Path(json.loads(resolved.output)["path"]).read_bytes() == inside.read_bytes()


def test_console_snapshot_capture_shares_revision_notifications_and_survives_source_removal(scripts, indexed):  # noqa: F811
    store, ids, inside, _ = indexed
    info = scripts.call("project.open", {"directory": str(store.directory)})["project"]
    session = scripts.call("script.open")["session"]
    code = f"frozen = stk.project.snapshots.capture({ids!r}, expected_revision=1)\nassert frozen['revision'] == 2\nassert stk.project.snapshots.verify(frozen['snapshot']['id'])['ok']"
    result = execute(scripts, session, code, project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    changed = scripts.wait_event(lambda e: e["event"] == "project.changed")["data"]
    assert changed == {"handle": info["handle"], "revision": 2}
    history = scripts.call("project.history", {"handle": info["handle"]})["history"]
    assert history[-1]["commands"][0]["op"] == "capture_files"
    inside.unlink()
    code = f"from pathlib import Path\nassert Path(stk.project.snapshots.resolve(frozen['snapshot']['id'], {ids[0]!r})['path']).is_file()"
    assert execute(scripts, session, code, project_handle=info["handle"])["run"]["state"] == "succeeded"
