"""The ordinary-table file index: portability, metadata-only edits and stable resource IDs."""
import shutil
import sqlite3
import json

from click.testing import CliRunner

import pytest

from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project.files import TABLE_ID, FIELD_IDS, PLATFORM
from suan.project.cli import project


@pytest.fixture
def files(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Files")
    (store.directory / "inputs").mkdir()
    inside = store.directory / "inputs" / "参数.json"
    inside.write_text('{"temperature":300}', encoding="utf-8")
    outside = tmp_path / "外部 image.png"
    outside.write_bytes(b"not actually an image")
    return store, inside, outside


def test_index_uses_shared_table_and_stable_ids_with_relative_and_external_paths(files):
    store, inside, outside = files
    answer = store.files.index([str(inside), str(outside), str(inside)], expected_revision=0)
    assert answer["revision"] == 1 and len(answer["record_ids"]) == 2
    table = store.snapshot()["tables"][0]
    assert table["id"] == TABLE_ID
    assert store.snapshot()["file_index"] == {"table_id": TABLE_ID, "fields": FIELD_IDS, "compatible": True}
    records = store.files.list()["records"]
    assert records[0]["path"] == "inputs/参数.json" and records[0]["location"] == "project"
    assert records[0]["kind"] == "data" and records[0]["size"] == inside.stat().st_size
    assert records[1]["path"] == str(outside) and records[1]["location"] == "external:" + PLATFORM
    assert records[1]["kind"] == "image"  # Filename classification only; contents were not inspected.
    assert all(row["state"] == "present" for row in records)
    again = store.files.index(["inputs/参数.json"], expected_revision=1)
    assert again["record_ids"] == answer["record_ids"][:1]
    assert len(store.files.list()["records"]) == 2
    assert ProjectStore(store.directory).files.list() == store.files.list()


def test_project_relocation_preserves_relative_paths_and_external_locations(files, tmp_path):
    store, inside, outside = files
    ids = store.files.index([str(inside), str(outside)], expected_revision=0)["record_ids"]
    moved = tmp_path / "moved 项目"
    shutil.move(store.directory, moved)
    reopened = ProjectStore(moved)
    assert reopened.files.resolve(ids[0], expected_revision=1)["path"] == str(moved / "inputs" / inside.name)
    assert reopened.files.resolve(ids[1], expected_revision=1)["path"] == str(outside)


def test_refresh_records_missing_changed_and_future_files_without_touching_contents(files):
    store, inside, outside = files
    future = store.directory / "output" / "future.pdf"
    ids = store.files.index([str(inside), str(outside), str(future)], expected_revision=0)["record_ids"]
    original = outside.read_bytes()
    inside.write_bytes(b"changed input")
    outside.unlink()
    future.parent.mkdir()
    future.write_bytes(b"future data")
    assert store.files.list()["records"][0]["size"] != inside.stat().st_size  # No background filesystem polling.
    store.files.refresh(ids, expected_revision=1)
    rows = store.files.list()["records"]
    assert rows[0]["state"] == "present" and rows[0]["size"] == len(b"changed input")
    assert rows[1]["state"] == "missing" and rows[1]["size"] is None and rows[1]["modified"] is None
    assert rows[2]["state"] == "present" and rows[2]["kind"] == "document"
    store.undo(expected_revision=2)
    assert store.files.list()["records"][1]["state"] == "present"  # Undo restores observations, not files.
    assert not outside.exists() and inside.read_bytes() == b"changed input"
    with pytest.raises(ProjectError, match="missing"):
        store.files.resolve(ids[1], expected_revision=3)
    assert original == b"not actually an image"


def test_index_and_delete_undo_leave_files_intact_and_restore_identical_record_ids(files):
    store, inside, _ = files
    identity = store.files.index([str(inside)], expected_revision=0)["record_ids"][0]
    store.undo(expected_revision=1)
    assert store.snapshot()["tables"] == [] and "file_index" not in store.snapshot()
    assert inside.is_file()
    store.redo(expected_revision=2)
    assert store.files.list()["records"][0]["id"] == identity
    store.apply([{"op": "delete_record", "id": identity}], expected_revision=3)
    assert inside.is_file() and store.files.list()["records"] == []
    store.undo(expected_revision=4)
    assert store.files.list()["records"][0]["id"] == identity


def test_field_names_can_change_but_structural_damage_requires_explicit_repair(files):
    store, inside, _ = files
    store.files.index([str(inside)], expected_revision=0)
    store.apply([{"op": "rename_table", "id": TABLE_ID, "name": "项目文件"},
                 {"op": "rename_field", "id": FIELD_IDS["path"], "name": "文件位置"}], expected_revision=1)
    assert store.files.list()["records"][0]["path"] == "inputs/参数.json"
    store.apply([{"op": "delete_field", "id": FIELD_IDS["path"]}], expected_revision=2)
    assert not store.snapshot()["file_index"]["compatible"]
    with pytest.raises(ProjectError, match="incompatible"):
        store.files.index([str(inside)], expected_revision=3)
    store.undo(expected_revision=3)
    assert store.snapshot()["file_index"]["compatible"]


@pytest.mark.parametrize("bad", ["../outside.txt", "/absolute.txt", "sub/../../escape", "..\\escape", ""])
def test_edited_relative_paths_cannot_escape_project(files, bad):
    store, inside, _ = files
    identity = store.files.index([str(inside)], expected_revision=0)["record_ids"][0]
    store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity, "field_id": FIELD_IDS["path"], "value": bad}], expected_revision=1)
    with pytest.raises(ProjectError):
        store.files.resolve(identity, expected_revision=2)
    store.files.refresh([identity], expected_revision=2)
    assert store.files.list()["records"][0]["state"] == "invalid_location"


def test_external_other_platform_is_not_treated_as_a_project_relative_path(files):
    store, inside, _ = files
    identity = store.files.index([str(inside)], expected_revision=0)["record_ids"][0]
    other = "external:posix" if PLATFORM == "windows" else "external:windows"
    path = "/tmp/file" if PLATFORM == "windows" else "C:\\research\\file"
    store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity, "field_id": FIELD_IDS[key], "value": value}
                 for key, value in (("location", other), ("path", path))], expected_revision=1)
    with pytest.raises(ProjectError, match="another platform"):
        store.files.resolve(identity, expected_revision=2)


def test_symlink_registered_as_its_explicit_target_and_later_escape_is_rejected(files):
    store, inside, outside = files
    link = store.directory / "link.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("This host does not allow creating symlinks")
    external = store.files.index([str(link)], expected_revision=0)["record_ids"][0]
    assert store.files.resolve(external, expected_revision=1)["path"] == str(outside)
    identity = store.files.index([str(inside)], expected_revision=1)["record_ids"][0]
    inside.unlink()
    inside.symlink_to(outside)
    with pytest.raises(ProjectError, match="outside"):
        store.files.resolve(identity, expected_revision=2)
    store.files.refresh([identity], expected_revision=2)
    assert store.files.list()["records"][1]["state"] == "invalid_location"


def test_bad_batch_conflict_and_database_paths_do_not_mutate_index(files):
    store, inside, _ = files
    before = store.snapshot()
    for paths in ([], [str(inside)] * 101, [str(inside), str(store.directory)], [str(store.path)], ["bad\0path"]):
        with pytest.raises(ProjectError):
            store.files.index(paths, expected_revision=0)
        assert store.snapshot() == before
    store.files.index([str(inside)], expected_revision=0)
    with pytest.raises(RevisionConflict):
        store.files.index([str(inside)], expected_revision=0)
    with pytest.raises(RevisionConflict):
        store.files.resolve(store.files.list()["records"][0]["id"], expected_revision=0)


def test_format_two_keeps_existing_operations_but_requires_explicit_upgrade_for_index(files):
    store, inside, _ = files
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS project_agent_objects")
        db.execute("DROP TABLE IF EXISTS project_agent_events")
        db.execute("DROP TABLE IF EXISTS project_agent_sessions")
        db.execute("DROP TABLE IF EXISTS project_labels")
        db.execute("DROP TABLE IF EXISTS project_archive")
        db.execute("DROP TABLE IF EXISTS workflow_run_events")
        db.execute("DROP TABLE IF EXISTS workflow_run_plans")
        db.execute("DROP TABLE IF EXISTS analysis_run_events")
        db.execute("DROP TABLE IF EXISTS analysis_run_plans")
        db.execute("DROP TABLE IF EXISTS project_requests")
        db.execute("DROP TABLE IF EXISTS project_proposals")
        db.execute("DROP TABLE IF EXISTS project_messages")
        db.execute("DROP TABLE IF EXISTS project_contexts")
        db.execute("DROP TABLE IF EXISTS project_drafts")
        db.execute("DROP TABLE edit_journal")
        db.execute("DROP TABLE run_observations")
        db.execute("DROP TABLE run_plans")
        db.execute("DROP TABLE project_snapshots")
        db.execute("PRAGMA user_version=2")
    with pytest.raises(ProjectError, match="Upgrade"):
        store.files.index([str(inside)], expected_revision=0)
    store.upgrade(expected_revision=0)
    store.files.index([str(inside)], expected_revision=1)
    assert store.files.list()["records"][0]["state"] == "present"


def test_cli_file_index_uses_project_relative_paths_and_revision_checks(files):
    store, inside, _ = files
    runner = CliRunner()
    response = runner.invoke(project, ["files", "index", str(store.directory), "inputs/参数.json", "--expected-revision", "0"])
    assert response.exit_code == 0, response.output
    identity = json.loads(response.output)["record_ids"][0]
    response = runner.invoke(project, ["files", "resolve", str(store.directory), identity, "--expected-revision", "1"])
    assert response.exit_code == 0, response.output
    assert json.loads(response.output)["path"] == str(inside)
    response = runner.invoke(project, ["files", "list", str(store.directory)])
    assert response.exit_code == 0 and json.loads(response.output)["records"][0]["id"] == identity
    response = runner.invoke(project, ["files", "refresh", str(store.directory), identity, "--expected-revision", "1"])
    assert response.exit_code == 0 and json.loads(response.output)["revision"] == 2
