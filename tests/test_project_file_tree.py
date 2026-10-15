"""Live, bounded project folders remain separate from saved resource observations."""
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project import file_tree
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.fixture
def tree(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Tree")
    folder = store.directory / "inputs"
    folder.mkdir()
    (folder / "model.py").write_text("raise AssertionError('must not run')", encoding="utf-8")
    (store.directory / "field.npy").write_bytes(b"synthetic fixture, never read while browsing")
    return store


def test_children_are_real_lazy_directories_and_do_not_register_or_read_content(tree, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("browsing must not read file content")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    root = tree.files.children(expected_revision=0)
    assert [item["name"] for item in root["entries"]] == ["inputs", "field.npy"]
    assert all(not item["registered"] for item in root["entries"])
    assert not any(item["path"].endswith("model.py") for item in root["entries"])
    child = tree.files.children("inputs", expected_revision=0)
    assert child["entries"][0]["path"] == "inputs/model.py"
    assert child["entries"][0]["kind"] == "file"
    assert tree.files.list()["records"] == [] and tree.info()["revision"] == 0


def test_live_missing_and_saved_external_observations_remain_distinct(tree, tmp_path, monkeypatch):
    outside = tmp_path / "external.npy"
    outside.write_bytes(b"synthetic")
    indexed = tree.files.index(["field.npy", "missing.npy", str(outside)], expected_revision=0)
    outside.unlink()
    (tree.directory / "field.npy").unlink()
    original_stat = Path.stat

    def stat_only_project(path, *args, **kwargs):
        if path == outside:
            pytest.fail("external registrations must not be probed while listing a directory")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_only_project)
    root = tree.files.children(expected_revision=1)
    by_name = {item["name"]: item for item in root["entries"]}
    assert by_name["field.npy"]["state"] == "missing" and by_name["field.npy"]["registered"]
    assert by_name["missing.npy"]["state"] == "missing"
    assert by_name["inputs"]["kind"] == "directory"
    assert root["registrations"][2]["location"].startswith("external:")
    assert root["registrations"][2]["state"] == "present"  # Last saved observation, not a new claim.
    assert root["registrations"][0]["id"] == indexed["record_ids"][0]
    assert tree.info()["revision"] == 1 and tree.files.list()["records"][0]["state"] == "present"


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a/../b", "a//b", "a\\b", ".stk", "backups", ".git",
                                 "project.sqlite3", "inputs/../../", "C:/outside", "inputs/\x00secret"])
def test_public_tree_boundary_rejects_escape_and_internal_paths(tree, path):
    for method in (tree.files.children, tree.files.resolve_path):
        with pytest.raises(ProjectError):
            method(path, expected_revision=0)


def test_internal_database_hidden_state_and_backups_are_not_listed(tree):
    for name in (".stk", ".git", "backups", "__pycache__"):
        (tree.directory / name).mkdir()
        (tree.directory / name / "private.txt").write_text("not a secret: synthetic fixture")
    (tree.directory / ".env").write_text("synthetic fixture")
    names = {item["name"] for item in tree.files.children(expected_revision=0)["entries"]}
    assert names == {"inputs", "field.npy"}


def test_links_are_visible_but_never_followed_and_cannot_be_opened(tree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_text("synthetic outside fixture")
    try:
        (tree.directory / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Platform cannot create fixture symlink: {error}")
    row = next(item for item in tree.files.children(expected_revision=0)["entries"] if item["name"] == "linked")
    assert row["kind"] == "link" and row["size"] is None
    with pytest.raises(ProjectError, match="links|regular"):
        tree.files.resolve_path("linked", expected_revision=0)
    with pytest.raises(ProjectError, match="links"):
        tree.files.children("linked", expected_revision=0)
    with pytest.raises(ProjectError, match="links"):
        tree.files.resolve_path("linked/private.py", expected_revision=0)


def test_paging_bounds_listing_and_reports_partial_scan_explicitly(tree, monkeypatch):
    for number in range(8):
        (tree.directory / f"f{number}.npy").touch()
    page = tree.files.children(expected_revision=0, limit=3)
    next_page = tree.files.children(expected_revision=0, limit=3, offset=page["next_offset"])
    assert not {row["path"] for row in page["entries"]} & {row["path"] for row in next_page["entries"]}
    assert not page["truncated"]
    monkeypatch.setattr(file_tree, "MAX_ENTRIES", 4)
    limited = tree.files.children(expected_revision=0, limit=3)
    assert limited["truncated"] and len(limited["entries"]) <= 3
    for options in ({"offset": -1}, {"offset": True}, {"offset": 4097}, {"limit": 0}, {"limit": 201}):
        with pytest.raises(ProjectError):
            tree.files.children(expected_revision=0, **options)


def test_unrepresentable_child_names_are_reported_as_truncated_without_breaking_contract(tree, monkeypatch):
    class Listing:
        def __enter__(self):
            return iter([SimpleNamespace(name="x" * 4097, stat=lambda **kwargs: pytest.fail("invalid path must not be statted"))])

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(file_tree.os, "scandir", lambda directory: Listing())
    page = tree.files.children(expected_revision=0)
    assert page["entries"] == [] and page["truncated"]


def test_explicit_resolve_rechecks_links_missing_revision_and_project_relocation(tree, tmp_path):
    assert tree.files.resolve_path("inputs", expected_revision=0)["kind"] == "directory"
    result = tree.files.resolve_path("inputs/model.py", expected_revision=0)
    assert result["path"] == str(tree.directory / "inputs/model.py")
    with pytest.raises(FileNotFoundError):
        tree.files.resolve_path("inputs/absent.py", expected_revision=0)
    with pytest.raises(RevisionConflict):
        tree.files.children(expected_revision=9)
    moved = tmp_path / "moved"
    shutil.move(tree.directory, moved)
    result = ProjectStore(moved).files.resolve_path("inputs/model.py", expected_revision=0)
    assert result["path"] == str(moved / "inputs/model.py")


def test_bridge_and_python_facade_use_strict_additive_methods_without_project_mutation(inproc, tree):
    harness = inproc()
    handle = harness.call("project.open", {"directory": str(tree.directory)})["project"]["handle"]
    project = Project(harness.call, handle)
    listed = project.files.children(expected_revision=0)
    assert listed["directory"] == "" and len(listed["entries"]) == 2
    assert project.files.resolve_path("field.npy", expected_revision=0)["kind"] == "file"
    assert harness.error("project.files.children", {"handle": handle, "expected_revision": 0, "limit": 201})["code"] == "invalid_params"
    assert harness.error("project.files.children", {"handle": handle, "expected_revision": 1})["code"] == "conflict"
    assert harness.error("project.files.resolve_path", {"handle": handle, "expected_revision": 0, "path": "../outside"})["code"] == "invalid_params"
    harness.call("project.close", {"handle": handle})
    assert harness.error("project.files.children", {"handle": handle, "expected_revision": 0})["code"] == "not_found"
    assert not harness.violations and tree.info()["revision"] == 0
