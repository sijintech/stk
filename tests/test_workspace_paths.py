"""Imported resource relocation leaves every project UUID, value and journal unchanged."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project import workspace_bundle as bundle
from suan.project.files import FIELD_IDS, PLATFORM, TABLE_ID, _resolve
from suan.project.workspace_paths import resolve_workspace_path


@pytest.fixture
def workspace(tmp_path):
    store = ProjectStore.create(tmp_path / "source-project", "Relocation")
    external = tmp_path / "external.dat"; external.write_bytes(b"scientific source")
    record = store.files.index([str(external)], expected_revision=0)["record_ids"][0]
    archive = bundle.export_workspace(store.directory, tmp_path / "research.stkworkspace", state={"app": {}},
        resources=[{"id": "input", "path": str(external)}], expected_revision=1)
    imported = bundle.import_workspace(archive["path"], tmp_path / "moved-machine")
    return ProjectStore(imported["project_directory"]), record, external, imported


def descriptor(store):
    path = store.directory.parent / "workspace.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_indexed_external_file_resolves_bundled_copy_after_original_is_gone_and_second_move(workspace, tmp_path):
    store, identity, external, imported = workspace
    before, history = store.snapshot(), store.history()
    external.unlink()
    answer = store.files.resolve(identity, expected_revision=1)
    assert Path(answer["path"]).read_bytes() == b"scientific source"
    assert Path(answer["path"]).is_relative_to(store.directory.parent / "resources")
    assert store.snapshot() == before and store.history() == history
    moved = tmp_path / "second-machine"
    shutil.move(store.directory.parent, moved)
    reopened = ProjectStore(moved / "project")
    assert Path(reopened.files.resolve(identity, expected_revision=1)["path"]).read_bytes() == b"scientific source"
    assert reopened.snapshot() == before and reopened.history() == history


def test_old_windows_source_works_on_posix_without_editing_the_imported_database(workspace):
    store, identity, external, _ = workspace
    original = r"C:\\Research\\Input\\external.dat"
    # A synthetic original Windows FileIndex models a package moved to this host.
    store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                  "field_id": FIELD_IDS["location"], "value": "external:windows"},
                 {"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                  "field_id": FIELD_IDS["path"], "value": original}], expected_revision=1)
    path, saved = descriptor(store)
    saved["resources"][0]["source"] = original
    saved["project"]["source_root"] = r"C:\\Research\\Project"
    write(path, saved)
    before, history = store.snapshot(), store.history()
    answer = store.files.resolve(identity, expected_revision=2)
    assert Path(answer["path"]).read_bytes() == b"scientific source"
    assert store.snapshot() == before and store.history() == history
    assert resolve_workspace_path(store.directory, "external:windows", r"c:\\research\\input\\EXTERNAL.DAT") == Path(answer["path"])


def test_posix_sources_parse_independently_of_current_file_index_platform(workspace, monkeypatch):
    store, _, external, _ = workspace
    path, saved = descriptor(store)
    original = "/original-posix/measurements/external.dat"
    saved["resources"][0]["source"] = original
    write(path, saved)
    before, history = store.snapshot(), store.history()
    external.unlink()
    from suan.project import files
    monkeypatch.setattr(files, "PLATFORM", "windows")
    resolved = _resolve(store.directory, "external:posix", original)
    assert resolved.read_bytes() == b"scientific source"
    assert store.snapshot() == before and store.history() == history
    # The stored flavor remains authoritative even when this host is Windows.
    for location, source in [("external:posix", r"Q:\Research\external.dat"),
                             ("external:windows", original)]:
        with pytest.raises(ProjectError, match="absolute"):
            _resolve(store.directory, location, source)


def test_longest_component_prefix_selects_specific_resource_and_file_resources_have_no_children(workspace):
    store, _, _, _ = workspace
    path, saved = descriptor(store)
    package = store.directory.parent
    directory = package / "resources" / "all" / "frames"
    (directory / "nested").mkdir(parents=True)
    (directory / "nested/data.dat").write_bytes(b"broad")
    specific = package / "resources" / "specific" / "data.dat"
    specific.parent.mkdir(); specific.write_bytes(b"specific")
    saved["resources"] = [
        {"id": "all", "source": "/source/frames", "path": "resources/all/frames", "kind": "directory"},
        {"id": "specific", "source": "/source/frames/nested/data.dat", "path": "resources/specific/data.dat", "kind": "file"}]
    write(path, saved)
    assert resolve_workspace_path(store.directory, "external:posix", "/source/frames/nested/data.dat") == specific
    with pytest.raises(ProjectError, match="file resource"):
        resolve_workspace_path(store.directory, "external:posix", "/source/frames/nested/data.dat/child")
    assert resolve_workspace_path(store.directory, "external:posix", "/source/frames-suffix/data.dat") is None


@pytest.mark.parametrize("fault", ["format", "uuid", "source_relative", "escape", "duplicate_id", "duplicate_source", "wrong_resource_prefix", "private_resource", "boolean_revision", "project_extra", "state_credentials", "duplicate_keys"])
def test_malformed_descriptor_never_silently_falls_back_to_the_original_host(workspace, fault):
    store, identity, external, _ = workspace
    path, saved = descriptor(store)
    if fault == "format": saved["format"] = "other/1"
    elif fault == "uuid": saved["project"]["id"] = str(uuid4())
    elif fault == "source_relative": saved["resources"][0]["source"] = "relative/input.dat"
    elif fault == "escape": saved["resources"][0]["path"] = "resources/input/../../outside.dat"
    elif fault == "duplicate_id": saved["resources"].append(deepcopy(saved["resources"][0]))
    elif fault == "duplicate_source":
        item = deepcopy(saved["resources"][0]); item["id"] = "another"; item["path"] = "resources/another/input.dat"
        saved["resources"].append(item)
    elif fault == "wrong_resource_prefix": saved["resources"][0]["path"] = "project/project.sqlite3"
    elif fault == "private_resource": saved["resources"][0]["path"] = "resources/input/.env"
    elif fault == "boolean_revision": saved["project"]["revision"] = True
    elif fault == "project_extra": saved["project"]["unexpected"] = 1
    elif fault == "state_credentials": saved["state"] = {"api_key": "abcdefghijklmnopqrstu"}
    write(path, saved)
    if fault == "duplicate_keys": path.write_text(path.read_text().replace('"format":', '"format":"stk.workspace/1","format":', 1))
    before = store.snapshot()
    with pytest.raises(ProjectError):
        store.files.resolve(identity, expected_revision=1)
    assert store.snapshot() == before and external.exists()


def test_symlink_descriptor_or_resource_is_rejected_without_following_it(workspace, tmp_path):
    if os.name == "nt": pytest.skip("POSIX symlink creation scenario; Windows junction guard is shared")
    store, identity, _, _ = workspace
    path, saved = descriptor(store)
    real = path.with_name("real-workspace.json"); path.rename(real); path.symlink_to(real)
    with pytest.raises(ProjectError, match="symbolic|reparse"):
        store.files.resolve(identity, expected_revision=1)
    path.unlink(); real.rename(path)
    resource = store.directory.parent / saved["resources"][0]["path"]
    resource.unlink()
    target = tmp_path / "unselected.dat"; target.write_bytes(b"not bundled")
    resource.symlink_to(target)
    with pytest.raises(ProjectError, match="symbolic|reparse"):
        store.files.resolve(identity, expected_revision=1)


def test_missing_mapping_retains_existing_foreign_platform_rejection_and_does_not_probe_source(tmp_path):
    store = ProjectStore.create(tmp_path / "ordinary", "Ordinary")
    location = "external:windows" if PLATFORM == "posix" else "external:posix"
    source = r"C:\\not-local\\input.dat" if PLATFORM == "posix" else "/not-local/input.dat"
    assert resolve_workspace_path(store.directory, location, source) is None
    with pytest.raises(ProjectError, match="another platform"):
        _resolve(store.directory, location, source)


def test_parent_traversal_and_database_sources_cannot_bypass_file_index_guards(workspace):
    store, _, _, _ = workspace
    with pytest.raises(ProjectError, match="parent"):
        resolve_workspace_path(store.directory, "external:posix", "/old/data/../.ssh/id_rsa")
    path, saved = descriptor(store)
    saved["project"]["aliases"] = ["/original-posix/project", r"Q:\OriginalProject"]
    write(path, saved)
    for location, original in [
            ("external:" + PLATFORM, saved["project"]["source_root"] + "/project.sqlite3"),
            ("external:posix", "/original-posix/project/project.sqlite3"),
            ("external:windows", r"Q:\OriginalProject\project.sqlite3")]:
        with pytest.raises(ProjectError, match="database"):
            _resolve(store.directory, location, original)


def test_primary_current_path_and_multiple_old_platform_aliases_resolve_the_same_copy(workspace):
    store, identity, external, _ = workspace
    path, saved = descriptor(store)
    resource = saved["resources"][0]
    resource["aliases"] = [resource["source"], r"D:\\OldLab\\external.dat", "/previous-machine/measurements/external.dat"]
    actual = store.directory.parent / resource["path"]
    resource["source"] = str(actual)
    write(path, saved)
    external.unlink()
    before, history = store.snapshot(), store.history()
    assert Path(store.files.resolve(identity, expected_revision=1)["path"]) == actual
    assert resolve_workspace_path(store.directory, "external:windows", r"d:\\oldlab\\EXTERNAL.DAT") == actual
    assert resolve_workspace_path(store.directory, "external:posix", "/previous-machine/measurements/external.dat") == actual
    assert resolve_workspace_path(store.directory, "external:" + PLATFORM, str(actual)) == actual
    assert store.snapshot() == before and store.history() == history


@pytest.mark.parametrize("aliases", [["relative/file"], ["/old/../outside"], ["/home/user/.ssh/id_rsa"], "not-array", ["/old/file"] * 129])
def test_invalid_resource_aliases_reject_the_descriptor(workspace, aliases):
    store, identity, _, _ = workspace
    path, saved = descriptor(store)
    saved["resources"][0]["aliases"] = aliases
    write(path, saved)
    with pytest.raises(ProjectError):
        store.files.resolve(identity, expected_revision=1)


def test_same_alias_cannot_retarget_another_resource_even_with_different_windows_case(workspace):
    store, identity, _, _ = workspace
    path, saved = descriptor(store)
    saved["resources"][0]["aliases"] = [r"C:\\old\\source.dat"]
    second = deepcopy(saved["resources"][0])
    second.update(id="second", source="/other/primary.dat", path="resources/second/copy.dat", aliases=[r"c:\\OLD\\SOURCE.DAT"])
    saved["resources"].append(second)
    write(path, saved)
    with pytest.raises(ProjectError, match="different targets"):
        store.files.resolve(identity, expected_revision=1)


def test_project_root_aliases_survive_multiple_platform_and_directory_migrations(workspace):
    store, _, _, _ = workspace
    path, saved = descriptor(store)
    original = saved["project"]["source_root"]
    posix_origin = "/original-posix/project"
    saved["project"]["aliases"] = [original, posix_origin, r"E:\\OldProject\\Study"]
    saved["project"]["source_root"] = str(store.directory)
    (store.directory / "inputs").mkdir()
    actual = store.directory / "inputs" / "raw.dat"; actual.write_bytes(b"project data")
    write(path, saved)
    before = store.snapshot()
    assert resolve_workspace_path(store.directory, "external:" + PLATFORM, original + "/inputs/raw.dat") == actual
    assert resolve_workspace_path(store.directory, "external:posix", posix_origin + "/inputs/raw.dat") == actual
    assert resolve_workspace_path(store.directory, "external:windows", r"e:\\oldproject\\study\\inputs\\raw.dat") == actual
    assert store.snapshot() == before


@pytest.mark.parametrize("aliases", [["relative/project"], ["/project/../outside"], ["/home/user/.ssh"], "not-array", ["/old/project"] * 129])
def test_invalid_project_aliases_reject_the_descriptor(workspace, aliases):
    store, identity, _, _ = workspace
    path, saved = descriptor(store)
    saved["project"]["aliases"] = aliases
    write(path, saved)
    with pytest.raises(ProjectError):
        store.files.resolve(identity, expected_revision=1)


def test_resource_cannot_shadow_a_project_root_alias(workspace):
    store, identity, _, _ = workspace
    path, saved = descriptor(store)
    saved["project"]["aliases"] = ["/old/common"]
    saved["resources"][0]["aliases"] = ["/old/common"]
    write(path, saved)
    with pytest.raises(ProjectError, match="different targets"):
        store.files.resolve(identity, expected_revision=1)
