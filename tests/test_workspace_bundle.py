"""Portable workspace state and unchanged project data; hostile containers publish nothing."""
import hashlib
import json
import os
import errno
from contextlib import contextmanager
from pathlib import Path
import shutil
import stat
from uuid import uuid4
import zipfile

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import workspace_bundle as bundle


def state(**app):
    return {"format": "stk.desktop.workspace-state", "version": 1,
            "windows": [{"x": 42, "width": 1440, "tabs": [{"kind": "python", "draft": "x = 2"}]}],
            "app": {"viewer": {"camera": [1, 2, 3], "clip": [0.1, 100], "visible": False}, **app}}


@pytest.fixture
def project(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "科研工作空间")
    (store.directory / "inputs").mkdir()
    (store.directory / "inputs" / "source.dat").write_bytes(b"frozen project source")
    (store.directory / "results").mkdir()
    (store.directory / "results" / "result.vtk").write_bytes(b"local result")
    ids = store.files.index([str(store.directory / "inputs/source.dat")], expected_revision=0)["record_ids"]
    captured = store.snapshots.capture(ids, expected_revision=1)
    return store, captured["snapshot"]["id"]


def rewrite(source, target, *, mutate=None, extras=()):
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    if mutate:
        mutate(manifest, members)
    members["manifest.json"] = bundle._json(manifest)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        for info, data in extras:
            archive.writestr(info, data)
    return target


def test_roundtrip_captures_all_state_and_sqlite_snapshot_frozen_objects(project, tmp_path):
    store, snapshot_id = project
    original = store.snapshot()
    saved = state(project_root=str(store.directory), input=str(store.directory / "inputs/source.dat"))
    result = bundle.export_workspace(store.directory, tmp_path / "research.stkworkspace", state=saved,
                                     expected_revision=2)
    assert result["complete"] and result["project"]["revision"] == 2
    assert store.snapshot() == original and not (store.directory / "backups").exists()
    preview = bundle.preview_workspace(result["path"])
    assert preview["sha256"] == result["sha256"]
    assert preview["state"]["app"]["project_root"] == "stk-project://"
    assert preview["state"]["app"]["input"] == "stk-project://inputs/source.dat"
    imported = bundle.import_workspace(result["path"], tmp_path / "new-machine", expected_sha256=preview["sha256"])
    copy = ProjectStore(imported["project_directory"])
    assert copy.snapshot() == original and copy.snapshots.verify(snapshot_id)["ok"]
    assert Path(imported["state"]["app"]["input"]).read_bytes() == b"frozen project source"
    assert imported["state"]["windows"] == saved["windows"]
    assert imported["state"]["app"]["viewer"] == saved["app"]["viewer"]
    assert imported["path_map"][str(store.directory)] == imported["project_directory"]
    assert Path(imported["workspace_path"]).exists()


def test_no_project_external_viewer_directory_and_children_relocate(tmp_path):
    viewer = tmp_path / "viewer-payload"
    (viewer / "blobs").mkdir(parents=True)
    (viewer / "manifest.json").write_text('{"format":"example"}')
    (viewer / "blobs/data.bin").write_bytes(bytes(range(256)))
    saved = state(source=str(viewer), child=str(viewer / "blobs/data.bin"))
    result = bundle.export_workspace(None, tmp_path / "viewer.stkworkspace", state=saved,
                                    resources=[{"id": "viewer-1", "path": str(viewer)}])
    imported = bundle.import_workspace(result["path"], tmp_path / "target")
    assert imported["project"] is None and imported["project_directory"] is None and imported["complete"]
    assert Path(imported["state"]["app"]["child"]).read_bytes() == bytes(range(256))
    assert Path(imported["state"]["app"]["source"]) == tmp_path / "target/resources/viewer-1/viewer-payload"
    assert imported["path_map"][str(viewer)] == imported["state"]["app"]["source"]
    assert not (tmp_path / "target/project").exists()


def test_empty_workspace_is_valid_and_no_model_or_execution_imports(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Workspace transfer cannot execute or contact a model")
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = bundle.export_workspace(None, tmp_path / "empty.stkworkspace", state=state())
    assert bundle.preview_workspace(result["path"])["file_count"] == 1
    imported = bundle.import_workspace(result["path"], tmp_path / "empty")
    assert imported["state"] == state()


def test_export_flushes_a_writable_archive_before_publication(tmp_path, monkeypatch):
    """Windows rejects fsync on a read-only CRT descriptor; keep the flush mandatory."""
    original_open, original_fsync = Path.open, os.fsync
    archives, flushed = {}, []
    def opened(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.name == "bundle.zip" and path.parent.name.startswith(".stk-workspace-"):
            archives[stream.fileno()] = stream
        return stream
    def synced(descriptor):
        stream = archives.get(descriptor)
        if stream is not None and not stream.closed:
            if not stream.writable():
                raise OSError(errno.EBADF, "Windows cannot flush a read-only descriptor")
            flushed.append(descriptor)
        return original_fsync(descriptor)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(os, "fsync", synced)
    exported = bundle.export_workspace(None, tmp_path / "flushed.stkworkspace", state=state())
    assert flushed and Path(exported["path"]).is_file()
    assert bundle.preview_workspace(exported["path"])["sha256"] == exported["sha256"]


@pytest.mark.parametrize("change_source", [False, True], ids=["unchanged", "changed"])
def test_export_checks_full_path_identity_when_scandir_omits_it(project, tmp_path, monkeypatch, change_source):
    """Windows DirEntry.stat omits dev/inode, unlike a fresh path lstat."""
    store, _ = project
    original_scandir, original_write = os.scandir, bundle._write_member
    class Entry:
        def __init__(self, entry):
            self.entry = entry
        def __getattr__(self, name):
            return getattr(self.entry, name)
        def stat(self, *args, **kwargs):
            info = self.entry.stat(*args, **kwargs)
            class Info:
                st_dev = st_ino = 0
                def __getattr__(self, name):
                    return getattr(info, name)
            return Info()
    @contextmanager
    def scanned(path):
        with original_scandir(path) as entries:
            if isinstance(path, (str, os.PathLike)) and Path(path).is_relative_to(store.directory):
                yield (Entry(entry) for entry in entries)
            else:
                yield entries
    changed = []
    def written(archive, name, source, remaining):
        result = original_write(archive, name, source, remaining)
        if change_source and name == "project/inputs/source.dat":
            source.write_bytes(b"source changed after the file was archived")
            changed.append(name)
        return result
    monkeypatch.setattr(os, "scandir", scanned)
    monkeypatch.setattr(bundle, "_write_member", written)
    target = tmp_path / "identity.stkworkspace"
    if change_source:
        with pytest.raises(ProjectError, match="project files changed"):
            bundle.export_workspace(store.directory, target, state=state())
        assert changed and not target.exists()
    else:
        exported = bundle.export_workspace(store.directory, target, state=state())
        assert exported["complete"]
        restored = bundle.import_workspace(target, tmp_path / "restored-identity")
        assert (Path(restored["project_directory"]) / "inputs/source.dat").read_bytes() == b"frozen project source"


def test_external_explicit_file_is_packed_but_unknown_absolute_path_never_read(project, tmp_path, monkeypatch):
    store, _ = project
    data = tmp_path / "outside.dat"
    data.write_bytes(b"external")
    unknown = tmp_path / "unknown.dat"
    unknown.write_bytes(b"do not read")
    original = bundle._reader
    def reader(path):
        assert path != unknown
        return original(path)
    monkeypatch.setattr(bundle, "_reader", reader)
    result = bundle.export_workspace(store.directory, tmp_path / "files.stkworkspace",
        state=state(source=str(data), unknown=str(unknown)), resources=[{"id": "source", "path": str(data)}])
    assert not result["complete"]
    assert [item["code"] for item in result["diagnostics"] if item["code"] != "excluded_internal_file"] == ["unmapped_absolute_path"]
    imported = bundle.import_workspace(result["path"], tmp_path / "copy")
    assert Path(imported["state"]["app"]["source"]).read_bytes() == b"external"
    assert imported["state"]["app"]["unknown"] == str(unknown)


def test_unselected_indexed_external_file_is_diagnostic_not_read(project, tmp_path, monkeypatch):
    store, _ = project
    external = tmp_path / "external.dat"
    external.write_bytes(b"not selected")
    store.files.index([str(external)], expected_revision=2)
    original = bundle._reader
    def reader(path):
        assert path != external
        return original(path)
    monkeypatch.setattr(bundle, "_reader", reader)
    result = bundle.export_workspace(store.directory, tmp_path / "test.stkworkspace", state=state())
    assert not result["complete"] and "external_not_included" in {item["code"] for item in result["diagnostics"]}


@pytest.mark.parametrize("key", ["api_key", "password", "credentials", "private_key", "model_endpoint",
                                 "network_policy", "STK_TOKEN_PLAN_API_KEY"])
def test_state_forbids_machine_credentials_before_reading_files(tmp_path, key):
    with pytest.raises(ProjectError, match="credentials"):
        bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state(nested={key: "abcdefghijklmnopqrstu"}))
    assert not (tmp_path / "out.stkworkspace").exists()


def test_ordinary_scientific_key_token_and_endpoint_labels_remain_valid(tmp_path):
    value = state(parameters={"key": 12, "token": "atom", "endpoint": [0, 100]})
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=value)
    assert bundle.preview_workspace(result["path"])["state"] == value


def test_sensitive_names_are_excluded_without_opening_and_missing_resources_are_explicit(project, tmp_path, monkeypatch):
    store, _ = project
    blocked = store.directory / ".env"
    blocked.write_bytes(b"abcdefghijklmnopqrstu")
    key = tmp_path / "id_rsa"
    key.write_bytes(b"abcdefghijklmnopqrstu")
    original = bundle._reader
    def reader(path):
        assert path not in (blocked, key)
        return original(path)
    monkeypatch.setattr(bundle, "_reader", reader)
    result = bundle.export_workspace(store.directory, tmp_path / "safe.stkworkspace", state=state(),
        resources=[{"id": "blocked", "path": str(key)}, {"id": "missing", "path": str(tmp_path / "gone.dat")}])
    assert not result["complete"]
    assert {item["code"] for item in result["diagnostics"]} >= {"excluded_private_file", "excluded_private_resource", "missing_resource"}
    with zipfile.ZipFile(result["path"]) as archive:
        assert not any(".env" in name or "id_rsa" in name for name in archive.namelist())


def test_stale_revision_budget_and_existing_outputs_never_publish_or_mutate(project, tmp_path):
    store, _ = project
    original = store.snapshot()
    target = tmp_path / "out.stkworkspace"
    with pytest.raises(RevisionConflict):
        bundle.export_workspace(store.directory, target, state=state(), expected_revision=1)
    with pytest.raises(ProjectError, match="budget"):
        bundle.export_workspace(store.directory, target, state=state(), max_bytes=16)
    assert not target.exists() and store.snapshot() == original
    target.write_bytes(b"existing")
    with pytest.raises(ProjectError, match="exists"):
        bundle.export_workspace(store.directory, target, state=state())
    assert target.read_bytes() == b"existing"


def test_import_sha_guard_existing_destination_and_failure_cleanup(project, tmp_path):
    store, _ = project
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    destination = tmp_path / "copy"
    with pytest.raises(ProjectError, match="changed since preview"):
        bundle.import_workspace(result["path"], destination, expected_sha256="0" * 64)
    assert not destination.exists() and not list(tmp_path.glob(".stk-import-*"))
    destination.mkdir()
    with pytest.raises(ProjectError, match="exists"):
        bundle.import_workspace(result["path"], destination)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape", "/absolute", "project/../../escape", "project\\escape", "C:/escape", "project/CON", "project/file."])
def test_zip_member_path_traversal_and_nonportable_names_rejected(tmp_path, name):
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state())
    bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", extras=[(name, b"bad")])
    with pytest.raises(ProjectError):
        bundle.import_workspace(bad, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


@pytest.mark.parametrize("mode", ["duplicate", "case", "link", "unlisted", "checksum", "missing", "bomb"])
def test_duplicate_link_manifest_and_checksum_attacks_publish_nothing(tmp_path, mode):
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state())
    extras = []
    def mutate(manifest, members):
        if mode == "duplicate":
            extras.append(("state.json", members["state.json"]))
        elif mode == "case":
            extras.append(("State.json", b"{}"))
        elif mode == "link":
            info = zipfile.ZipInfo("project/link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            extras.append((info, b"/etc/passwd"))
        elif mode == "unlisted":
            extras.append(("project/extra.dat", b"unknown"))
        elif mode == "checksum":
            members["state.json"] = b" " * len(members["state.json"])
        elif mode == "missing":
            del members["state.json"]
        else:
            manifest["files"][0]["size"] = 1 << 50
    if mode == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"):
            bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", mutate=mutate, extras=extras)
    else:
        bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", mutate=mutate, extras=extras)
    with pytest.raises(ProjectError):
        bundle.import_workspace(bad, tmp_path / "copy")
    assert not (tmp_path / "copy").exists() and not list(tmp_path.glob(".stk-import-*"))


def test_forged_sensitive_state_and_unknown_resource_uri_are_rejected(tmp_path):
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state())
    for i, value in enumerate([state(credentials="abcdefghijklmnopqrstu"), state(source="stk-resource://unlisted")]):
        def mutate(manifest, members):
            members["state.json"] = bundle._json(value)
            manifest["files"][0] = {"path": "state.json", "size": len(members["state.json"]),
                "sha256": hashlib.sha256(members["state.json"]).hexdigest()}
        bad = rewrite(result["path"], tmp_path / f"bad-{i}.stkworkspace", mutate=mutate)
        with pytest.raises(ProjectError):
            bundle.import_workspace(bad, tmp_path / f"copy-{i}")
        assert not (tmp_path / f"copy-{i}").exists()


def test_project_identity_forgery_rejected_after_checksum_verification(project, tmp_path):
    store, _ = project
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    def mutate(manifest, members):
        manifest["project"]["id"] = str(uuid4())
    bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", mutate=mutate)
    with pytest.raises(ProjectError, match="identity"):
        bundle.import_workspace(bad, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


def test_changed_project_file_during_export_does_not_publish(project, tmp_path, monkeypatch):
    store, _ = project
    original = bundle._write_member
    def write(*args):
        result = original(*args)
        if args[1] == "project/inputs/source.dat":
            args[2].write_bytes(b"changed after reading")
        return result
    monkeypatch.setattr(bundle, "_write_member", write)
    with pytest.raises(ProjectError, match="changed"):
        bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    assert not (tmp_path / "out.stkworkspace").exists()


def test_publish_race_does_not_replace_even_empty_destination(tmp_path, monkeypatch):
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state())
    original = bundle._publish_directory
    def raced(source, destination):
        destination.mkdir()
        original(source, destination)
    monkeypatch.setattr(bundle, "_publish_directory", raced)
    with pytest.raises((ProjectError, FileExistsError)):
        bundle.import_workspace(result["path"], tmp_path / "race")
    assert list((tmp_path / "race").iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks requires special Windows privileges")
def test_project_links_skipped_and_selected_link_or_symlink_output_rejected(project, tmp_path):
    store, _ = project
    external = tmp_path / "outside.dat"
    external.write_bytes(b"not automatically read")
    (store.directory / "linked.dat").symlink_to(external)
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    assert not result["complete"] and "excluded_link" in {item["code"] for item in result["diagnostics"]}
    with pytest.raises(ProjectError, match="symbolic"):
        bundle.export_workspace(None, tmp_path / "linked.stkworkspace", state=state(),
                                resources=[{"id": "link", "path": str(store.directory / "linked.dat")}])
    alias = tmp_path / "alias"
    alias.symlink_to(store.directory, target_is_directory=True)
    with pytest.raises(ProjectError, match="symbolic"):
        bundle.export_workspace(alias, tmp_path / "bad.stkworkspace", state=state())


def test_export_rejects_own_output_inside_project_or_resource_directory(project, tmp_path):
    store, _ = project
    with pytest.raises(ProjectError, match="outside"):
        bundle.export_workspace(store.directory, store.directory / "inside.stkworkspace", state=state())
    resource = tmp_path / "payload"
    resource.mkdir()
    with pytest.raises(ProjectError, match="outside"):
        bundle.export_workspace(None, resource / "inside.stkworkspace", state=state(),
                                resources=[{"id": "viewer", "path": str(resource)}])


def test_reopen_after_a_second_directory_move_keeps_uuid_and_rebases_all_paths(project, tmp_path):
    store, _ = project
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace",
                                     state=state(source=str(store.directory / "results/result.vtk")))
    imported = bundle.import_workspace(result["path"], tmp_path / "first")
    moved = tmp_path / "second-machine"
    shutil.move(imported["directory"], moved)
    reopened = bundle.open_workspace(moved)
    assert reopened["project_directory"] == str(moved / "project")
    assert Path(reopened["state"]["app"]["source"]).read_bytes() == b"local result"
    assert reopened["path_map"][str(store.directory)] == str(moved / "project")
    assert ProjectStore(reopened["project_directory"]).info()["id"] == store.info()["id"]


def test_project_file_addition_during_export_does_not_publish(project, tmp_path, monkeypatch):
    store, _ = project
    original = bundle._write_member
    def write(*args):
        result = original(*args)
        if args[1] == "project/results/result.vtk":
            (store.directory / "new-file.dat").write_bytes(b"changed tree")
        return result
    monkeypatch.setattr(bundle, "_write_member", write)
    with pytest.raises(ProjectError, match="tree changed"):
        bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    assert not (tmp_path / "out.stkworkspace").exists()


@pytest.mark.parametrize("names", [("resources/x/Directory/a", "resources/x/directory/b"), ("project/file", "project/file/child")])
def test_cross_platform_directory_collisions_and_file_parent_conflicts_rejected(tmp_path, names):
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state())
    bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", extras=[(name, b"bad") for name in names])
    with pytest.raises(ProjectError, match="collide|parent directory"):
        bundle.preview_workspace(bad)
    assert not (tmp_path / "copy").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_exported_archive_and_import_descriptor_are_private(tmp_path):
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state())
    assert stat.S_IMODE(Path(result["path"]).stat().st_mode) == 0o600
    imported = bundle.import_workspace(result["path"], tmp_path / "copy")
    assert stat.S_IMODE(Path(imported["directory"]).stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(imported["workspace_path"]).stat().st_mode) == 0o600


def test_empty_project_directories_and_selected_working_directory_survive_roundtrip(project, tmp_path):
    store, _ = project
    empty = store.directory / "inputs/empty"
    empty.mkdir()
    (store.directory / "new-program/folder").mkdir(parents=True)
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state(directory=str(empty)))
    assert result["complete"]
    imported = bundle.import_workspace(result["path"], tmp_path / "copy")
    assert Path(imported["state"]["app"]["directory"]).is_dir()
    assert list(Path(imported["state"]["app"]["directory"]).iterdir()) == []
    assert (Path(imported["project_directory"]) / "new-program/folder").is_dir()
    with zipfile.ZipFile(result["path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert "project/inputs/empty" in manifest["directories"]
        assert "project/inputs/empty" not in archive.namelist()


def test_empty_external_viewer_directory_and_nested_empty_children_survive(tmp_path):
    source = tmp_path / "payload"
    (source / "empty/nested").mkdir(parents=True)
    result = bundle.export_workspace(None, tmp_path / "out.stkworkspace", state=state(directory=str(source / "empty/nested")),
        resources=[{"id": "viewer", "path": str(source)}])
    imported = bundle.import_workspace(result["path"], tmp_path / "copy")
    assert result["complete"] and Path(imported["state"]["app"]["directory"]).is_dir()
    assert list(Path(imported["state"]["app"]["directory"]).iterdir()) == []


@pytest.mark.parametrize("names", [["../escape"], ["resources/x/missing"], ["project/a", "project/A"], ["project/.ssh"], ["project/CON"]])
def test_forged_directory_inventory_cannot_escape_collide_or_restore_credentials(project, tmp_path, names):
    store, _ = project
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", mutate=lambda manifest, members: manifest.update(directories=names))
    with pytest.raises(ProjectError):
        bundle.import_workspace(bad, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


def test_directory_inventory_cannot_conflict_with_a_regular_file(project, tmp_path):
    store, _ = project
    result = bundle.export_workspace(store.directory, tmp_path / "out.stkworkspace", state=state())
    bad = rewrite(result["path"], tmp_path / "bad.stkworkspace", mutate=lambda manifest, members:
                  manifest.update(directories=["project/inputs/source.dat/child"]))
    with pytest.raises(ProjectError, match="parent directory"):
        bundle.preview_workspace(bad)


def test_preview_never_opens_a_named_credential_file_even_when_selected_as_an_archive(tmp_path, monkeypatch):
    secret = tmp_path / "id_rsa"
    secret.write_bytes(b"abcdefghijklmnopqrstu")
    original = bundle.os.open
    def opened(path, *args, **kwargs):
        assert Path(path) != secret
        return original(path, *args, **kwargs)
    monkeypatch.setattr(bundle.os, "open", opened)
    with pytest.raises(ProjectError, match="credential"):
        bundle.preview_workspace(secret)


def test_project_backup_directory_is_internal_without_incomplete_restore_confirmation(project, tmp_path):
    store, _ = project
    backup = Path(store.backup()['path'])
    assert backup.is_file()
    exported = bundle.export_workspace(store.directory, tmp_path / 'out.stkworkspace', state=state())
    assert exported['complete']
    assert {'code':'excluded_internal_file','path':'backups'} in exported['diagnostics']
    with zipfile.ZipFile(exported['path']) as archive:
        assert not any(name.startswith('project/backups/') for name in archive.namelist())


def test_macos_standard_alias_rule_cannot_canonicalize_arbitrary_resource_symlinks(monkeypatch):
    monkeypatch.setattr(bundle.sys, 'platform', 'darwin')
    monkeypatch.setattr(bundle.Path, 'is_symlink', lambda path: True)
    monkeypatch.setattr(bundle.Path, 'resolve', lambda path: Path('/private') / path.name)
    assert bundle._standard_macos_alias(Path('/var'))
    assert bundle._standard_macos_alias(Path('/tmp'))
    assert bundle._standard_macos_alias(Path('/etc'))
    assert not bundle._standard_macos_alias(Path('/tmp/user-link'))
    assert not bundle._standard_macos_alias(Path('/var/selected-resource'))
    monkeypatch.setattr(bundle.Path, 'resolve', lambda path: Path('/elsewhere'))
    assert not bundle._standard_macos_alias(Path('/var'))


def test_trusted_system_root_alias_relocates_state_and_remains_portable(project, tmp_path, monkeypatch):
    store, snapshot_id = project
    alias = tmp_path / 'trusted-system-prefix'
    try:
        alias.symlink_to(store.directory, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip('Directory symlinks are unavailable')
    # Simulate only the fixed macOS system-prefix exception. All other link checks,
    # project reads, JSON relocation, archive validation and SQLite backup are real.
    standard = bundle._standard_macos_alias
    monkeypatch.setattr(bundle, '_standard_macos_alias', lambda path: path == alias or standard(path))
    saved = state(project_root=str(alias), source=str(alias / 'inputs/source.dat'))
    exported = bundle.export_workspace(alias, tmp_path / 'first.stkworkspace', state=saved)
    assert exported['complete'], exported['diagnostics']
    assert str(alias) in exported['project']['aliases']
    first = bundle.import_workspace(exported['path'], tmp_path / 'first')
    assert first['state']['app']['project_root'] == first['project_directory']
    assert Path(first['state']['app']['source']).read_bytes() == b'frozen project source'
    assert first['path_map'][str(alias)] == first['project_directory']
    assert ProjectStore(first['project_directory']).snapshots.verify(snapshot_id)['ok']
    second_export = bundle.export_workspace(first['project_directory'], tmp_path / 'second.stkworkspace', state=saved)
    assert second_export['complete'], second_export['diagnostics']
    second = bundle.import_workspace(second_export['path'], tmp_path / 'second')
    assert second['state']['app']['project_root'] == second['project_directory']
    assert Path(second['state']['app']['source']).read_bytes() == b'frozen project source'
    assert second['path_map'][str(alias)] == second['project_directory']


def test_untrusted_project_root_symlink_still_refuses_before_export(project, tmp_path):
    store, _ = project
    alias = tmp_path / 'untrusted-user-link'
    try:
        alias.symlink_to(store.directory, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip('Directory symlinks are unavailable')
    with pytest.raises(ProjectError, match='symbolic links'):
        bundle.export_workspace(alias, tmp_path / 'out.stkworkspace', state=state(project_root=str(alias)))
    assert not (tmp_path / 'out.stkworkspace').exists()


def trusted_prefix(tmp_path, monkeypatch):
    alias = tmp_path / 'trusted-system-prefix'
    try:
        alias.symlink_to(tmp_path, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip('Directory symlinks are unavailable')
    standard = bundle._standard_macos_alias
    monkeypatch.setattr(bundle, '_standard_macos_alias', lambda path: path == alias or standard(path))
    return alias


@pytest.mark.parametrize('kind,aliased_output', [('project', True), ('project', False), ('resource', True), ('resource', False)])
def test_trusted_prefix_cannot_hide_export_inside_project_or_selected_resource(project, tmp_path, monkeypatch, kind, aliased_output):
    store, _ = project
    alias = trusted_prefix(tmp_path, monkeypatch)
    if kind == 'project':
        source = store.directory if aliased_output else alias / 'project'
        output = (alias / 'project' if aliased_output else store.directory) / 'inside.stkworkspace'
        resources = None
    else:
        asset = tmp_path / 'viewer-assets'; asset.mkdir(); (asset / 'manifest.json').write_text('{}')
        source = None
        resources = [{'id':'viewer', 'path':str(asset if aliased_output else alias / 'viewer-assets')}]
        output = (alias / 'viewer-assets' if aliased_output else asset) / 'inside.stkworkspace'
    with pytest.raises(ProjectError, match='outside its (project|resource) director'):
        bundle.export_workspace(source, output, state=state(), resources=resources)
    assert not output.exists()


def test_trusted_prefix_reader_import_reopen_and_resource_history_share_physical_paths(project, tmp_path, monkeypatch):
    store, _ = project; alias = trusted_prefix(tmp_path, monkeypatch)
    asset = tmp_path / 'viewer-assets'; asset.mkdir(); (asset / 'empty').mkdir()
    external = asset / 'source.vtk'; external.write_bytes(b'public viewer asset')
    record = store.files.index([str(external)], expected_revision=store.info()['revision'])['record_ids'][0]
    saved = state(project_root=str(alias / 'project'), source=str(alias / 'viewer-assets/source.vtk'))
    exported = bundle.export_workspace(alias / 'project', alias / 'first.stkworkspace', state=saved,
        resources=[{'id':'viewer', 'path':str(alias / 'viewer-assets')}])
    assert exported['complete'], exported['diagnostics']
    assert Path(exported['path']) == tmp_path / 'first.stkworkspace'
    preview = bundle.preview_workspace(alias / 'first.stkworkspace')
    first = bundle.import_workspace(alias / 'first.stkworkspace', alias / 'first', expected_sha256=preview['sha256'])
    assert first['directory'] == str(tmp_path / 'first')
    reopened = bundle.open_workspace(alias / 'first/workspace.json')
    assert reopened['directory'] == first['directory']
    assert reopened['project_directory'] == first['project_directory']
    assert Path(reopened['state']['app']['source']).read_bytes() == b'public viewer asset'
    assert (Path(reopened['state']['app']['source']).parent / 'empty').is_dir()
    first_store = ProjectStore(reopened['project_directory'])
    assert Path(first_store.files.resolve(record, expected_revision=first_store.info()['revision'])['path']).read_bytes() == b'public viewer asset'
    local = Path(reopened['state']['app']['source']).parent
    aliased_local = alias / local.relative_to(tmp_path)
    second_export = bundle.export_workspace(alias / 'first/project', alias / 'second.stkworkspace', state=saved,
        resources=[{'id':'viewer', 'path':str(aliased_local)}])
    assert second_export['complete'], second_export['diagnostics']
    second = bundle.import_workspace(second_export['path'], alias / 'second')
    expected_history = first_store.history()
    shutil.rmtree(asset)
    shutil.rmtree(tmp_path / 'first')
    second_store = ProjectStore(second['project_directory'])
    assert Path(second_store.files.resolve(record, expected_revision=second_store.info()['revision'])['path']).read_bytes() == b'public viewer asset'
    assert second_store.history() == expected_history


def test_trusted_prefix_and_physical_resource_descriptors_merge_without_ambiguous_targets(tmp_path, monkeypatch):
    alias = trusted_prefix(tmp_path, monkeypatch)
    asset = tmp_path / 'data.vtk'; asset.write_bytes(b'public scientific asset')
    exported = bundle.export_workspace(None, tmp_path / 'out.stkworkspace', state=state(one=str(asset), two=str(alias / 'data.vtk')),
        resources=[{'id':'selected', 'path':str(alias / 'data.vtk')}, {'id':'indexed', 'path':str(asset)}])
    assert exported['complete'], exported['diagnostics']
    preview = bundle.preview_workspace(exported['path'])
    assert len(preview['resources']) == 1
    imported = bundle.import_workspace(exported['path'], alias / 'imported')
    assert imported['state']['app']['one'] == imported['state']['app']['two']
    assert Path(imported['state']['app']['one']).read_bytes() == b'public scientific asset'


def test_trusted_prefix_does_not_allow_nested_user_links(tmp_path, monkeypatch):
    alias = trusted_prefix(tmp_path, monkeypatch)
    source = tmp_path / 'data.vtk'; source.write_bytes(b'public data')
    (tmp_path / 'user-link.vtk').symlink_to(source)
    with pytest.raises(ProjectError, match='symbolic links'):
        bundle.export_workspace(None, tmp_path / 'out.stkworkspace', state=state(),
            resources=[{'id':'viewer','path':str(alias / 'user-link.vtk')}])


def test_reexport_inherits_initial_and_intermediate_resource_and_project_origins(project, tmp_path):
    store, _ = project
    external = tmp_path / 'original.dat'
    external.write_bytes(b'public scientific source')
    record = store.files.index([str(external)], expected_revision=2)['record_ids'][0]
    exported = bundle.export_workspace(store.directory, tmp_path / 'first.stkworkspace',
        state=state(source=str(external)), resources=[{'id':'source','path':str(external)}])
    first = bundle.import_workspace(exported['path'], tmp_path / 'first')
    external.unlink()
    first_store = ProjectStore(first['project_directory'])
    first_local = first['state']['app']['source']
    new_record = first_store.files.index([first_local], expected_revision=first_store.info()['revision'])['record_ids'][0]
    expected_history = first_store.history()
    second_export = bundle.export_workspace(first_store.directory, tmp_path / 'second.stkworkspace',
        state=state(source=str(external), project_root=str(store.directory)), resources=[{'id':'source','path':first_local}])
    assert second_export['complete'], second_export['diagnostics']
    second = bundle.import_workspace(second_export['path'], tmp_path / 'second')
    shutil.rmtree(first['directory'])
    second_store = ProjectStore(second['project_directory'])
    for identity in (record,new_record):
        assert Path(second_store.files.resolve(identity, expected_revision=second_store.info()['revision'])['path']).read_bytes() == b'public scientific source'
    assert second['state']['app']['project_root'] == second['project_directory']
    assert second_store.history() == expected_history
    assert second['path_map'][str(external)] == second['state']['app']['source']
    assert second['path_map'][str(store.directory)] == second['project_directory']
    third_export = bundle.export_workspace(second_store.directory, tmp_path / 'third.stkworkspace',
        state=state(source=str(external)), resources=[{'id':'source','path':second['state']['app']['source']}])
    third = bundle.import_workspace(third_export['path'], tmp_path / 'third')
    shutil.rmtree(second['directory'])
    third_store = ProjectStore(third['project_directory'])
    for identity in (record,new_record):
        assert Path(third_store.files.resolve(identity, expected_revision=third_store.info()['revision'])['path']).read_bytes() == b'public scientific source'
    assert third_store.history() == expected_history and third_export['complete']


@pytest.mark.parametrize('aliases', [['relative'], ['bad\0path'], 12, ['/path']*129])
def test_invalid_resource_aliases_are_rejected_before_publication(tmp_path, aliases):
    source=tmp_path/'source.dat'; source.write_bytes(b'public')
    with pytest.raises(ProjectError):
        bundle.export_workspace(None,tmp_path/'out.stkworkspace',state=state(),resources=[{'id':'source','path':str(source),'aliases':aliases}])
    assert not (tmp_path/'out.stkworkspace').exists()


def test_source_alias_cannot_map_two_resources_to_different_targets(tmp_path):
    one,two=tmp_path/'one.dat',tmp_path/'two.dat'
    one.write_bytes(b'one');two.write_bytes(b'two')
    with pytest.raises(ProjectError,match='different'):
        bundle.export_workspace(None,tmp_path/'out.stkworkspace',state=state(),resources=[
            {'id':'one','path':str(one),'aliases':['/old/shared.dat']},
            {'id':'two','path':str(two),'aliases':['/old/shared.dat']}])
    assert not (tmp_path/'out.stkworkspace').exists()
